"""
Capa de base de datos: engine async SQLAlchemy + session factory.

Soporta SQLite (standalone, equivalente a Uatcher) y PostgreSQL (centralizado).
"""
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from lbamonitor.core.config import get_settings
from lbamonitor.core.models import Base
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Globals (lazy init)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_url() -> str:
    """Construye la URL de conexión según la config."""
    s = get_settings().database
    if s.engine == "sqlite":
        # Caso especial: SQLite en memoria (tests)
        if s.path == ":memory:" or s.path == "":
            return "sqlite+aiosqlite:///:memory:"
        # Asegurar que el directorio padre existe
        Path(s.path).parent.mkdir(parents=True, exist_ok=True)
        # URL async: aiosqlite
        path = Path(s.path).resolve()
        return f"sqlite+aiosqlite:///{path}"
    elif s.engine == "postgresql":
        return (
            f"postgresql+asyncpg://{s.user}:{s.password}@{s.host}:{s.port}/{s.path}"
        )
    else:
        raise ValueError(f"Motor de BD no soportado: {s.engine!r}")


def _engine_kwargs() -> dict[str, Any]:
    """Kwargs para create_async_engine según el motor."""
    s = get_settings().database
    kwargs: dict[str, Any] = {
        "echo": s.echo,
        "future": True,
    }
    if s.engine == "sqlite":
        # PRAGMAs para SQLite (ejecutados en cada conexión)
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["pool_pre_ping"] = True
        # PRAGMA via event listener (ver más abajo)
    elif s.engine == "postgresql":
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_pre_ping"] = True
    return kwargs


async def init_engine() -> AsyncEngine:
    """Inicializa el engine async global. Idempotente."""
    global _engine, _session_factory
    if _engine is not None:
        return _engine

    url = _build_url()
    log.info(f"Inicializando engine async: {url.split('://')[0]}")

    _engine = create_async_engine(url, **_engine_kwargs())

    # Para SQLite: aplicar PRAGMAs en cada conexión
    if get_settings().database.engine == "sqlite":
        from sqlalchemy import event

        @event.listens_for(_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA cache_size=-64000")  # 64 MB
            cursor.close()
            log.debug("SQLite PRAGMAs aplicados (WAL, FK, cache 64MB)")

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    log.info("Engine inicializado correctamente")
    return _engine


async def dispose_engine() -> None:
    """Cierra el engine y libera recursos."""
    global _engine, _session_factory
    if _engine is not None:
        log.info("Cerrando engine...")
        await _engine.dispose()
        _engine = None
        _session_factory = None


def get_engine() -> AsyncEngine:
    """Devuelve el engine async (debe estar inicializado)."""
    if _engine is None:
        raise RuntimeError("Engine no inicializado. Llama a init_engine() primero.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Devuelve la factory de sesiones async."""
    if _session_factory is None:
        raise RuntimeError("Session factory no inicializada.")
    return _session_factory


# ---------------------------------------------------------------------------
# Sesión async (FastAPI dependency + context manager)
# ---------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """
    Context manager transaccional: hace commit si todo va bien, rollback si hay excepción.

    Uso:
        async with session_scope() as session:
            session.add(obj)
            # Al salir del with: commit automático
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db() -> AsyncIterator[AsyncSession]:
    """
    Dependency de FastAPI: provee una sesión async por request.

    Uso en rutas:
        @router.get("/")
        async def index(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Creación del schema (para init y tests)
# ---------------------------------------------------------------------------

async def create_all_tables() -> None:
    """Crea todas las tablas. Solo para desarrollo y tests; en producción usar Alembic."""
    engine = await init_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("Tablas creadas (create_all)")


async def drop_all_tables() -> None:
    """Elimina todas las tablas. ¡PELIGROSO! Solo para tests."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    log.warning("Tablas eliminadas (drop_all)")
