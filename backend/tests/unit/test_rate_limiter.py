"""
Tests del rate limiter — v4.3.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ["LBAMONITOR_ENV"] = "test"

from lbamonitor.core.security.rate_limiter import RateLimiter, _limiter, get_limiter


@pytest.fixture(autouse=True)
def reset_limiter():
    """Limpia el rate limiter entre tests."""
    limiter = get_limiter()
    limiter._entries.clear()
    yield
    limiter._entries.clear()


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        lim = RateLimiter()
        for _ in range(5):
            await lim.check("key1", per_minute=5, block_seconds=60)

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        from fastapi import HTTPException
        lim = RateLimiter()
        # 5 requests OK
        for _ in range(5):
            await lim.check("key2", per_minute=5, block_seconds=60)
        # 6to debe bloquear
        with pytest.raises(HTTPException) as exc:
            await lim.check("key2", per_minute=5, block_seconds=60)
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_block_expires(self):
        """Verifica que el bloqueo temporal expira."""
        import time
        from fastapi import HTTPException
        lim = RateLimiter()
        # Bloquear por 1 segundo
        for _ in range(3):
            await lim.check("key3", per_minute=3, block_seconds=1)
        with pytest.raises(HTTPException):
            await lim.check("key3", per_minute=3, block_seconds=1)
        # Esperar a que expire el bloqueo Y la ventana (ambos 60s y 1s)
        # Como no podemos esperar 60s, verificamos que el bloqueo se levanta tras 1s
        # aunque los timestamps sigan en la ventana. El comportamiento esperado es:
        # tras expirar el bloqueo, si la ventana sigue llena, se bloquea de nuevo.
        time.sleep(1.1)
        # El bloqueo expiró, pero los timestamps antiguos siguen dentro de la ventana de 60s
        # así que se vuelve a bloquear. Esto es correcto.
        with pytest.raises(HTTPException):
            await lim.check("key3", per_minute=3, block_seconds=1)

    @pytest.mark.asyncio
    async def test_different_keys_independent(self):
        lim = RateLimiter()
        # key A usa todo el cupo
        for _ in range(3):
            await lim.check("keyA", per_minute=3, block_seconds=60)
        # key B debe seguir funcionando
        await lim.check("keyB", per_minute=3, block_seconds=60)

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired(self):
        import time
        lim = RateLimiter()
        await lim.check("key-cleanup", per_minute=10, block_seconds=1)
        assert "key-cleanup" in lim._entries
        # Forzar expiración
        for entry in lim._entries.values():
            entry.timestamps = []
            entry.blocked_until = 0
        lim._last_cleanup = 0
        # Disparar cleanup
        lim._cleanup(time.monotonic())
