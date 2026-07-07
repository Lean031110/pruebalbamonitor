"""Router de backups: listado, trigger, descarga."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import not_found
from lbamonitor.api.schemas.common import MessageResponse
from lbamonitor.api.schemas.system import BackupRecordResponse, BackupTriggerResponse
from lbamonitor.core.config import get_settings
from lbamonitor.core.db import get_db, get_session_factory
from lbamonitor.core.models import User
from lbamonitor.core.security.auth import require_admin, require_operator
from lbamonitor.core.services.backup_engine import BackupEngine

router = APIRouter(prefix="/backups", tags=["backups"])


def _get_engine() -> BackupEngine:
    s = get_settings()
    factory = get_session_factory()
    return BackupEngine(
        session_factory=factory,
        db_path=s.database.path,
        destination=s.backup.destination,
        max_backups=s.backup.keep_days,
    )


@router.get("", response_model=list[BackupRecordResponse])
async def list_backups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    engine = _get_engine()
    records = await engine.list_backups()
    return [BackupRecordResponse.model_validate(r) for r in records]


@router.post("/trigger", response_model=BackupTriggerResponse)
async def trigger_backup(
    notes: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Fuerza un backup ahora."""
    try:
        engine = _get_engine()
        record = await engine.backup(auto=False, notes=notes)
        return BackupTriggerResponse(
            success=True,
            backup=BackupRecordResponse.model_validate(record),
            message="Backup creado correctamente",
        )
    except Exception as e:
        return BackupTriggerResponse(success=False, message=f"Error: {e}")


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Descarga el archivo de un backup."""
    engine = _get_engine()
    records = await engine.list_backups()
    record = next((r for r in records if r.id == backup_id), None)
    if not record:
        raise not_found(f"Backup {backup_id} no encontrado")
    p = Path(record.file_path)
    if not p.is_file():
        raise not_found(f"Archivo de backup no existe: {p}")
    return FileResponse(
        path=str(p),
        filename=p.name,
        media_type="application/octet-stream",
    )
