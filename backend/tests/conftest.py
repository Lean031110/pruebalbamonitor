"""Conftest global de pytest."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

# Asegurar que backend/ esté en sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Config de tests: SQLite en archivo temporal (cada proceso tiene el suyo)
# Es importante NO usar :memory: porque SQLAlchemy async crea múltiples conexiones
# y :memory: no se comparte entre ellas.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="lbamonitor-tests-"))
_TEST_DB_PATH = _TEST_DB_DIR / "test.db"

os.environ["LBAMONITOR_DATABASE__ENGINE"] = "sqlite"
os.environ["LBAMONITOR_DATABASE__PATH"] = str(_TEST_DB_PATH)
os.environ["LBAMONITOR_DATABASE__ECHO"] = "false"
os.environ["LBAMONITOR_LOGGING__CONSOLE"] = "false"
os.environ["LBAMONITOR_LOGGING__LEVEL"] = "WARNING"


@pytest.fixture(scope="session")
def event_loop():
    """Event loop a nivel de sesión para tests async."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    """Inicializa el engine, aplica migraciones Alembic y hace cleanup al final."""
    from lbamonitor.core.config import reload_settings
    reload_settings()  # Asegura que la config de tests se aplique

    from lbamonitor.core.db import dispose_engine, init_engine

    # Eliminar BD previa si existe para empezar limpio
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()
        for suffix in ("-wal", "-shm"):
            p = Path(str(_TEST_DB_PATH) + suffix)
            if p.exists():
                p.unlink()

    # Aplicar migraciones Alembic (más realista que create_all)
    from lbamonitor.core.migrations import run_migrations
    run_migrations()

    await init_engine()
    yield
    await dispose_engine()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncIterator:
    """Sesión de BD aislada por test."""
    from lbamonitor.core.db import get_session_factory
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        await session.close()
