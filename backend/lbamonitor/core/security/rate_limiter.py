"""
Rate limiter para LBAMonitor v4.3.

Algoritmo: sliding window con bloqueo temporal.
- Cada IP+path tiene un contador de requests en la ventana actual (60s por defecto)
- Si excede el límite, la IP se bloquea por `block_seconds`
- Thread-safe (Lock)
- Usa time.monotonic() (no afectado por cambios de reloj)

Uso:
    from lbamonitor.core.security.rate_limiter import rate_limit

    @router.post("/login")
    @rate_limit(per_minute=5, block_seconds=60)
    async def login(...):
        ...
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request, status

from lbamonitor.core.config import get_settings
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class _WindowEntry:
    """Entrada del sliding window para una IP+key."""
    timestamps: list[float] = field(default_factory=list)
    blocked_until: float = 0.0


class RateLimiter:
    """
    Rate limiter sliding window con bloqueo.

    Thread-safe para uso en multi-threading. Para async, se usa un Lock
    (es breve el critical section).
    """
    def __init__(self) -> None:
        self._entries: dict[str, _WindowEntry] = defaultdict(_WindowEntry)
        self._lock = asyncio.Lock()
        self._last_cleanup = time.monotonic()

    async def check(self, key: str, per_minute: int, block_seconds: int) -> None:
        """
        Verifica si la key (IP+path) puede hacer el request.

        Lanza HTTPException 429 si excede el límite.
        """
        async with self._lock:
            now = time.monotonic()

            # Cleanup periódico (cada 5 min)
            if now - self._last_cleanup > 300:
                self._cleanup(now)
                self._last_cleanup = now

            entry = self._entries[key]

            # ¿Está bloqueada?
            if entry.blocked_until > now:
                wait = int(entry.blocked_until - now)
                log.warning(f"Rate limit bloqueado para {key}. Espera {wait}s.")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Demasiadas solicitudes. Reintente en {wait} segundos.",
                    headers={"Retry-After": str(wait)},
                )

            # Sliding window: eliminar timestamps fuera de la ventana (60s)
            window_start = now - 60
            entry.timestamps = [ts for ts in entry.timestamps if ts > window_start]

            # ¿Excede el límite?
            if len(entry.timestamps) >= per_minute:
                # Bloquear
                entry.blocked_until = now + block_seconds
                log.warning(
                    f"Rate limit excedido para {key}: {len(entry.timestamps)} en 60s "
                    f"(límite: {per_minute}). Bloqueado {block_seconds}s."
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Demasiadas solicitudes. Bloqueado por {block_seconds} segundos.",
                    headers={"Retry-After": str(block_seconds)},
                )

            # Registrar este request
            entry.timestamps.append(now)

    def _cleanup(self, now: float) -> None:
        """Elimina entradas expiradas para evitar memory leak."""
        window_start = now - 60
        expired = [
            k for k, v in self._entries.items()
            if v.blocked_until < now and not any(t > window_start for t in v.timestamps)
        ]
        for k in expired:
            del self._entries[k]
        if expired:
            log.debug(f"RateLimiter cleanup: {len(expired)} entradas eliminadas")


# Singleton
_limiter = RateLimiter()


def _get_client_ip(request: Request) -> str:
    """Obtiene la IP del cliente (considerando proxies)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(
    per_minute: int | None = None,
    block_seconds: int | None = None,
    key_func: Callable[[Request], str] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """
    Decorator de rate limiting para endpoints FastAPI.

    Args:
        per_minute: límite de requests por minuto. Default: settings.rate_limit.default_per_minute
        block_seconds: segundos de bloqueo al exceder. Default: settings.rate_limit.block_seconds
        key_func: función que devuelve la key de rate limit (por defecto: IP + path)

    Uso:
        @router.post("/login")
        @rate_limit(per_minute=5)
        async def login(...): ...
    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            s = get_settings().rate_limit
            if not s.enabled:
                return await func(*args, **kwargs)

            # Encontrar el request en los argumentos
            request: Request | None = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is not None:
                pm = per_minute if per_minute is not None else s.default_per_minute
                bs = block_seconds if block_seconds is not None else s.block_seconds
                if key_func is not None:
                    key = key_func(request)
                else:
                    key = f"{_get_client_ip(request)}:{request.url.path}"

                await _limiter.check(key, pm, bs)

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def get_limiter() -> RateLimiter:
    """Devuelve la instancia singleton del rate limiter (para tests)."""
    return _limiter
