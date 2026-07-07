r"""
Monitor de inserción/extracción de memorias USB (mass-storage).

Usa WMI `Win32_DeviceChangeEvent` para detectar cambios en dispositivos,
luego consulta qué drives removibles hay actualmente.

CRÍTICO: Este monitor SOLO detecta USB mass-storage (las que aparecen con
letra de unidad E:\, F:\, etc.). Para dispositivos MTP (teléfono Android,
cámaras) ver `mtp_monitor.py`.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Awaitable, Callable

from lbamonitor.monitor.wmi_utils import (
    USBDeviceInfo,
    get_usb_info,
    is_windows,
    list_removable_drives,
)
from lbamonitor.utils.helpers import utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


# Tipo del callback: (info: USBDeviceInfo) -> None | Awaitable[None]
USBEventCallback = Callable[[USBDeviceInfo], "object"] | Callable[[USBDeviceInfo], Awaitable[None]]


class USBMonitor:
    """
    Detecta inserción/extracción de memorias USB.

    En Windows: usa WMI `Win32_DeviceChangeEvent.watch_for()` en un hilo.
    En no-Windows: hace polling cada N segundos (para tests).

    Callbacks:
      - on_inserted(USBDeviceInfo): cuando se detecta una nueva USB
      - on_removed(drive_letter: str): cuando se extrae una USB
    """

    def __init__(
        self,
        on_inserted: USBEventCallback | None = None,
        on_removed: Callable[[str], "object"] | None = None,
        poll_interval_seconds: int = 2,
    ) -> None:
        self._on_inserted = on_inserted
        self._on_removed = on_removed
        self._poll_interval = poll_interval_seconds
        self._known_drives: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False

    def _initial_scan(self) -> None:
        """Escaneo inicial: marca todas las USBs actuales como conocidas."""
        drives = list_removable_drives()
        self._known_drives = set(drives)
        log.info(f"Escaneo inicial: {len(drives)} USB(s) conectadas: {drives}")

    def _scan(self) -> None:
        """Un ciclo de escaneo: detecta inserciones y extracciones."""
        try:
            current = set(list_removable_drives())

            # Detectar inserciones
            inserted = current - self._known_drives
            for drive in inserted:
                log.info(f"USB insertada: {drive}")
                self._fire_inserted(drive)

            # Detectar extracciones
            removed = self._known_drives - current
            for drive in removed:
                log.info(f"USB extraída: {drive}")
                self._fire_removed(drive)

            self._known_drives = current
        except Exception as e:
            log.exception(f"Error en escaneo USB: {e}")

    def _fire_inserted(self, drive_letter: str) -> None:
        """Obtiene info de la USB y dispara callback."""
        # Pequeña espera para que Windows asigne la letra y WMI tenga datos
        time.sleep(0.5)

        info = get_usb_info(drive_letter)
        if not info.fingerprint:
            log.warning(
                f"No se pudo obtener fingerprint de {drive_letter} "
                f"(USB sin serial ni device_id)"
            )

        if self._on_inserted and self._loop:
            try:
                result = self._on_inserted(info)
                if asyncio.iscoroutine(result):
                    asyncio.run_coroutine_threadsafe(result, self._loop)
            except Exception as e:
                log.exception(f"Error en callback on_inserted: {e}")

    def _fire_removed(self, drive_letter: str) -> None:
        if self._on_removed and self._loop:
            try:
                result = self._on_removed(drive_letter)
                if asyncio.iscoroutine(result):
                    asyncio.run_coroutine_threadsafe(result, self._loop)
            except Exception as e:
                log.exception(f"Error en callback on_removed: {e}")

    def _run_wmi_watcher(self) -> None:
        """
        Hilo que escucha eventos WMI Win32_DeviceChangeEvent.
        En cada evento, dispara un _scan().
        """
        if not is_windows():
            # Fallback: polling
            self._run_polling()
            return

        try:
            import wmi  # type: ignore
            import pythoncom  # type: ignore

            pythoncom.CoInitialize()
            c = wmi.WMI()

            log.info("USBMonitor: escuchando WMI Win32_DeviceChangeEvent")

            # watch_for bloquea el hilo hasta el primer evento
            while not self._stop_event.is_set():
                try:
                    # Timeout de 5s para poder comprobar el stop_event
                    watcher = c.Win32_DeviceChangeEvent.watch_for(
                        notification_type="Creation",
                        timeout_ms=self._poll_interval * 1000,
                    )
                    # Si llegó aquí, hubo evento (o timeout)
                    self._scan()
                except wmi.x_wmi_timed_out:
                    # Timeout normal, seguir esperando
                    continue
                except Exception as e:
                    if self._stop_event.is_set():
                        break
                    log.warning(f"Error en WMI watcher: {e}")
                    time.sleep(1)

        except ImportError:
            log.warning("WMI no disponible, usando polling como fallback")
            self._run_polling()
        except Exception as e:
            log.exception(f"Error fatal en WMI watcher: {e}")
            self._run_polling()

    def _run_polling(self) -> None:
        """Fallback: polling cada N segundos."""
        log.info(f"USBMonitor: polling cada {self._poll_interval}s (fallback)")
        while not self._stop_event.is_set():
            self._scan()
            self._stop_event.wait(self._poll_interval)

    async def start(self) -> None:
        """Arranca el monitor en background."""
        if self._running:
            return
        self._loop = asyncio.get_event_loop()
        self._initial_scan()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_wmi_watcher, name="USBMonitor", daemon=True
        )
        self._thread.start()
        self._running = True
        log.info("USBMonitor arrancado")

    async def stop(self) -> None:
        """Detiene el monitor."""
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        log.info("USBMonitor detenido")
