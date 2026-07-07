"""
Categorización automática de archivos por extensión y nombre.

Puro Python, sin dependencias de Windows. 100% testeable.
"""
from __future__ import annotations

import re
from typing import Optional

from lbamonitor.core.enums import FileCategory


# Mapeo extensión → categoría (heredado de LBA USB Manager v3.0)
EXT_CATEGORIES: dict[str, FileCategory] = {
    # Video
    ".mp4": FileCategory.VIDEO,
    ".avi": FileCategory.VIDEO,
    ".mkv": FileCategory.VIDEO,
    ".mov": FileCategory.VIDEO,
    ".wmv": FileCategory.VIDEO,
    ".flv": FileCategory.VIDEO,
    ".webm": FileCategory.VIDEO,
    ".m4v": FileCategory.VIDEO,
    ".mpg": FileCategory.VIDEO,
    ".mpeg": FileCategory.VIDEO,
    ".3gp": FileCategory.VIDEO,
    ".vob": FileCategory.VIDEO,
    # Audio
    ".mp3": FileCategory.MUSIC,
    ".wav": FileCategory.MUSIC,
    ".flac": FileCategory.MUSIC,
    ".aac": FileCategory.MUSIC,
    ".ogg": FileCategory.MUSIC,
    ".wma": FileCategory.MUSIC,
    ".m4a": FileCategory.MUSIC,
    ".opus": FileCategory.MUSIC,
    # Documentos
    ".pdf": FileCategory.DOCUMENT,
    ".doc": FileCategory.DOCUMENT,
    ".docx": FileCategory.DOCUMENT,
    ".xls": FileCategory.DOCUMENT,
    ".xlsx": FileCategory.DOCUMENT,
    ".ppt": FileCategory.DOCUMENT,
    ".pptx": FileCategory.DOCUMENT,
    ".txt": FileCategory.DOCUMENT,
    ".odt": FileCategory.DOCUMENT,
    ".ods": FileCategory.DOCUMENT,
    ".rtf": FileCategory.DOCUMENT,
    ".epub": FileCategory.DOCUMENT,
    ".md": FileCategory.DOCUMENT,
    # Imágenes
    ".jpg": FileCategory.IMAGE,
    ".jpeg": FileCategory.IMAGE,
    ".png": FileCategory.IMAGE,
    ".gif": FileCategory.IMAGE,
    ".bmp": FileCategory.IMAGE,
    ".webp": FileCategory.IMAGE,
    ".tiff": FileCategory.IMAGE,
    ".tif": FileCategory.IMAGE,
    ".svg": FileCategory.IMAGE,
    ".heic": FileCategory.IMAGE,
    # Juegos
    ".iso": FileCategory.GAME,
    ".nsp": FileCategory.GAME,
    ".xci": FileCategory.GAME,
    ".rom": FileCategory.GAME,
    # Apps
    ".apk": FileCategory.APP,
    ".ipa": FileCategory.APP,
    ".exe": FileCategory.APP,
    ".msi": FileCategory.APP,
    ".dmg": FileCategory.APP,
    ".deb": FileCategory.APP,
    ".rpm": FileCategory.APP,
    # Archivos
    ".zip": FileCategory.OTHER,
    ".rar": FileCategory.OTHER,
    ".7z": FileCategory.OTHER,
    ".tar": FileCategory.OTHER,
    ".gz": FileCategory.OTHER,
}


# Patrones para distinguir películas/series dentro de videos
SERIES_PATTERNS = [
    re.compile(r"[Ss]\d{1,2}[Ee]\d{1,2}"),  # S01E05
    re.compile(r"\d{1,2}[xX]\d{1,2}"),  # 1x05
    re.compile(r"[Tt]emporada\s*\d+", re.IGNORECASE),  # Temporada 1
    re.compile(r"[Ss]eason\s*\d+", re.IGNORECASE),  # Season 1
    re.compile(r"[Cc]ap[ií]tulo\s*\d+", re.IGNORECASE),  # Capítulo 1
    re.compile(r"[Ee]pisode\s*\d+", re.IGNORECASE),  # Episode 1
    re.compile(r"\b[tT]\d{1,2}\b"),  # T01
]

MOVIE_PATTERNS = [
    re.compile(r"\b(1080|720|480)[pP]?\b"),  # 1080p, 720p
    re.compile(r"\b(bdrip|brrip|dvdrip|webrip|web-dl|hdtv)\b", re.IGNORECASE),
    re.compile(r"\bx264|x265|h264|h265|hevc|avc\b", re.IGNORECASE),
    re.compile(r"\(\d{4}\)"),  # Año entre paréntesis (2024)
    re.compile(r"\b(extended|remastered|directors.?cut|imax)\b", re.IGNORECASE),
]


def get_extension(file_name: str) -> str:
    """
    Devuelve la extensión en minúsculas con el punto.
    Ej: "pelicula.mp4" → ".mp4"
    """
    import os
    _, ext = os.path.splitext(file_name)
    return ext.lower()


def categorize_file(file_name: str, ext: Optional[str] = None) -> FileCategory:
    """
    Categoriza un archivo según su extensión y, si es video, su nombre.

    Para videos, distingue entre MOVIE y SERIES con regex.
    Si no se puede determinar, devuelve VIDEO genérico.

    Args:
        file_name: nombre del archivo (puede ser path completo)
        ext: extensión pre-calculada (opcional, evita recalcular)
    """
    if ext is None:
        ext = get_extension(file_name)

    # Solo el nombre base para los regex
    import os
    base_name = os.path.basename(file_name)
    name_lower = base_name.lower()

    # Categoría base por extensión
    category = EXT_CATEGORIES.get(ext, FileCategory.OTHER)

    # Refinamiento para videos: distinguir película/serie
    if category == FileCategory.VIDEO:
        for pattern in SERIES_PATTERNS:
            if pattern.search(base_name):
                return FileCategory.SERIES
        for pattern in MOVIE_PATTERNS:
            if pattern.search(base_name):
                return FileCategory.MOVIE
        # Si no hay patrón claro, dejamos VIDEO genérico
        return FileCategory.VIDEO

    return category


def is_system_file(file_name: str) -> bool:
    """True si el archivo debe ser excluido (Thumbs.db, .DS_Store, etc.)."""
    import os
    base = os.path.basename(file_name).lower()
    system_files = {
        "thumbs.db",
        ".ds_store",
        "desktop.ini",
        ".spotlight-v100",
        ".trashes",
        "ehthumbs.db",
        "$recycle.bin",
    }
    if base in system_files:
        return True
    # Archivos temporales de Office
    if base.startswith("~$") or base.startswith("~"):
        return True
    # System Volume Information
    if "system volume information" in file_name.lower():
        return True
    return False


def matches_filter(file_name: str, exclude_patterns: list[str]) -> bool:
    """
    True si el archivo coincide algún patrón de exclusión (glob).

    Soporta wildcards simples: *, ?.
    """
    import fnmatch
    base = file_name.lower()
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(base, pattern.lower()):
            return True
    return False
