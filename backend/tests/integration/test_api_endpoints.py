"""Tests de integración de los principales endpoints de la API."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from lbamonitor.api.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def initialized_db():
    """Inicializa BD con migraciones."""
    from pathlib import Path
    import os
    from lbamonitor.core.db import dispose_engine, init_engine
    from lbamonitor.core.migrations import run_migrations

    test_db = Path(os.environ["LBAMONITOR_DATABASE__PATH"])
    if test_db.exists():
        test_db.unlink()

    run_migrations()
    await init_engine()
    yield
    await dispose_engine()


@pytest.mark.asyncio
async def test_list_users_empty(app, initialized_db) -> None:
    """GET /api/users devuelve lista vacía inicialmente."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/users")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "pagination" in data
    assert data["items"] == []
    assert data["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_create_and_get_user(app, initialized_db) -> None:
    """POST /api/users + GET /api/users/{id}."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Crear
        r = await client.post("/api/users", json={
            "username": "admin_test",
            "password": "Secret123!",
            "role": "admin",
            "full_name": "Admin Test",
            "email": "admin@test.com",
        })
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["username"] == "admin_test"
        assert created["role"] == "admin"
        user_id = created["id"]

        # Get
        r2 = await client.get(f"/api/users/{user_id}")
        assert r2.status_code == 200
        assert r2.json()["username"] == "admin_test"


@pytest.mark.asyncio
async def test_create_user_duplicate_rejected(app, initialized_db) -> None:
    """POST /api/users con username duplicado falla con 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "username": "dup",
            "password": "x",
            "role": "operator",
        }
        r1 = await client.post("/api/users", json=payload)
        assert r1.status_code == 201
        r2 = await client.post("/api/users", json=payload)
        assert r2.status_code == 400


@pytest.mark.asyncio
async def test_inserted_drives_empty(app, initialized_db) -> None:
    """GET /api/inserted-drives devuelve lista vacía inicialmente."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/inserted-drives")
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_inserted_drives_filters(app, initialized_db) -> None:
    """GET /api/inserted-drives con filtros no falla."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/api/inserted-drives",
            params={
                "device_name": "E:",
                "is_mobile": False,
                "has_payment": True,
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_statistics_endpoints(app, initialized_db) -> None:
    """GET /api/statistics funciona con BD vacía."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/statistics")
    assert r.status_code == 200
    data = r.json()
    assert "today_kpis" in data
    assert "month_kpis" in data
    assert "year_kpis" in data
    assert "insights" in data
    assert data["today_kpis"]["transactions"] == 0


@pytest.mark.asyncio
async def test_settings_keyvalue_flow(app, initialized_db) -> None:
    """PUT + GET /api/settings/{key} funciona."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # PUT
        r = await client.put(
            "/api/settings/test_key",
            json={"value": "test_value_123"},
        )
        assert r.status_code == 200
        assert r.json()["value"] == "test_value_123"

        # GET
        r2 = await client.get("/api/settings/test_key")
        assert r2.status_code == 200
        assert r2.json()["value"] == "test_value_123"


@pytest.mark.asyncio
async def test_business_info_flow(app, initialized_db) -> None:
    """PUT + GET /api/settings/business-info."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # PUT
        r = await client.put("/api/settings/business-info", json={
            "name": "Copistería Test",
            "marketing_text": "Ofertas especiales",
            "address": "Calle Test 123",
        })
        assert r.status_code == 200

        # GET
        r2 = await client.get("/api/settings/business-info")
        assert r2.status_code == 200
        data = r2.json()
        assert data["name"] == "Copistería Test"
        assert data["address"] == "Calle Test 123"


@pytest.mark.asyncio
async def test_license_machine_id(app, initialized_db) -> None:
    """GET /api/license/machine-id devuelve un hash."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/license/machine-id")
    assert r.status_code == 200
    data = r.json()
    assert "machine_id" in data
    # Es un hash hex (puede ser vacío en Linux sin WMI)
    if data["machine_id"]:
        assert len(data["machine_id"]) == 64


@pytest.mark.asyncio
async def test_license_status(app, initialized_db) -> None:
    """GET /api/license devuelve estado trial cuando no hay licencia."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/license")
    assert r.status_code == 200
    data = r.json()
    assert "valid" in data
    assert "machine_id" in data


@pytest.mark.asyncio
async def test_catalog_crud(app, initialized_db) -> None:
    """CRUD completo de catálogo."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Crear
        r = await client.post("/api/catalog", json={
            "title": "Inception",
            "category": "movie",
            "year": 2010,
            "genre": "Sci-Fi",
            "rating": 8.8,
            "size_gb": 4.5,
        })
        assert r.status_code == 201, r.text
        entry_id = r.json()["id"]

        # Get
        r2 = await client.get(f"/api/catalog/{entry_id}")
        assert r2.status_code == 200
        assert r2.json()["title"] == "Inception"

        # Patch
        r3 = await client.patch(f"/api/catalog/{entry_id}", json={
            "rating": 9.0,
        })
        assert r3.status_code == 200
        assert r3.json()["rating"] == 9.0

        # List
        r4 = await client.get("/api/catalog")
        assert r4.status_code == 200
        assert r4.json()["pagination"]["total"] == 1

        # Delete (soft)
        r5 = await client.delete(f"/api/catalog/{entry_id}")
        assert r5.status_code == 200


@pytest.mark.asyncio
async def test_membership_levels_init(app, initialized_db) -> None:
    """GET /api/memberships/levels inicializa los 5 niveles por defecto."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/memberships/levels")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 5
    tiers = [l["tier"] for l in data]
    assert "bronce" in tiers
    assert "diamante" in tiers


@pytest.mark.asyncio
async def test_billings_calculate(app, initialized_db) -> None:
    """POST /api/billings/calculate calcula precio."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/billings/calculate", params={
            "gb_copied": 4.5,
            "files_copied": 12,
            "vip_type": "none",
            "tier_discount_percent": 0.0,
        })
    assert r.status_code == 200
    data = r.json()
    assert "suggested_price" in data
    assert "pricing_mode" in data
    assert data["base_price"] > 0


@pytest.mark.asyncio
async def test_billings_calculate_with_vip(app, initialized_db) -> None:
    """POST /api/billings/calculate con VIP FREE aplica 100% descuento."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/billings/calculate", params={
            "gb_copied": 4.5,
            "vip_type": "free",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["discount_percent"] == 100.0
    assert data["suggested_price"] == 0.0 or data["suggested_price"] == 5.0  # min_price


@pytest.mark.asyncio
async def test_admin_status(app, initialized_db) -> None:
    """GET /api/admin/status devuelve el estado del servicio."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/admin/status")
    assert r.status_code == 200
    data = r.json()
    assert "running" in data


@pytest.mark.asyncio
async def test_openapi_docs(app, initialized_db) -> None:
    """GET /openapi.json devuelve el schema OpenAPI completo."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    assert data["info"]["title"] == "LBAMonitor"
    # Verificar que hay múltiples paths
    assert len(data["paths"]) > 10
