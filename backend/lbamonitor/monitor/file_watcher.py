"""
FileSystemWatcher con watchdog + debouncer.

Vigila una carpeta (raíz de una USB montada) y emite eventos:
  - on_created: archivo copiado hacia la USB
  - on_deleted: archivo borrado de la USB
  - on_modified: archivo modificado (raros, se filtran con debounce)

El debouncer de 500ms evita eventos duplicados típicos de Windows
(Created + Modified + Modified al crear un archivo).

CRÍTICO: Este watcher SOLO funciona para USB mass-storage (con letra de unidad).
Para MTP (celulares Android) NO funciona porque no hay filesystem montado.
Ver mtp_monitor.py para el polling específico de MTP.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from lbamonitor.core.enums import OperationType
from lbamonitor.monitor.categorizer import (
    categorize_file,
    get_extension,
    is_system_file,
    matches_filter,
)
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class FileEvent:
    """Evento unificado de filesystem."""

    operation: OperationType
    file_path: str
    file_name: str
    file_ext: str
    file_size: int
    category: str  # FileCategory value
    detected_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "operation": self.operation.value,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_ext": self.file_ext,
            "file_size": self.file_size,
            "category": self.category,
            "detected_at": self.detected_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Handler interno con debouncer
# ---------------------------------------------------------------------------

class _DebouncedHandler(FileSystemEventHandler):
    """
    Handler con debounce por path: si el mismo path genera múltiples eventos
    en ventana de N ms, solo se emite el último.

    Esto es necesario porque Windows dispara Created+Modified+Modified+Modified
    al crear un archivo.
    """

    def __init__(
        self,
        debounce_ms: int,
        exclude_patterns: list[str],
        exclude_system: bool,
        callback: Callable[[FileEvent], None],
    ) -> None:
        super().__init__()
        self._debounce_seconds = debounce_ms / 1000.0
        self._exclude_patterns = exclude_patterns
        self._exclude_system = exclude_system
        self._callback = callback
        self._lock = threading.Lock()
        self._last_events: dict[str, float] = defaultdict(float)
        self._sizes: dict[str, int] = {}

    def _should_skip(self, path: str) -> bool:
        """True si el evento debe ignorarse."""
        if self._exclude_system and is_system_file(path):
            return True
        if matches_filter(path, self._exclude_patterns):
            return True
        return False

    def _get_size(self, path: str) -> int:
        """Devuelve el tamaño del archivo de forma segura."""
        try:
            return Path(path).stat().st_size
        except (OSError, FileNotFoundError):
            # Para eventos deleted, el archivo ya no existe
            return self._sizes.get(path, 0)

    def _emit(self, operation: OperationType, src_path: str) -> None:
        """Emit un evento con debounce."""
        if self._should_skip(src_path):
            return

        now = time.monotonic()
        with self._lock:
            last = self._last_events.get(src_path, 0)
            if now - last < self._debounce_seconds:
                # Suprimir duplicado dentro de la ventana
                return
            self._last_events[src_path] = now

            # Cleanup periódico de entradas antiguas (memory leak fix)
            # Mantener solo entries dentro de 10x la ventana de debounce
            cutoff = now - (self._debounce_seconds * 10)
            expired = [k for k, v in self._last_events.items() if v < cutoff]
            for k in expired:
                self._last_events.pop(k, None)
                self._sizes.pop(k, None)

        # Para deleted, recuperar size del cache
        size = self._get_size(src_path)
        if operation == OperationType.CREATED:
            self._sizes[src_path] = size
        elif operation == OperationType.DELETED:
            size = self._sizes.pop(src_path, size)

        # Solo el nombre base
        from os.path import basename, splitext
        file_name = basename(src_path)
        ext = get_extension(file_name)
        category = categorize_file(file_name, ext).value

        event = FileEvent(
            operation=operation,
            file_path=src_path,
            file_name=file_name,
            file_ext=ext,
            file_size=size,
            category=category,
        )
        try:
            self._callback(event)
        except Exception as e:
            log.exception(f"Error en callback de file_watcher: {e}")

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._emit(OperationType.CREATED, event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._emit(OperationType.DELETED, event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        # Solo nos interesan modificaciones de archivos existentes
        # (no las modificaciones que acompañan a un Created, que filtra el debounce)
        if event.is_directory:
            return
        # Para modificaciones, actualizar size en cache pero no emitir evento
        # (en la copia a USB, las modificaciones son ruido)
        try:
            size = Path(event.src_path).stat().st_size
            with self._lock:
                self._sizes[event.src_path] = size
        except (OSError, FileNotFoundError):
            pass

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        # Renamed: emitimos como DELETED del viejo + CREATED del nuevo
        self._emit(OperationType.DELETED, event.src_path)
        self._emit(OperationType.CREATED, event.dest_path)


# ---------------------------------------------------------------------------
# CopyMonitor — wrapper async-friendly sobre watchdog
# ---------------------------------------------------------------------------

class CopyMonitor:
    """
    Vigila una carpeta (raíz de USB) y emite FileEvent vía callback.

    Uso:
        monitor = CopyMonitor(callback=my_async_callback)
        monitor.start("E:\\\\")
        ...
        monitor.stop()

    El callback puede ser sync o async. Si es async, se programa en el loop.
    """

    def __init__(
        self,
        callback: Callable[[FileEvent], Awaitable[None] | None],
        debounce_ms: int = 500,
        exclude_patterns: list[str] | None = None,
        exclude_system: bool = True,
    ) -> None:
        self._callback = callback
        self._debounce_ms = debounce_ms
        self._exclude_patterns = exclude_patterns or [
            "Thumbs.db", ".DS_Store", "desktop.ini", "~$*", "*.tmp",
        ]
        self._exclude_system = exclude_system
        self._observer: Observer | None = None
        self._handler: _DebouncedHandler | None = None
        self._watched_path: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # Stats en vivo (thread-safe)
        self._stats_lock = threading.Lock()
        self._stats = {
            "files_copied": 0,
            "files_deleted": 0,
            "files_modified": 0,
            "bytes_copied": 0,
            "operation_count": 0,
        }
        self._category_counts: dict[str, int] = defaultdict(int)

    def _on_event(self, event: FileEvent) -> None:
        """Callback síncrono invocado por watchdog en su hilo."""
        # Actualizar stats
        with self._stats_lock:
            if event.operation == OperationType.CREATED:
                self._stats["files_copied"] += 1
                self._stats["bytes_copied"] += event.file_size
            elif event.operation == OperationType.DELETED:
                self._stats["files_deleted"] += 1
            self._stats["operation_count"] += 1
            self._category_counts[event.category] += 1

        # Pasar al callback del usuario (puede ser async)
        try:
            result = self._callback(event)
            if asyncio.iscoroutine(result):
                # Programar en el loop principal
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(result, self._loop)
                else:
                    # Sin loop, descartar (no debería pasar)
                    result.close()
        except Exception as e:
            log.exception(f"Error en callback de CopyMonitor: {e}")

    def start(self, path: str) -> None:
        """Inicia el watcher sobre la carpeta dada."""
        if self._observer is not None:
            log.warning("CopyMonitor ya está corriendo")
            return

        self._watched_path = path
        self._loop = asyncio.get_event_loop()

        self._handler = _DebouncedHandler(
            debounce_ms=self._debounce_ms,
            exclude_patterns=self._exclude_patterns,
            exclude_system=self._exclude_system,
            callback=self._on_event,
        )
        self._observer = Observer()
        # recursive=True para vigilar subcarpetas
        self._observer.schedule(self._handler, path, recursive=True)
        self._observer.start()
        log.info(f"CopyMonitor iniciado en {path}")

    def stop(self) -> None:
        """Detiene el watcher."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            self._handler = None
            log.info(f"CopyMonitor detenido en {self._watched_path}")
            self._watched_path = None

    def snapshot(self) -> dict:
        """Devuelve una copia de las stats actuales."""
        with self._stats_lock:
            return {
                **self._stats,
                "categories": dict(self._category_counts),
            }

    def finalize(self) -> dict:
        """
        Devuelve las stats finales y limpia estado.
        Llamar antes de detener para capturar el snapshot final.
        """
        return self.snapshot()
