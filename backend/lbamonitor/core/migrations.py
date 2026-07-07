"""
Utilidades de migración: ejecutar `alembic upgrade head` al arrancar.

Esto se llama desde el lifespan de FastAPI y desde el entrypoint del servicio
para garantizar que el esquema de la BD está siempre actualizado.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


def run_migrations() -> bool:
    """
    Ejecuta `alembic upgrade head` para aplicar migraciones pendientes.

    Devuelve True si todo fue bien, False si hubo error.

    Se ejecuta:
      - Al arrancar la API (lifespan de FastAPI)
      - Al arrancar el servicio de monitoreo (lbamonitor-svc)
      - Manualmente vía `lbamonitor-cli init-db` (modo desarrollo)
    """
    # Buscar alembic.ini en el backend/
    backend_dir = Path(__file__).resolve().parent.parent.parent
    alembic_ini = backend_dir / "alembic.ini"

    if not alembic_ini.is_file():
        log.warning(f"No se encontró {alembic_ini} — saltando migraciones")
        return False

    log.info("Ejecutando migraciones Alembic (alembic upgrade head)...")

    try:
        # Usar el mismo intérprete Python
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(alembic_ini), "upgrade", "head"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode == 0:
            # Filtrar output: alembic puede ser verboso
            for line in result.stdout.splitlines():
                if line.strip() and "INFO" not in line:
                    log.debug(f"alembic: {line}")
            log.info("Migraciones aplicadas correctamente ✓")
            return True
        else:
            log.error(f"alembic upgrade head falló (exit {result.returncode})")
            log.error(f"stdout: {result.stdout[-500:] if result.stdout else ''}")
            log.error(f"stderr: {result.stderr[-500:] if result.stderr else ''}")
            return False
    except subprocess.TimeoutExpired:
        log.error("Timeout ejecutando alembic upgrade head (120s)")
        return False
    except FileNotFoundError:
        log.error("No se encontró el comando alembic. ¿Está instalado?")
        return False
    except Exception as e:
        log.exception(f"Error inesperado ejecutando migraciones: {e}")
        return False
