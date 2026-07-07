"""Utilidades de logging basadas en loguru."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from loguru import logger

from lbamonitor.core.config import get_settings


def setup_logging() -> None:
    """
    Configura loguru con consola + archivo rotativo (por tiempo Y por tamaño).

    Rotación:
      - Diaria (1 día) → hasta 30 días
      - Por tamaño (10 MB por archivo) → hasta 5 archivos
    Esto evita que logs masivos (p. ej. copia de 1M archivos) llenen el disco.
    """
    s = get_settings().logging

    # Remover handler por defecto
    logger.remove()

    # Consola
    if s.console:
        logger.add(
            sys.stderr,
            level=s.level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <7}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

    # Archivo rotativo por tiempo (diario)
    log_path = Path(s.path)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_path / "lbamonitor.log",
        level=s.level,
        rotation=s.rotation,  # "1 day"
        retention=s.retention,  # "30 days"
        compression="zip",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name}:{function}:{line} | {message}"
        ),
        backtrace=True,
        diagnose=False,  # No exponer variables en producción
        enqueue=True,  # Thread-safe
    )

    # Archivo rotativo por tamaño (10 MB, máx 5 archivos = 50 MB cap)
    logger.add(
        log_path / "lbamonitor-size.log",
        level=s.level,
        rotation="10 MB",
        retention=5,  # 5 archivos de 10 MB = 50 MB máx
        compression="zip",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name}:{function}:{line} | {message}"
        ),
        backtrace=True,
        diagnose=False,
        enqueue=True,
    )

    # Errores a archivo separado (rotación por tamaño, más pequeño)
    logger.add(
        log_path / "lbamonitor-errors.log",
        level="ERROR",
        rotation="2 MB",
        retention=10,  # 10 archivos de 2 MB = 20 MB máx
        compression="zip",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name}:{function}:{line} | {message}"
        ),
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )

    # Silenciar ruido
    logger.disable("sqlalchemy.engine")
    logger.disable("aiosqlite")
    logger.disable("watchdog.observers")
    logger.disable("urllib3")

    logger.info(f"Logging configurado — level={s.level}, path={log_path}")


def get_logger(name: str | None = None) -> Any:
    """Devuelve un logger con el nombre dado (compat con estándar logging)."""
    return logger.bind(name=name or "lbamonitor")
