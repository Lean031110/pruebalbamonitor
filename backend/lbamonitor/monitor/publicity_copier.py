"""
Auto-copiador de archivos de publicidad al insertar una USB.

Si la configuración `paths.publicity_automatic` está activada, al insertar
una memoria USB se copian recursivamente todos los archivos de
`paths.publicity_folder` al dispositivo.

CRÍTICO: La copia de archivos es una operación BLOQUEANTE (I/O síncrono).
Se ejecuta con `asyncio.to_thread()` para no congelar el event loop
(detección de nuevos USB).
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from lbamonitor.utils.helpers import utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


async def copy_publicity_to_usb(
    drive_letter: str,
    source_folder: str,
    overwrite: bool = False,
) -> dict:
    """
    Copia recursivamente todos los archivos de `source_folder` al dispositivo
    con letra `drive_letter`.

    Se ejecuta en un hilo (asyncio.to_thread) para no bloquear el event loop.

    Args:
        drive_letter: "E:" o "E:\\" (destino)
        source_folder: ruta local con archivos a copiar
        overwrite: si True, sobrescribe archivos existentes

    Devuelve dict con: copied_count, skipped_count, failed_count, bytes_copied,
    duration_seconds, errors (list of str).
    """
    start = utcnow()
    result = {
        "copied_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "bytes_copied": 0,
        "duration_seconds": 0.0,
        "errors": [],
    }

    # Validar inputs
    src = Path(source_folder)
    if not src.is_dir():
        msg = f"Carpeta de publicidad no existe: {source_folder}"
        log.warning(msg)
        result["errors"].append(msg)
        return result

    # Normalizar destino (acepta "E:", "E:\\", "E:/", "/media/usb")
    dest_str = drive_letter.replace("\\", "/").rstrip("/")
    dest = Path(dest_str)
    if not dest.is_dir():
        msg = f"Destino no accesible: {dest}"
        log.warning(msg)
        result["errors"].append(msg)
        return result

    log.info(f"Iniciando copia de publicidad: {src} → {dest}")

    # Ejecutar copia en hilo para no bloquear event loop
    await asyncio.to_thread(
        _copy_tree_sync, src, dest, overwrite, result
    )

    end = utcnow()
    result["duration_seconds"] = (end - start).total_seconds()
    log.info(
        f"Copia de publicidad completada: {result['copied_count']} archivos, "
        f"{result['skipped_count']} saltados, {result['failed_count']} errores, "
        f"{result['bytes_copied']} bytes en {result['duration_seconds']:.1f}s"
    )
    return result


def _copy_tree_sync(
    src: Path,
    dest: Path,
    overwrite: bool,
    result: dict,
) -> None:
    """
    Copia recursiva síncrona (se ejecuta en un hilo).

    Preserva la estructura de subcarpetas.
    """
    try:
        for src_path in src.rglob("*"):
            if src_path.is_dir():
                continue

            # Calcular ruta relativa y destino
            rel = src_path.relative_to(src)
            dst_path = dest / rel

            # Crear subcarpetas si hace falta
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            # ¿Existe ya?
            if dst_path.exists() and not overwrite:
                result["skipped_count"] += 1
                continue

            try:
                shutil.copy2(src_path, dst_path)
                size = src_path.stat().st_size
                result["copied_count"] += 1
                result["bytes_copied"] += size
                log.debug(f"Copiado: {rel} ({size} bytes)")
            except Exception as e:
                result["failed_count"] += 1
                result["errors"].append(f"{rel}: {e}")
                log.warning(f"Error copiando {rel}: {e}")
    except Exception as e:
        result["failed_count"] += 1
        result["errors"].append(f"_copy_tree_sync: {e}")
        log.exception(f"Error fatal en copia de publicidad: {e}")


async def copy_single_file(src: str, dest_dir: str, filename: str | None = None) -> bool:
    """
    Copia un solo archivo al destino. Útil para recibos, plantillas, etc.

    Se ejecuta en hilo para no bloquear.
    """
    src_path = Path(src)
    if not src_path.is_file():
        log.warning(f"Archivo origen no existe: {src}")
        return False

    dest_path = Path(dest_dir) / (filename or src_path.name)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        await asyncio.to_thread(shutil.copy2, src_path, dest_path)
        log.debug(f"Archivo copiado: {src_path.name} → {dest_path}")
        return True
    except Exception as e:
        log.warning(f"Error copiando {src_path}: {e}")
        return False


def get_publicity_stats(source_folder: str) -> dict:
    """
    Devuelve estadísticas de la carpeta de publicidad sin copiar nada.
    Útil para previsualizar qué se copiaría.
    """
    src = Path(source_folder)
    if not src.is_dir():
        return {"file_count": 0, "total_bytes": 0, "valid": False}

    total_bytes = 0
    file_count = 0
    for p in src.rglob("*"):
        if p.is_file():
            file_count += 1
            try:
                total_bytes += p.stat().st_size
            except OSError:
                pass

    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "valid": True,
    }
