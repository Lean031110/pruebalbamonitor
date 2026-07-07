"""Tests del FileWatcher (watchdog + debouncer)."""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path

import pytest

from lbamonitor.core.enums import OperationType
from lbamonitor.monitor.file_watcher import CopyMonitor, FileEvent


@pytest.mark.asyncio
async def test_file_watcher_detects_creation():
    """CopyMonitor detecta creación de archivos en la carpeta vigilada."""
    events: list[FileEvent] = []

    async def on_event(ev: FileEvent) -> None:
        events.append(ev)

    with tempfile.TemporaryDirectory() as tmp:
        monitor = CopyMonitor(callback=on_event, debounce_ms=200)
        monitor.start(tmp)

        # Crear un archivo
        (Path(tmp) / "test.mp4").write_bytes(b"x" * 100)

        # Esperar a que el watcher procese (con margen para latencia)
        await asyncio.sleep(2.0)

        monitor.stop()

    # Verificar que detectó el archivo (al menos 1 evento created)
    created = [e for e in events if e.operation == OperationType.CREATED]
    assert len(created) >= 1
    if created:
        assert created[0].file_name == "test.mp4"
        assert created[0].file_ext == ".mp4"
        assert created[0].file_size == 100
        assert created[0].category == "video"


@pytest.mark.asyncio
async def test_file_watcher_detects_deletion():
    """CopyMonitor detecta borrado de archivos."""
    events: list[FileEvent] = []

    async def on_event(ev: FileEvent) -> None:
        events.append(ev)

    with tempfile.TemporaryDirectory() as tmp:
        # Crear archivo antes de empezar a vigilar
        f = Path(tmp) / "to_delete.txt"
        f.write_text("data")

        monitor = CopyMonitor(callback=on_event, debounce_ms=200)
        monitor.start(tmp)

        # Esperar a que el watcher haga snapshot inicial
        await asyncio.sleep(0.3)

        # Borrar el archivo
        f.unlink()

        await asyncio.sleep(1.0)
        monitor.stop()

    deleted = [e for e in events if e.operation == OperationType.DELETED]
    assert len(deleted) >= 1
    assert deleted[0].file_name == "to_delete.txt"


@pytest.mark.asyncio
async def test_file_watcher_excludes_system_files():
    """Thumbs.db y .DS_Store no generan eventos."""
    events: list[FileEvent] = []

    async def on_event(ev: FileEvent) -> None:
        events.append(ev)

    with tempfile.TemporaryDirectory() as tmp:
        monitor = CopyMonitor(
            callback=on_event,
            debounce_ms=200,
            exclude_system=True,
        )
        monitor.start(tmp)

        (Path(tmp) / "Thumbs.db").write_bytes(b"system")
        (Path(tmp) / "pelicula.mp4").write_bytes(b"x" * 10)

        await asyncio.sleep(1.0)
        monitor.stop()

    # Solo debe haber detectado pelicula.mp4, no Thumbs.db
    names = [e.file_name for e in events]
    assert "pelicula.mp4" in names
    assert "Thumbs.db" not in names


@pytest.mark.asyncio
async def test_file_watcher_debounce():
    """Múltiples eventos del mismo path en ventana corta se filtran."""
    events: list[FileEvent] = []

    async def on_event(ev: FileEvent) -> None:
        events.append(ev)

    with tempfile.TemporaryDirectory() as tmp:
        # Debounce alto (1s) para asegurar que filtre
        monitor = CopyMonitor(callback=on_event, debounce_ms=1000)
        monitor.start(tmp)

        # Crear archivo (genera Created + Modified x N)
        f = Path(tmp) / "debounced.txt"
        f.write_text("data")

        # Tocar el archivo varias veces rápido
        for _ in range(5):
            f.write_text("data" + str(time.time()))
            time.sleep(0.05)

        await asyncio.sleep(1.5)
        monitor.stop()

    # Solo debe haber 1 evento Created (debounce filtra duplicados)
    created = [e for e in events if e.operation == OperationType.CREATED]
    assert len(created) == 1


@pytest.mark.asyncio
async def test_file_watcher_stats():
    """snapshot() devuelve stats acumuladas."""
    events: list[FileEvent] = []

    async def on_event(ev: FileEvent) -> None:
        events.append(ev)

    with tempfile.TemporaryDirectory() as tmp:
        monitor = CopyMonitor(callback=on_event, debounce_ms=200)
        monitor.start(tmp)

        (Path(tmp) / "a.mp4").write_bytes(b"x" * 100)
        (Path(tmp) / "b.mp3").write_bytes(b"y" * 50)

        # Esperar más tiempo para que watchdog procese (puede haber latencia)
        await asyncio.sleep(2.0)
        stats = monitor.snapshot()
        monitor.stop()

    # Al menos 1 evento debe haberse registrado (puede haber latencia)
    assert stats["files_copied"] >= 1
    assert stats["operation_count"] >= 1
    # Categorías contadas
    assert "video" in stats["categories"] or "music" in stats["categories"]
