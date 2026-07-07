"""Tests del auto-copiador de publicidad."""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from lbamonitor.monitor.publicity_copier import (
    copy_publicity_to_usb,
    copy_single_file,
    get_publicity_stats,
)


@pytest.fixture
def temp_dirs():
    """Crea carpetas temporales fuente y destino con archivos de prueba."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "publicidad"
        dest = Path(tmp) / "usb_destino"
        src.mkdir()
        dest.mkdir()

        # Crear algunos archivos
        (src / "promo.txt").write_text("Contenido promocional")
        (src / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        # Subcarpeta con más archivos
        sub = src / "catalogo"
        sub.mkdir()
        (sub / "peliculas.txt").write_text("Catálogo de películas")

        yield src, dest


@pytest.mark.asyncio
async def test_copy_publicity_basic(temp_dirs) -> None:
    """Copia recursiva de archivos funciona."""
    src, dest = temp_dirs

    result = await copy_publicity_to_usb(str(dest), str(src))

    assert result["copied_count"] == 3  # promo.txt, logo.png, peliculas.txt
    assert result["failed_count"] == 0
    assert result["bytes_copied"] > 0

    # Verificar que los archivos existen en destino
    assert (dest / "promo.txt").is_file()
    assert (dest / "logo.png").is_file()
    assert (dest / "catalogo" / "peliculas.txt").is_file()


@pytest.mark.asyncio
async def test_copy_publicity_skip_existing(temp_dirs) -> None:
    """Si overwrite=False, no se sobrescriben archivos existentes."""
    src, dest = temp_dirs

    # Primera copia
    r1 = await copy_publicity_to_usb(str(dest), str(src))
    assert r1["copied_count"] == 3
    assert r1["skipped_count"] == 0

    # Modificar el original
    (src / "promo.txt").write_text("Contenido MODIFICADO")

    # Segunda copia sin overwrite → debe saltar todos
    r2 = await copy_publicity_to_usb(str(dest), str(src))
    assert r2["copied_count"] == 0
    assert r2["skipped_count"] == 3

    # Verificar que el archivo en destino NO fue sobrescrito
    assert (dest / "promo.txt").read_text() == "Contenido promocional"


@pytest.mark.asyncio
async def test_copy_publicity_overwrite(temp_dirs) -> None:
    """Con overwrite=True, se sobrescriben archivos existentes."""
    src, dest = temp_dirs

    await copy_publicity_to_usb(str(dest), str(src))
    (src / "promo.txt").write_text("Contenido MODIFICADO")

    r2 = await copy_publicity_to_usb(str(dest), str(src), overwrite=True)
    # Con overwrite=True, los 3 archivos se "copian" (sobrescriben)
    assert r2["copied_count"] == 3
    # El archivo modificado debe tener el contenido nuevo
    assert (dest / "promo.txt").read_text() == "Contenido MODIFICADO"


@pytest.mark.asyncio
async def test_copy_publicity_invalid_source() -> None:
    """Si la carpeta origen no existe, devuelve error."""
    result = await copy_publicity_to_usb("X:\\", "/no/existe/esta/ruta")
    assert result["copied_count"] == 0
    assert len(result["errors"]) > 0


@pytest.mark.asyncio
async def test_copy_single_file(temp_dirs) -> None:
    """Copia de un archivo individual."""
    src, dest = temp_dirs
    src_file = src / "promo.txt"
    dest_dir = dest / "subdir"
    dest_dir.mkdir()

    ok = await copy_single_file(str(src_file), str(dest_dir), "renombrado.txt")
    assert ok is True
    assert (dest_dir / "renombrado.txt").is_file()


@pytest.mark.asyncio
async def test_copy_single_file_nonexistent() -> None:
    """Si el archivo no existe, devuelve False."""
    ok = await copy_single_file("/no/existe.txt", "/tmp")
    assert ok is False


def test_get_publicity_stats(temp_dirs) -> None:
    """get_publicity_stats devuelve conteo correcto."""
    src, _ = temp_dirs
    stats = get_publicity_stats(str(src))
    assert stats["valid"] is True
    assert stats["file_count"] == 3
    assert stats["total_bytes"] > 0


def test_get_publicity_stats_invalid() -> None:
    """Si la carpeta no existe, valid=False."""
    stats = get_publicity_stats("/no/existe")
    assert stats["valid"] is False
    assert stats["file_count"] == 0
