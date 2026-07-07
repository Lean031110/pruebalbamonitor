"""
Cliente WebSocket thread-safe para LBAMonitor v4.3.

Diseño:
- WSClient hereda QObject y define `pyqtSignal`s (en PySide6: `Signal`).
  Los signals son thread-safe en Qt: cuando se emiten desde un hilo
  distinto al del receptor, Qt encola la llamada en la event loop del
  hilo del receptor (main thread por defecto). Así evitamos llamar a
  métodos Qt (QSystemTrayIcon.showMessage, signal.emit de QObject en
  main thread, etc.) directamente desde el hilo del WebSocket.
- _WSWorker es un QObject que se mueve a un QThread dedicado vía
  `moveToThread`. El worker usa `websocket-client` (WebSocketApp) que
  es sincrónico y bloqueante, por lo que corre en su propio hilo.
- El worker emite signals del WSClient (pasado como parent_client)
  cuando llega un mensaje, se abre o se cierra la conexión.

Eventos del backend (ver backend/lbamonitor/api/routes/ws.py):
    {
      "type": "drive.inserted" | "drive.removed" | "file.copied" |
              "file.deleted" | "payment.altered" |
              "service.session.started" | "service.session.ended" |
              "pc.datetime.changed" | "billing.registered" |
              "reward.granted" | "membership.upgraded" |
              "connection.established" | "ping",
      "data": {...},
      "timestamp": "ISO-8601"
    }
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

log = logging.getLogger(__name__)


class WSClient(QObject):
    """Cliente WebSocket thread-safe que expone signals Qt."""

    # Signals emitidos cuando llega un evento (se dispatchean al main thread)
    event_received = Signal(dict)
    connected = Signal()
    disconnected = Signal()
    error = Signal(str)

    def __init__(self, url: str, token: Optional[str] = None) -> None:
        super().__init__()
        self._url = url
        self._token = token
        self._thread: Optional[QThread] = None
        self._worker: Optional[_WSWorker] = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Arranca el worker en un QThread dedicado."""
        if self._running:
            return
        self._running = True
        self._thread = QThread()
        self._thread.setObjectName("WSClientThread")
        self._worker = _WSWorker(self._url, self._token, self)
        self._worker.moveToThread(self._thread)
        # Conexiones para iniciar/parar el worker
        self._thread.started.connect(self._worker.run)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def stop(self) -> None:
        """Detiene el worker y el hilo de forma ordenada."""
        if not self._running:
            return
        self._running = False
        if self._worker is not None:
            # Llamar a stop() del worker — esto invoca ws.close() que es
            # thread-safe y desbloquea run_forever().
            try:
                self._worker.stop()
            except Exception as e:
                log.debug(f"WSClient.stop: worker.stop error: {e}")
        if self._thread is not None:
            self._thread.quit()
            # Esperar hasta 5s a que el hilo termine
            self._thread.wait(5000)
            self._thread = None
        self._worker = None

    @property
    def is_running(self) -> bool:
        return self._running


class _WSWorker(QObject):
    """Worker que corre WebSocketApp.run_forever() en un QThread."""

    def __init__(
        self,
        url: str,
        token: Optional[str],
        parent_client: WSClient,
    ) -> None:
        super().__init__()
        self._url = url
        self._token = token
        self._client = parent_client
        self._ws = None
        self._running = False

    # ------------------------------------------------------------------
    # Main loop (corre en el QThread)
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            from websocket import WebSocketApp, WebSocketException
        except ImportError:
            log.warning(
                "websocket-client no instalado — eventos WS desactivados. "
                "Instala con: pip install websocket-client"
            )
            self._client.error.emit("websocket-client no instalado")
            return

        self._running = True

        # URL con token como query param (forward-compatible con auth WS)
        ws_url = self._url
        if self._token and "?" not in ws_url:
            ws_url = f"{ws_url}?token={self._token}"
        elif self._token:
            ws_url = f"{ws_url}&token={self._token}"

        # Reconexión con backoff
        import time
        backoff = 1

        while self._running:
            try:
                self._ws = WebSocketApp(
                    ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                # run_forever bloquea hasta que se cierre la conexión
                self._ws.run_forever(
                    ping_interval=30,
                    ping_timeout=10,
                )
            except WebSocketException as e:
                log.warning(f"WSClient WebSocketException: {e}")
            except Exception as e:
                log.warning(f"WSClient error inesperado: {e}")

            if not self._running:
                break

            # Backoff exponencial hasta 30s
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

    # ------------------------------------------------------------------
    # WebSocketApp callbacks (corren en el QThread del worker)
    # ------------------------------------------------------------------

    def _on_open(self, ws) -> None:  # noqa: ANN001
        log.info(f"WebSocket conectado: {self._url}")
        # Emitir signal (thread-safe: se dispatchea al main thread)
        self._client.connected.emit()

    def _on_message(self, ws, message: str) -> None:  # noqa: ANN001
        try:
            data = json.loads(message)
            if not isinstance(data, dict):
                return
            self._client.event_received.emit(data)
        except (json.JSONDecodeError, ValueError) as e:
            log.debug(f"WSClient: mensaje no JSON: {e}")

    def _on_error(self, ws, error) -> None:  # noqa: ANN001
        log.warning(f"WSClient error: {error}")
        self._client.error.emit(str(error))

    def _on_close(self, ws, *args) -> None:  # noqa: ANN001
        log.info("WebSocket desconectado")
        self._client.disconnected.emit()

    # ------------------------------------------------------------------
    # Stop (puede ser llamado desde el main thread)
    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._running = False
        ws = self._ws
        if ws is not None:
            try:
                # close() es thread-safe en websocket-client (usa internal lock)
                ws.close()
            except Exception as e:
                log.debug(f"WSWorker.stop: ws.close error: {e}")
