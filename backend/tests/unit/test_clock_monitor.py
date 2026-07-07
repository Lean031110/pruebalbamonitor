"""Tests del monitor de cambios de reloj."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from lbamonitor.monitor.clock_monitor import ClockMonitor
from lbamonitor.utils.helpers import utcnow


@pytest.mark.asyncio
async def test_no_change_on_normal_tick() -> None:
    """Un tick normal (sin cambio de reloj) no dispara callback."""
    changes = []
    monitor = ClockMonitor(threshold_seconds=60, interval_seconds=1)
    monitor.set_on_change_callback(lambda m, n: changes.append((m, n)))
    monitor.initialize()

    # Esperar un tick corto
    await asyncio.sleep(0.05)
    # Forzar un tick manual con tiempo cercano
    monitor._last_check = utcnow()
    await monitor._tick()

    assert len(changes) == 0


@pytest.mark.asyncio
async def test_detects_forward_clock_change() -> None:
    """Un salto hacia adelante de 5 minutos se detecta."""
    changes = []
    monitor = ClockMonitor(threshold_seconds=60, interval_seconds=1)

    async def callback(moment, new_time):
        changes.append((moment, new_time))

    monitor.set_on_change_callback(callback)
    # Simular que el último check fue hace 5 minutos (salto grande)
    monitor._last_check = utcnow() - timedelta(minutes=5)
    await monitor._tick()

    assert len(changes) == 1
    moment, new_time = changes[0]
    assert (new_time - moment).total_seconds() > 60


@pytest.mark.asyncio
async def test_detects_backward_clock_change() -> None:
    """Un salto hacia atrás (rewind) también se detecta."""
    changes = []
    monitor = ClockMonitor(threshold_seconds=60, interval_seconds=1)

    async def callback(moment, new_time):
        changes.append((moment, new_time))

    monitor.set_on_change_callback(callback)
    # Simular que el último check fue en el futuro (alguien retrocedió el reloj)
    monitor._last_check = utcnow() + timedelta(minutes=5)
    await monitor._tick()

    assert len(changes) == 1


@pytest.mark.asyncio
async def test_threshold_respected() -> None:
    """Saltos menores al threshold no disparan."""
    changes = []
    monitor = ClockMonitor(threshold_seconds=60, interval_seconds=1)
    monitor.set_on_change_callback(lambda m, n: changes.append((m, n)))

    # Salto de 30s (menor al threshold de 60s)
    monitor._last_check = utcnow() - timedelta(seconds=30)
    await monitor._tick()

    assert len(changes) == 0


def test_check_now_sync() -> None:
    """check_now devuelve tupla (is_significant, delta)."""
    monitor = ClockMonitor(threshold_seconds=60, interval_seconds=1)
    monitor._last_check = utcnow() - timedelta(hours=2)

    is_sig, delta = monitor.check_now()
    assert is_sig is True
    assert delta > 60  # Más de 60 segundos de delta


@pytest.mark.asyncio
async def test_start_stop_lifecycle() -> None:
    """Arrancar y parar el monitor funciona sin errores."""
    monitor = ClockMonitor(threshold_seconds=60, interval_seconds=1)
    monitor.initialize()

    await monitor.start()
    assert monitor._running is True

    await asyncio.sleep(0.1)  # Dejar que corra un poco

    await monitor.stop()
    assert monitor._running is False
