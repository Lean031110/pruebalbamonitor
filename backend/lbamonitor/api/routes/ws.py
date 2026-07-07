"""
WebSocket /ws/events para eventos en tiempo real.

Los clientes se conectan a ws://127.0.0.1:8123/ws/events y reciben eventos:
  - drive.inserted
  - drive.removed
  - file.copied
  - file.deleted
  - payment.altered
  - service.session.started
  - service.session.ended
  - pc.datetime.changed
  - billing.registered
  - reward.granted
  - membership.upgraded

El bus de eventos es un singleton asyncio.Queue por cliente conectado.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from lbamonitor.utils.helpers import utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)

router = APIRouter()


class EventBus:
    """
    Bus de eventos en memoria: distribuye eventos a todos los suscriptores.

    Cada cliente WebSocket tiene su propia asyncio.Queue. Cuando se publica
    un evento, se encola en todas las queues activas.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(q)
        log.debug(f"Nuevo suscriptor WS (total: {len(self._subscribers)})")
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(q)
        log.debug(f"Suscriptor desconectado (total: {len(self._subscribers)})")

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publica un evento a todos los suscriptores."""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": utcnow().isoformat(),
        }
        async with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Si la queue está llena, descartar el evento más viejo
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass
        log.debug(f"Evento publicado: {event_type} a {len(subscribers)} suscriptores")


# Singleton
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    """
    WebSocket para recibir eventos en tiempo real.

    El cliente recibe mensajes JSON con la estructura:
    {
        "type": "drive.inserted",
        "data": {...},
        "timestamp": "2026-07-04T22:00:00+00:00"
    }
    """
    await websocket.accept()
    log.info(f"WebSocket conectado desde {websocket.client}")

    bus = get_event_bus()
    queue = await bus.subscribe()

    try:
        # Enviar mensaje de bienvenida
        await websocket.send_json({
            "type": "connection.established",
            "data": {"message": "Conectado al bus de eventos de LBAMonitor"},
            "timestamp": utcnow().isoformat(),
        })

        # Loop principal: leer de la queue y enviar al cliente
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                # Ping periódico para mantener viva la conexión
                await websocket.send_json({
                    "type": "ping",
                    "data": {},
                    "timestamp": utcnow().isoformat(),
                })
    except WebSocketDisconnect:
        log.info(f"WebSocket desconectado desde {websocket.client}")
    except Exception as e:
        log.exception(f"Error en WebSocket: {e}")
    finally:
        await bus.unsubscribe(queue)
