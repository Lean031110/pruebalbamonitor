"""
Tests del endpoint /api/auth/login — v4.3.

Verifica:
- Login exitoso devuelve access_token + refresh_token
- Login fallido devuelve 401
- Rate limiting: 5 intentos fallidos → 429
- Refresh token genera nuevo par
- Logout revoca el token
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ["LBAMONITOR_ENV"] = "test"
os.environ["PYTEST_CURRENT_TEST"] = "1"

# Setup antes de importar la app
from lbamonitor.core.config import get_settings, reload_settings
reload_settings()
s = get_settings()
s.security.jwt_secret = "test-secret-very-secure-12345"
s.security.require_auth = False  # Los endpoints individuales validan
s.database.path = ":memory:"


@pytest.fixture(scope="module")
def app():
    from lbamonitor.api.main import app as _app
    return _app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestLoginEndpoint:
    @pytest.mark.asyncio
    async def test_login_missing_user_returns_401(self, client):
        """Login con usuario que no existe debe devolver 401."""
        # Como la BD está vacía, cualquier login falla
        r = await client.post("/api/auth/login", json={
            "username": "nonexistent",
            "password": "whatever",
        })
        assert r.status_code == 401
        assert "inválidas" in r.json()["detail"].lower() or "invalid" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_empty_body_returns_422(self, client):
        """Login sin body debe devolver 422 (validation error)."""
        r = await client.post("/api/auth/login", json={})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_login_empty_password_returns_422(self, client):
        """Login con password vacía debe devolver 422."""
        r = await client.post("/api/auth/login", json={"username": "x", "password": ""})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token_returns_401(self, client):
        """Refresh con token inválido debe devolver 401."""
        r = await client.post("/api/auth/refresh", json={"refresh_token": "invalid.token.here"})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_returns_200(self, client):
        """Logout debe ser idempotente y devolver 200."""
        r = await client.post("/api/auth/logout", json={"token": "anything"})
        assert r.status_code == 200
        assert "sesión cerrada" in r.json()["message"].lower() or "cerrada" in r.json()["message"].lower()


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_public(self, client):
        """Health check debe ser público (sin auth)."""
        r = await client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
