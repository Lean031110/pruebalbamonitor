"""Tests de la API: health check."""
from __future__ import annotations

import os
import pytest
from httpx import ASGITransport, AsyncClient

from lbamonitor.api.main import create_app


@pytest.fixture
def app():
    """Crea la app sin disparar el lifespan (que requeriría BD real)."""
    return create_app()


@pytest.fixture
async def initialized_db():
    """Inicializa BD y aplica migraciones Alembic (definida por conftest)."""
    from lbamonitor.core.db import dispose_engine, init_engine
    from lbamonitor.core.migrations import run_migrations

    # Limpiar BD previa
    from pathlib import Path
    test_db = Path(os.environ["LBAMONITOR_DATABASE__PATH"])
    if test_db.exists():
        test_db.unlink()

    run_migrations()
    await init_engine()
    yield
    await dispose_engine()


@pytest.mark.asyncio
async def test_health_endpoint(app, initialized_db) -> None:
    """GET /api/health devuelve JSON con status ok (BD debe estar inicializada)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["name"] == "LBAMonitor"
    assert "version" in data
    assert "platform" in data
    assert "config" in data


@pytest.mark.asyncio
async def test_health_endpoint_with_db(app, initialized_db) -> None:
    """GET /api/health con BD inicializada devuelve counts."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "counts" in data
    # La BD está vacía, todos los counts deben ser 0
    counts = data["counts"]
    assert counts.get("usb_devices", 0) == 0
    assert counts.get("inserted_drives", 0) == 0


@pytest.mark.asyncio
async def test_ping_endpoint(app) -> None:
    """GET /api/health/ping devuelve pong."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/health/ping")
    assert r.status_code == 200
    data = r.json()
    assert "pong" in data


@pytest.mark.asyncio
async def test_root_endpoint(app) -> None:
    """GET / devuelve el index.html del frontend (si dist existe) o info básica."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        # Si hay frontend dist montado, devuelve HTML; si no, devuelve JSON
        content_type = r.headers.get("content-type", "")
        if "json" in content_type:
            data = r.json()
            assert data["name"] == "LBAMonitor"
        else:
            # HTML del frontend
            assert "LBAMonitor" in r.text or "<div id=\"root\"" in r.text
