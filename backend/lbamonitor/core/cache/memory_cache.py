"""
Caché en memoria LRU + TTL para LBAMonitor v4.3.

Implementación:
- OrderedDict para LRU evicción O(1)
- TTL con auto-expiración
- Thread-safe (Lock)
- Decorador `cached` para aplicar a funciones async
- Estadísticas (hits, misses, evicciones)

Uso:
    from lbamonitor.core.cache.memory_cache import cached

    @cached(ttl=60, key="catalog:list")
    async def list_catalog(...): ...
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import wraps
from typing import Any, Awaitable, Callable

from lbamonitor.core.config import get_settings
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class MemoryCache:
    """
    Caché LRU + TTL thread-safe.

    - LRU: cuando se alcanza max_entries, se elimina el menos usado
    - TTL: cada entrada tiene un tiempo de expiración
    - Auto-cleanup: cada cleanup_interval segundos, se eliminan entradas expiradas
    """
    def __init__(
        self,
        max_entries: int = 1000,
        default_ttl: int = 60,
        cleanup_interval: int = 300,
    ) -> None:
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._max_entries = max_entries
        self._default_ttl = default_ttl
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.monotonic()
        # Stats
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    async def get(self, key: str) -> Any | None:
        """Obtiene un valor de la caché. Devuelve None si no existe o expiró."""
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            # Verificar TTL
            if entry.expires_at <= time.monotonic():
                del self._entries[key]
                self._misses += 1
                return None
            # LRU: mover al final (más recientemente usado)
            self._entries.move_to_end(key)
            self._hits += 1
            return entry.value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Inserta un valor en la caché."""
        async with self._lock:
            # Si ya existe, mover al final
            if key in self._entries:
                self._entries.move_to_end(key)
            else:
                # Verificar max_entries
                while len(self._entries) >= self._max_entries:
                    self._entries.popitem(last=False)  # LRU evict
                    self._evictions += 1

            t = ttl if ttl is not None else self._default_ttl
            self._entries[key] = _CacheEntry(value=value, expires_at=time.monotonic() + t)

    async def delete(self, key: str) -> bool:
        """Elimina una entrada. Devuelve True si existía."""
        async with self._lock:
            if key in self._entries:
                del self._entries[key]
                return True
            return False

    async def invalidate_prefix(self, prefix: str) -> int:
        """Elimina todas las entradas cuya key empieza con `prefix`. Devuelve count."""
        async with self._lock:
            to_delete = [k for k in self._entries if k.startswith(prefix)]
            for k in to_delete:
                del self._entries[k]
            return len(to_delete)

    async def clear(self) -> None:
        """Vacía la caché."""
        async with self._lock:
            self._entries.clear()

    async def cleanup(self) -> int:
        """Elimina entradas expiradas. Devuelve count."""
        async with self._lock:
            now = time.monotonic()
            expired = [k for k, v in self._entries.items() if v.expires_at <= now]
            for k in expired:
                del self._entries[k]
            return len(expired)

    async def maybe_cleanup(self) -> None:
        """Ejecuta cleanup si ha pasado suficiente tiempo."""
        now = time.monotonic()
        if now - self._last_cleanup > self._cleanup_interval:
            n = await self.cleanup()
            self._last_cleanup = now
            if n:
                log.debug(f"Cache cleanup: {n} entradas expiradas eliminadas")

    async def stats(self) -> dict[str, Any]:
        """Devuelve estadísticas de la caché."""
        async with self._lock:
            return {
                "size": len(self._entries),
                "max_entries": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate": self._hits / max(1, self._hits + self._misses),
            }


# Singleton
_cache: MemoryCache | None = None


def get_cache() -> MemoryCache:
    """Devuelve la instancia singleton del caché."""
    global _cache
    if _cache is None:
        s = get_settings().cache
        _cache = MemoryCache(
            max_entries=s.max_entries,
            default_ttl=s.default_ttl,
            cleanup_interval=s.cleanup_interval,
        )
    return _cache


def cached(
    ttl: int | None = None,
    key: str | Callable[..., str] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """
    Decorator para cachear resultados de funciones async.

    Args:
        ttl: tiempo de vida en segundos. Default: settings.cache.default_ttl
        key: string o función que devuelve la key. Si es None, se genera automáticamente.

    Auto-key: usa el nombre de la función + args + kwargs (hash).

    Uso:
        @cached(ttl=60)
        async def get_statistics(): ...

        @cached(key="catalog:list")
        async def list_catalog(): ...
    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            s = get_settings().cache
            if not s.enabled:
                return await func(*args, **kwargs)

            cache = get_cache()

            # Construir key
            if key is None:
                # Auto-key: nombre de función + hash de args
                import hashlib
                args_str = f"{args!r}{kwargs!r}"
                args_hash = hashlib.md5(args_str.encode()).hexdigest()[:16]
                cache_key = f"{func.__module__}.{func.__qualname__}:{args_hash}"
            elif callable(key):
                cache_key = key(*args, **kwargs)
            else:
                cache_key = key

            # Intentar caché
            value = await cache.get(cache_key)
            if value is not None:
                return value

            # Ejecutar y cachear
            value = await func(*args, **kwargs)
            await cache.set(cache_key, value, ttl=ttl)
            return value

        return wrapper

    return decorator


async def invalidate_prefix(prefix: str) -> int:
    """Convenience: invalida todas las entradas con un prefijo."""
    return await get_cache().invalidate_prefix(prefix)
