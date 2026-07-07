"""
Factory principal de la aplicación FastAPI.

Estructura:
  - CORS middleware
  - Exception handlers → RFC 7807 Problem Details
  - Lifespan: init engine, scheduler, monitor
  - Static files (frontend build)
  - Routers montados bajo /api
  - WebSocket /ws/events
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from lbamonitor import __version__
from lbamonitor.core.config import get_settings
from lbamonitor.core.db import dispose_engine, init_engine
from lbamonitor.utils.logging_setup import get_logger, setup_logging

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (reemplaza a @app.on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Arranque y parada ordenada de la app."""
    log.info(f"LBAMonitor API v{__version__} arrancando...")
    setup_logging()
    s = get_settings()
    log.info(f"Config cargada: engine={s.database.engine}, host={s.server.host}:{s.server.port}")

    # Inicializar BD
    await init_engine()
    log.info("Base de datos inicializada")

    # Ejecutar migraciones Alembic automáticamente (CRÍTICO para upgrades)
    from lbamonitor.core.migrations import run_migrations
    import asyncio
    mig_ok = await asyncio.to_thread(run_migrations)
    if not mig_ok:
        log.warning("Migraciones fallaron — la app puede tener comportamiento inesperado")

    # Inicializar caché
    from lbamonitor.core.cache.memory_cache import get_cache
    get_cache()
    log.info("Caché LRU+TTL inicializado")

    # Inicializar estado de licencia (trial 10 días)
    try:
        from lbamonitor.core.services.license_state import init_license_state
        from lbamonitor.core.db import get_session_factory
        init_license_state(get_session_factory())
        log.info("License state (trial 10 días) inicializado")
    except Exception as e:
        log.warning(f"License state no inicializado: {e}")

    # Inicializar plugins (con firma HMAC obligatoria)
    try:
        from lbamonitor.core.services.plugin_manager import get_plugin_manager
        pm = get_plugin_manager()
        count = pm.load_all()
        if count > 0:
            log.info(f"{count} plugin(s) cargado(s) y firmados ✓")
    except Exception as e:
        log.warning(f"Plugins no cargados: {e}")

    # Inicializar scheduler (backup nocturno + cleanup)
    try:
        from lbamonitor.core.services.scheduler import start_scheduler
        await start_scheduler()
        log.info("Scheduler iniciado (backup nocturno + cleanup)")
    except Exception as e:
        log.warning(f"Scheduler no iniciado: {e}")

    # Inicializar monitor USB (solo en Windows) — CRÍTICO para producción
    if os.name == 'nt':
        try:
            from lbamonitor.monitor.service import start_monitor
            await start_monitor()
            log.info("Monitor USB iniciado")
        except Exception as e:
            log.error(f"Monitor USB no pudo iniciarse: {e}", exc_info=True)
    else:
        log.info("Monitor USB deshabilitado (solo Windows). En Linux/Mac solo API.")

    log.info("LBAMonitor API listo ✓")
    yield

    # Shutdown
    log.info("LBAMonitor API deteniéndose...")
    if os.name == 'nt':
        try:
            from lbamonitor.monitor.service import stop_monitor
            await stop_monitor()
        except Exception:
            pass
    try:
        from lbamonitor.core.services.scheduler import stop_scheduler
        await stop_scheduler()
    except Exception:
        pass
    await dispose_engine()
    log.info("LBAMonitor API detenido ✓")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Crea y configura la app FastAPI."""
    s = get_settings()

    app = FastAPI(
        title="LBAMonitor",
        description=(
            "Servidor de monitoreo de copias a memorias USB / MTP para Windows. "
            "Reimplementación moderna de Uatcher con arquitectura API-first."
        ),
        version=__version__,
        docs_url="/docs" if s.server.docs_enabled else None,
        redoc_url="/redoc" if s.server.docs_enabled else None,
        openapi_url="/openapi.json" if s.server.docs_enabled else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth middleware (parsea JWT y setea request.state.current_user)
    from lbamonitor.api.middleware.auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)

    # Security headers
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        import time as _time
        start = _time.monotonic()
        response = await call_next(request)
        elapsed_ms = round((_time.monotonic() - start) * 1000, 2)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        return response

    # Exception handlers
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception(f"Error no manejado en {request.method} {request.url.path}: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "type": "https://lbamonitor/errors/internal",
                "title": "Internal Server Error",
                "status": 500,
                "detail": str(exc) if s.server.docs_enabled else "Error interno",
                "instance": str(request.url.path),
            },
        )

    # Routers
    from lbamonitor.api.routes.auth import router as auth_router
    from lbamonitor.api.routes.health import router as health_router
    from lbamonitor.api.routes.users import router as users_router
    from lbamonitor.api.routes.inserted_drives import router as inserted_drives_router
    from lbamonitor.api.routes.copies import router as copies_router
    from lbamonitor.api.routes.statistics import router as statistics_router
    from lbamonitor.api.routes.settings_router import router as settings_router
    from lbamonitor.api.routes.license_router import router as license_router
    from lbamonitor.api.routes.sessions import router as sessions_router
    from lbamonitor.api.routes.backups import router as backups_router
    from lbamonitor.api.routes.pc_datetime_changes import router as pc_changes_router
    from lbamonitor.api.routes.usb_devices import router as usb_devices_router
    from lbamonitor.api.routes.billings import router as billings_router
    from lbamonitor.api.routes.catalog import router as catalog_router
    from lbamonitor.api.routes.clients import router as clients_router
    from lbamonitor.api.routes.admin import router as admin_router
    from lbamonitor.api.routes.ws import router as ws_router
    # Web (HTML dashboard + catálogo público con Jinja2Templates)
    from lbamonitor.web.routes import router as web_router

    app.include_router(auth_router)  # prefix /api/auth ya en router
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(users_router, prefix="/api")
    app.include_router(inserted_drives_router, prefix="/api")
    app.include_router(copies_router, prefix="/api")
    app.include_router(statistics_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(license_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(backups_router, prefix="/api")
    app.include_router(pc_changes_router, prefix="/api")
    app.include_router(usb_devices_router, prefix="/api")
    app.include_router(billings_router, prefix="/api")
    app.include_router(catalog_router, prefix="/api")
    app.include_router(clients_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(ws_router)  # WebSocket sin prefix /api
    app.include_router(web_router)  # /web/* (HTML, Jinja2Templates)

    # Static files del web (CSS/JS del dashboard) — mount antes que el catch-all
    web_static_dir = Path(__file__).resolve().parent.parent / "web" / "static"
    if web_static_dir.is_dir():
        app.mount("/web/static", StaticFiles(directory=str(web_static_dir)), name="web-static")
        log.info(f"Web estático montado: {web_static_dir}")

    # Frontend estático (si existe dist/)
    frontend_dist = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
        log.info(f"Frontend estático montado: {frontend_dist}")
    else:
        @app.get("/")
        async def root():
            return {
                "name": "LBAMonitor",
                "version": __version__,
                "docs": "/docs" if s.server.docs_enabled else "disabled",
                "status": "running",
            }

    return app


# ---------------------------------------------------------------------------
# Módulo
# ---------------------------------------------------------------------------

app = create_app()


def run_dev() -> None:
    """Punto de entrada para desarrollo: `python -m lbamonitor.api.main` o `lbamonitor-api`."""
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "lbamonitor.api.main:app",
        host=s.server.host,
        port=s.server.port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    run_dev()
