"""
Monitor de cambios de reloj del PC.

Cada minuto compara la hora actual con la anterior. Si el salto es mayor a
±60 segundos, registra un PCDatetimeChange en la BD.

IMPORTANTE: Todas las comparaciones se hacen en UTC para evitar falsos
positivos por cambios de zona horaria (DST).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from lbamonitor.utils.helpers import is_clock_skew_significant, utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


class ClockMonitor:
    """
    Detecta cambios bruscos del reloj del sistema (potencial fraude).

    Algoritmo:
      1. Cada `interval_seconds` (default 60s), toma utcnow().
      2. Compara con el timestamp anterior.
      3. Si el delta > threshold (default 60s), registra PCDatetimeChange.

    Notas:
      - Comparar en UTC, no en hora local, para evitar DST false positives.
      - El primer tick no dispara (no hay anterior).
      - Si el servicio estuvo caído, al arrancar compara con el último
        AliveDateTime de la ServiceSession anterior.
    """

    def __init__(
        self,
        threshold_seconds: int = 60,
        interval_seconds: int = 60,
    ) -> None:
        self._threshold = threshold_seconds
        self._interval = interval_seconds
        self._last_check: datetime | None = None
        self._task: asyncio.Task | None = None
        self._running = False
        # Callback que se invoca con (moment_utc, new_time_utc) al detectar cambio
        self._on_change_callback = None

    def set_on_change_callback(self, callback) -> None:
        """Define el callback async para cuando se detecta un cambio."""
        self._on_change_callback = callback

    def initialize(self, last_known_time: datetime | None = None) -> None:
        """
        Inicializa el último timestamp conocido.

        Útil al arrancar el servicio: si el último heartbeat fue hace 5 min
        pero ahora la hora del sistema saltó 2 horas, detectar el cambio.
        """
        self._last_check = last_known_time or utcnow()
        log.debug(f"ClockMonitor inicializado con último timestamp: {self._last_check}")

    async def _tick(self) -> None:
        """Un tick del monitor: comparar hora actual con la anterior."""
        if self._last_check is None:
            self._last_check = utcnow()
            return

        current = utcnow()
        is_significant, delta = is_clock_skew_significant(
            self._last_check, current, self._threshold
        )

        if is_significant:
            log.warning(
                f"Cambio de reloj detectado: delta={delta}s "
                f"(antes={self._last_check.isoformat()}, ahora={current.isoformat()})"
            )
            if self._on_change_callback:
                try:
                    result = self._on_change_callback(self._last_check, current)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    log.exception(f"Error en callback de ClockMonitor: {e}")

        self._last_check = current

    async def _run(self) -> None:
        """Loop principal del monitor."""
        log.info(
            f"ClockMonitor arrancado (interval={self._interval}s, threshold={self._threshold}s)"
        )
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                log.exception(f"Error en tick de ClockMonitor: {e}")
            await asyncio.sleep(self._interval)

    async def start(self) -> None:
        """Arranca el monitor en background."""
        if self._running:
            return
        if self._last_check is None:
            self.initialize()
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Detiene el monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await asyncio.gather(self._task, return_exceptions=True)
            except Exception:
                pass
            self._task = None
        log.info("ClockMonitor detenido")

    def check_now(self) -> tuple[bool, int]:
        """
        Verificación puntual (sin esperar al próximo tick).
        Útil para tests.
        """
        if self._last_check is None:
            self._last_check = utcnow()
            return False, 0
        current = utcnow()
        return is_clock_skew_significant(self._last_check, current, self._threshold)
