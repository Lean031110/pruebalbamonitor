"""
Tests del caché LRU+TTL — v4.3.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ["LBAMONITOR_ENV"] = "test"

from lbamonitor.core.cache.memory_cache import MemoryCache


@pytest.fixture
def cache():
    return MemoryCache(max_entries=5, default_ttl=60, cleanup_interval=0)


class TestMemoryCache:
    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        await cache.set("k1", "v1")
        assert await cache.get("k1") == "v1"

    @pytest.mark.asyncio
    async def test_get_missing(self, cache):
        assert await cache.get("missing") is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, cache):
        c = MemoryCache(max_entries=5, default_ttl=1)
        await c.set("k1", "v1", ttl=1)
        assert await c.get("k1") == "v1"
        time.sleep(1.1)
        assert await c.get("k1") is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self, cache):
        # Llenar el caché
        for i in range(5):
            await cache.set(f"k{i}", f"v{i}")
        # Acceder a k0 para marcarlo como recientemente usado
        await cache.get("k0")
        # Añadir uno más, debe eviccinar k1 (LRU)
        await cache.set("k5", "v5")
        assert await cache.get("k0") == "v0"  # sigue (fue accedido)
        assert await cache.get("k1") is None  # eviccionado
        assert await cache.get("k5") == "v5"

    @pytest.mark.asyncio
    async def test_delete(self, cache):
        await cache.set("k1", "v1")
        assert await cache.delete("k1") is True
        assert await cache.get("k1") is None
        assert await cache.delete("k1") is False

    @pytest.mark.asyncio
    async def test_invalidate_prefix(self, cache):
        await cache.set("stats:today", 1)
        await cache.set("stats:month", 2)
        await cache.set("other:key", 3)
        n = await cache.invalidate_prefix("stats:")
        assert n == 2
        assert await cache.get("stats:today") is None
        assert await cache.get("stats:month") is None
        assert await cache.get("other:key") == 3

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        await cache.set("k1", "v1")
        await cache.set("k2", "v2")
        await cache.clear()
        assert await cache.get("k1") is None
        assert await cache.get("k2") is None

    @pytest.mark.asyncio
    async def test_stats(self, cache):
        await cache.set("k1", "v1")
        await cache.get("k1")  # hit
        await cache.get("k1")  # hit
        await cache.get("missing")  # miss
        stats = await cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert 0 < stats["hit_rate"] <= 1

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, cache):
        c = MemoryCache(max_entries=5, default_ttl=1)
        await c.set("k1", "v1", ttl=1)
        await c.set("k2", "v2", ttl=10)
        time.sleep(1.1)
        n = await c.cleanup()
        assert n == 1  # k1 expirado
        assert await c.get("k2") == "v2"  # k2 sigue


class TestCachedDecorator:
    @pytest.mark.asyncio
    async def test_cached_decorator(self):
        from lbamonitor.core.cache.memory_cache import cached, get_cache
        # Limpiar caché
        cache = get_cache()
        await cache.clear()

        call_count = 0

        @cached(ttl=60, key="test:decorator")
        async def expensive_function():
            nonlocal call_count
            call_count += 1
            return {"result": "computed"}

        # Primera llamada: ejecuta
        r1 = await expensive_function()
        assert r1 == {"result": "computed"}
        assert call_count == 1

        # Segunda llamada: caché hit
        r2 = await expensive_function()
        assert r2 == {"result": "computed"}
        assert call_count == 1  # no se ejecutó de nuevo
