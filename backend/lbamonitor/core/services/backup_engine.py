"""
Motor de backups: VACUUM INTO para SQLite (snapshot consistente sin bloquear
escrituras) + rotación automática.

Para PostgreSQL se usaría pg_dump (no implementado en esta versión).
"""
from __future__ import annotations

import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.config import get_settings
from lbamonitor.core.models import BackupRecord
from lbamonitor.utils.helpers import timestamp_filename, utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


class BackupEngine:
    """Genera y rota backups de la BD."""

    def __init__(self, session_factory, db_path: str, destination: str, max_backups: int = 30) -> None:
        self._factory = session_factory
        self._db_path = Path(db_path)
        self._destination = Path(destination)
        self._max_backups = max_backups

    async def backup(self, auto: bool = True, notes: Optional[str] = None) -> BackupRecord:
        """
        Crea un backup consistente de la BD.

        - SQLite: usa VACUUM INTO (no bloquea escrituras)
        - PostgreSQL: no implementado (usar pg_dump externo)

        Args:
            auto: True si es automático (scheduler), False si es manual.
            notes: notas opcionales.
        """
        self._destination.mkdir(parents=True, exist_ok=True)

        s = get_settings().database
        if s.engine != "sqlite":
            raise NotImplementedError("Backup solo implementado para SQLite")

        # Nombre del archivo
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"lbamonitor_{ts}.db"
        dest_path = self._destination / filename

        # VACUUM INTO via SQL (snapchat consistente)
        # Se ejecuta en un thread para no bloquear event loop
        await asyncio.to_thread(self._vacuum_into, str(dest_path))

        size = dest_path.stat().st_size if dest_path.exists() else 0

        # Registrar en BD
        async with self._factory() as session:
            record = BackupRecord(
                file_path=str(dest_path),
                size_bytes=size,
                auto=auto,
                notes=notes,
                created_at=utcnow(),
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)

        log.info(
            f"Backup creado: {dest_path.name} ({size} bytes, auto={auto})"
        )

        # Rotar backups antiguos
        await self._rotate()

        return record

    def _vacuum_into(self, dest_path: str) -> None:
        """Ejecuta VACUUM INTO en un hilo síncrono. Path validado contra inyección SQL."""
        import re
        # Validar que el path no contiene comillas (previene SQL injection vía VACUUM INTO)
        if not re.match(r"^[A-Za-z0-9_./\\:\- ]+$", dest_path):
            raise ValueError(f"Path de backup contiene caracteres no permitidos: {dest_path!r}")
        # VACUUM INTO es atómico y no bloquea escrituras
        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
        try:
            # Escapar comillas simples duplicándolas (defensa en profundidad)
            safe_path = dest_path.replace("'", "''")
            conn.execute(f"VACUUM INTO '{safe_path}'")
        finally:
            conn.close()

    async def _rotate(self) -> None:
        """Elimina los backups más antiguos si superamos max_backups."""
        backups = sorted(
            self._destination.glob("lbamonitor_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if len(backups) <= self._max_backups:
            return

        to_delete = backups[self._max_backups:]
        for old in to_delete:
            try:
                old.unlink()
                log.debug(f"Backup antiguo eliminado: {old.name}")
            except OSError as e:
                log.warning(f"No se pudo eliminar backup {old}: {e}")

    async def list_backups(self) -> list[BackupRecord]:
        """Lista los backups registrados en BD."""
        from sqlalchemy import select
        async with self._factory() as session:
            result = await session.execute(
                select(BackupRecord).order_by(BackupRecord.created_at.desc())
            )
            return list(result.scalars().all())

    async def restore(self, backup_path: str) -> bool:
        """
        Restaura un backup. PELIGROSO: sobrescribe la BD actual.

        1. Hace backup de seguridad de la BD actual (.pre_restore.<ts>.db)
        2. Copia el backup indicado sobre la BD actual
        """
        src = Path(backup_path)
        if not src.is_file():
            log.error(f"Backup no existe: {backup_path}")
            return False

        # Backup de seguridad previo
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safety_path = self._db_path.parent / f"{self._db_path.stem}.pre_restore.{ts}.db"

        try:
            await asyncio.to_thread(shutil.copy2, self._db_path, safety_path)
            await asyncio.to_thread(shutil.copy2, src, self._db_path)
            log.info(
                f"BD restaurada desde {src.name}. "
                f"Backup de seguridad en {safety_path.name}"
            )
            return True
        except Exception as e:
            log.exception(f"Error restaurando backup: {e}")
            return False
