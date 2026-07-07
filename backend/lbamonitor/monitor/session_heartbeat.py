"""
Heartbeat de la sesión del servicio.

Crea una ServiceSession al arrancar, actualiza AliveDateTime cada N minutos,
y al detenerse cierra con EndDateTime y SessionTime.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.models import ServiceSession
from lbamonitor.utils.helpers import utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


class SessionHeartbeat:
    """
    Mantiene viva la ServiceSession del servicio.

    Ciclo de vida:
      1. start(): crea ServiceSession con StartDateTime=utcnow()
      2. Cada `interval_seconds` (default 300 = 5min): actualiza AliveDateTime
      3. stop(): actualiza EndDateTime=utcnow() y calcula SessionTime

    El ID de la sesión se guarda para que otros componentes puedan referenciarla.
    """

    def __init__(self, session_factory, interval_seconds: int = 300) -> None:
        """
        Args:
            session_factory: async_sessionmaker para obtener sesiones de BD.
            interval_seconds: cada cuánto actualizar AliveDateTime.
        """
        self._factory = session_factory
        self._interval = interval_seconds
        self._session_id: int | None = None
        self._start_time: datetime | None = None
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def session_id(self) -> int | None:
        return self._session_id

    @property
    def start_time(self) -> datetime | None:
        return self._start_time

    async def start(self) -> int | None:
        """Crea la ServiceSession en BD y arranca el heartbeat."""
        if self._running:
            return self._session_id

        self._start_time = utcnow()
        try:
            async with self._factory() as session:
                sess = ServiceSession(
                    start_date_time=self._start_time,
                    alive_date_time=self._start_time,
                )
                session.add(sess)
                await session.commit()
                await session.refresh(sess)
                self._session_id = sess.id
                log.info(f"ServiceSession #{self._session_id} iniciada a las {self._start_time}")
        except Exception as e:
            log.exception(f"Error creando ServiceSession: {e}")
            return None

        self._running = True
        self._task = asyncio.create_task(self._run())
        return self._session_id

    async def _run(self) -> None:
        """Loop de heartbeat."""
        log.info(f"Heartbeat arrancado (cada {self._interval}s)")
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                if not self._running:
                    break
                await self._beat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception(f"Error en heartbeat: {e}")
                await asyncio.sleep(self._interval)

    async def _beat(self) -> None:
        """Actualiza AliveDateTime en la BD."""
        if not self._session_id:
            return
        now = utcnow()
        try:
            async with self._factory() as session:
                await session.execute(
                    update(ServiceSession)
                    .where(ServiceSession.id == self._session_id)
                    .values(alive_date_time=now)
                )
                await session.commit()
                log.debug(f"Heartbeat OK a las {now}")
        except Exception as e:
            log.warning(f"Error en heartbeat (no crítico): {e}")

    async def stop(self) -> None:
        """Cierra la ServiceSession con EndDateTime y SessionTime."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await asyncio.gather(self._task, return_exceptions=True)
            except Exception:
                pass
            self._task = None

        if not self._session_id or not self._start_time:
            return

        end_time = utcnow()
        session_time = int((end_time - self._start_time).total_seconds())

        try:
            async with self._factory() as session:
                await session.execute(
                    update(ServiceSession)
                    .where(ServiceSession.id == self._session_id)
                    .values(
                        end_date_time=end_time,
                        alive_date_time=end_time,
                        session_time=session_time,
                    )
                )
                await session.commit()
                log.info(
                    f"ServiceSession #{self._session_id} cerrada "
                    f"(duración: {session_time}s)"
                )
        except Exception as e:
            log.exception(f"Error cerrando ServiceSession: {e}")

        self._session_id = None
        self._start_time = None

    async def get_last_alive(self) -> datetime | None:
        """
        Devuelve el último AliveDateTime de la sesión más reciente que NO sea
        la actual (para detectar cambios de reloj al arrancar).
        """
        try:
            async with self._factory() as session:
                result = await session.execute(
                    select(ServiceSession)
                    .where(ServiceSession.end_date_time.isnot(None))
                    .order_by(ServiceSession.start_date_time.desc())
                    .limit(1)
                )
                sess = result.scalar_one_or_none()
                if sess:
                    return sess.alive_date_time or sess.end_date_time
        except Exception as e:
            log.warning(f"Error obteniendo último heartbeat: {e}")
        return None
