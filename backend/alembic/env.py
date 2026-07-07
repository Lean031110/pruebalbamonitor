"""
Alembic env.py — configuración de migraciones para SQLAlchemy async.

Soporta SQLite y PostgreSQL, leyendo la URL de la configuración de LBAMonitor.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from lbamonitor.core.config import get_settings
from lbamonitor.core.models import Base

# Importar TODOS los modelos para que Alembic los detecte en autogenerate
import lbamonitor.core.models  # noqa: F401

# this is the Alembic Config object
config = context.config

# Interpretar config file para logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Meta target para autogenerate
target_metadata = Base.metadata


def _get_url() -> str:
    """
    Construye la URL síncrona o async según el motor configurado.

    Para Alembic async necesitamos el driver async (aiosqlite / asyncpg).
    """
    s = get_settings().database
    if s.engine == "sqlite":
        from pathlib import Path
        # Caso especial: SQLite en memoria (tests)
        if s.path == ":memory:" or s.path == "":
            return "sqlite+aiosqlite:///:memory:"
        Path(s.path).parent.mkdir(parents=True, exist_ok=True)
        path = Path(s.path).resolve()
        return f"sqlite+aiosqlite:///{path}"
    elif s.engine == "postgresql":
        return (
            f"postgresql+asyncpg://{s.user}:{s.password}@{s.host}:{s.port}/{s.path}"
        )
    raise ValueError(f"Motor no soportado: {s.engine!r}")


def run_migrations_offline() -> None:
    """
    Modo offline: genera SQL sin conectar a la BD.
    Útil para revisar qué haría una migración.
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Ejecuta migraciones sobre una conexión dada."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # SQLite no soporta ALTER bien; recomendado para desarrollo:
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Modo online con engine async (necesario para aiosqlite/asyncpg).
    """
    url = _get_url()
    config_section = config.get_section(config.config_ini_section, {})
    config_section["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Wrapper síncrono que arranca el loop async."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
