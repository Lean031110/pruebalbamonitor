"""Endpoint de salud y diagnóstico."""
from __future__ import annotations

import os
import platform
import sys
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor import __version__
from lbamonitor.core.config import get_settings
from lbamonitor.core.db import get_db
from lbamonitor.core.models import ServiceSession, USBDevice, InsertedDrive, Copy

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Estado de salud del servidor.

    Devuelve:
      - version
      - plataforma
      - python_version
      - engine DB
      - última sesión del servicio (si existe)
      - contadores básicos
    """
    s = get_settings()

    # Última sesión del servicio
    last_session = None
    try:
        result = await db.execute(
            select(ServiceSession).order_by(ServiceSession.start_date_time.desc()).limit(1)
        )
        sess = result.scalar_one_or_none()
        if sess:
            last_session = {
                "id": sess.id,
                "start": sess.start_date_time.isoformat() if sess.start_date_time else None,
                "end": sess.end_date_time.isoformat() if sess.end_date_time else None,
                "alive": sess.alive_date_time.isoformat() if sess.alive_date_time else None,
                "is_running": sess.end_date_time is None,
            }
    except Exception:
        # BD puede no estar migrada aún
        pass

    # Contadores
    counts = {}
    try:
        for model, key in [
            (USBDevice, "usb_devices"),
            (InsertedDrive, "inserted_drives"),
            (Copy, "copies"),
        ]:
            r = await db.execute(select(func.count()).select_from(model))
            counts[key] = r.scalar() or 0
    except Exception:
        pass

    return {
        "status": "ok",
        "name": "LBAMonitor",
        "version": __version__,
        "timestamp": datetime.now().isoformat(),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "processor": platform.processor()[:100] if platform.processor() else None,
        },
        "python": sys.version.split()[0],
        "config": {
            "database_engine": s.database.engine,
            "host": s.server.host,
            "port": s.server.port,
            "docs_enabled": s.server.docs_enabled,
        },
        "service_session": last_session,
        "counts": counts,
    }


@router.get("/health/ping")
async def ping() -> dict:
    """Ping simple para keepalive."""
    return {"pong": datetime.now().isoformat()}
