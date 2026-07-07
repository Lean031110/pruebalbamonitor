"""
Punto de entrada del servicio de monitoreo (lbamonitor-svc).

En Windows corre como servicio Windows (NSSM) o en primer plano.
En otros sistemas solo hace logging (no hay monitoreo USB fuera de Windows).

Arranque:
  1. Setup logging
  2. Inicializar engine BD
  3. Ejecutar migraciones Alembic (CRÍTICO para upgrades)
  4. Arrancar MonitorService (USB + MTP + Clock + Heartbeat)
  5. Arrancar API FastAPI (puerto 8123)
  6. Esperar señal de parada
  7. Cierre ordenado
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
from typing import Any

from lbamonitor import __version__


async def _run_async() -> None:
    """Loop principal del servicio."""
    from lbamonitor.utils.logging_setup import get_logger, setup_logging

    setup_logging()
    log = get_logger("lbamonitor-svc")
    log.info(f"LBAMonitor SVC v{__version__} arrancando...")

    if os.name != "nt":
        log.warning(
            "Monitor USB no soportado en plataformas no-Windows. "
            "El servicio quedará en modo API-only (sin detección de USBs)."
        )

    # 1. Inicializar BD
    from lbamonitor.core.db import init_engine, dispose_engine
    await init_engine()
    log.info("Base de datos inicializada")

    # 2. Ejecutar migraciones Alembic automáticamente (CRÍTICO para upgrades)
    from lbamonitor.core.migrations import run_migrations
    mig_ok = await asyncio.to_thread(run_migrations)
    if not mig_ok:
        log.warning("Migraciones fallaron — continuando de todas formas")

    # 3. Arrancar servicio de monitoreo
    from lbamonitor.monitor.service import start_monitor_service, stop_monitor_service
    monitor = await start_monitor_service()
    log.info(f"MonitorService status: {monitor.get_status()}")

    # 4. Arrancar API FastAPI en el mismo proceso
    # (uvicorn programáticamente, sin bloquear el event loop)
    import uvicorn
    from lbamonitor.api.main import app
    from lbamonitor.core.config import get_settings

    s = get_settings()
    config = uvicorn.Config(
        app,
        host=s.server.host,
        port=s.server.port,
        log_config=None,  # Usar loguru
        access_log=False,  # Reducir ruido
    )
    server = uvicorn.Server(config)

    # 5. Esperar señal de parada
    stop_event = asyncio.Event()

    def _stop(*_: Any) -> None:
        log.info("Señal de parada recibida")
        stop_event.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _stop)
            except (NotImplementedError, RuntimeError):
                # Windows no soporta add_signal_handler
                signal.signal(sig, lambda *_: stop_event.set())
    except RuntimeError:
        pass

    log.info(
        f"LBAMonitor SVC corriendo. API en http://{s.server.host}:{s.server.port}. "
        f"Presiona Ctrl+C para parar."
    )

    # Arrancar uvicorn en background y esperar stop_event
    server_task = asyncio.create_task(server.serve())
    stop_wait_task = asyncio.create_task(stop_event.wait())

    # Esperar cualquiera de los dos
    done, pending = await asyncio.wait(
        {server_task, stop_wait_task}, return_when=asyncio.FIRST_COMPLETED
    )

    # 6. Cierre ordenado
    log.info("LBAMonitor SVC deteniéndose...")
    if not server_task.done():
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=10)
        except asyncio.TimeoutError:
            log.warning("Timeout cerrando uvicorn")
    stop_wait_task.cancel()

    await stop_monitor_service()
    await dispose_engine()
    log.info("LBAMonitor SVC detenido ✓")


def main() -> int:
    """Entry point para `lbamonitor-svc` o `python -m lbamonitor.monitor`."""
    try:
        asyncio.run(_run_async())
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error fatal: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
