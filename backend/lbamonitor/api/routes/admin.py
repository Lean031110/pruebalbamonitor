"""
Router de administración: control del servicio (start/stop), estado del monitor,
lectura de logs.

Estos endpoints son usados por la app desktop admin para gestionar el servicio.
Solo deberían ser accesibles desde localhost.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from lbamonitor.api.schemas.common import MessageResponse
from lbamonitor.api.schemas.settings import LogLine, LogsResponse
from lbamonitor.core.config import get_settings
from lbamonitor.core.models import User
from lbamonitor.core.security.auth import require_admin
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/status", response_model=dict)
async def get_service_status(
    current_user: User = Depends(require_admin),
):
    """Devuelve el estado del MonitorService."""
    from lbamonitor.monitor.service import get_monitor_service
    svc = get_monitor_service()
    if not svc:
        return {
            "running": False,
            "message": "MonitorService no inicializado",
        }
    return svc.get_status()


@router.post("/service/stop", response_model=MessageResponse)
async def stop_service(
    current_user: User = Depends(require_admin),
):
    """
    Detiene el servicio de monitoreo (NO la API).

    Esto detiene la detección de USBs/MTP pero la API sigue respondiendo.
    Útil para maintenance.
    """
    from lbamonitor.monitor.service import get_monitor_service, stop_monitor_service
    svc = get_monitor_service()
    if not svc:
        raise HTTPException(404, detail="Servicio no está corriendo")
    await stop_monitor_service()
    return MessageResponse(message="Servicio de monitoreo detenido")


@router.post("/service/start", response_model=MessageResponse)
async def start_service(
    current_user: User = Depends(require_admin),
):
    """Arranca el servicio de monitoreo (si estaba detenido)."""
    from lbamonitor.monitor.service import get_monitor_service, start_monitor_service
    svc = get_monitor_service()
    if svc and svc._running:
        raise HTTPException(400, detail="Servicio ya está corriendo")
    await start_monitor_service()
    return MessageResponse(message="Servicio de monitoreo arrancado")


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

# Niveles ordenados de menor a mayor severidad (para filtrado por >= level)
_LEVEL_ORDER = {"TRACE": 0, "DEBUG": 1, "INFO": 2, "SUCCESS": 2, "WARNING": 3, "ERROR": 4, "CRITICAL": 5}
_VALID_LEVELS = set(_LEVEL_ORDER.keys())


def _parse_log_line(line: str) -> Optional[LogLine]:
    """Parsea una línea de log de loguru en formato:
    ``YYYY-MM-DD HH:mm:ss | LEVEL  | module:function:line | message``
    Devuelve None si no se pudo parsear.
    """
    line = line.rstrip("\n")
    if not line:
        return None
    # Formato: "2024-01-01 12:34:56 | INFO    | module:func:12 | mensaje"
    parts = line.split(" | ", 3)
    if len(parts) < 4:
        # Línea de continuación o sin formato esperado
        return None
    timestamp, level_raw, module, message = parts[0], parts[1].strip(), parts[2], parts[3]
    return LogLine(timestamp=timestamp, level=level_raw, module=module, message=message)


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    level: str = Query("INFO", description="Nivel mínimo: TRACE|DEBUG|INFO|WARNING|ERROR|CRITICAL"),
    limit: int = Query(100, ge=1, le=2000, description="Cantidad máxima de líneas a devolver"),
    search: Optional[str] = Query(None, description="Substring a buscar (case-insensitive)"),
    file: str = Query("lbamonitor.log", description="Nombre del archivo de log a leer"),
    current_user: User = Depends(require_admin),
):
    """Lee los logs recientes del archivo de log configurado en ``settings.logging.path``.

    Filtros:
      - ``level``: nivel mínimo (incluye niveles superiores).
      - ``search``: substring case-insensitive en cualquier campo.
      - ``limit``: número máximo de líneas devueltas (se leen las últimas N del archivo).
      - ``file``: nombre del archivo dentro de ``settings.logging.path``
        (default: ``lbamonitor.log``).
    """
    level_upper = (level or "INFO").upper()
    if level_upper not in _VALID_LEVELS:
        raise HTTPException(400, detail=f"level inválido. Válidos: {sorted(_VALID_LEVELS)}")
    min_level = _LEVEL_ORDER[level_upper]

    s = get_settings().logging
    log_dir = Path(s.path)
    log_file = log_dir / file

    if not log_file.is_file():
        # Si no existe el archivo, devolver lista vacía en lugar de error
        return LogsResponse(
            file=str(log_file),
            level=level_upper,
            search=search,
            total=0,
            limit=limit,
            items=[],
        )

    # Leer las últimas líneas del archivo. Estrategia: leer en bloques desde el final
    # para no cargar archivos grandes en memoria.
    items: list[LogLine] = []
    try:
        with log_file.open("r", encoding="utf-8", errors="replace") as fh:
            # Para simplicidad y robustez: leer todas las líneas y quedarnos con las últimas.
            # Si el archivo fuera muy grande, se podría optimizar con seek desde el final.
            all_lines = fh.readlines()
    except OSError as e:
        log.warning(f"No se pudo leer {log_file}: {e}")
        return LogsResponse(
            file=str(log_file),
            level=level_upper,
            search=search,
            total=0,
            limit=limit,
            items=[],
        )

    # Filtrar y parsear
    search_lower = search.lower() if search else None
    for raw in reversed(all_lines):
        parsed = _parse_log_line(raw)
        if parsed is None:
            continue
        # Filtro por nivel mínimo
        parsed_level = _LEVEL_ORDER.get(parsed.level.upper(), 2)
        if parsed_level < min_level:
            continue
        # Filtro por búsqueda
        if search_lower:
            haystack = (
                f"{parsed.timestamp} {parsed.level} {parsed.module} {parsed.message}".lower()
            )
            if search_lower not in haystack:
                continue
        items.append(parsed)
        if len(items) >= limit:
            break

    # Devolver en orden cronológico ascendente (más antiguas primero)
    items.reverse()

    return LogsResponse(
        file=str(log_file),
        level=level_upper,
        search=search,
        total=len(items),
        limit=limit,
        items=items,
    )
