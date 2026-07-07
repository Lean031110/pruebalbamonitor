"""Tests del categorizer de archivos."""
from __future__ import annotations

from lbamonitor.core.enums import FileCategory
from lbamonitor.monitor.categorizer import (
    categorize_file,
    get_extension,
    is_system_file,
    matches_filter,
)


class TestGetExtension:
    def test_simple(self) -> None:
        assert get_extension("pelicula.mp4") == ".mp4"
        assert get_extension("documento.PDF") == ".pdf"  # minúsculas
        assert get_extension("archivo.tar.gz") == ".gz"

    def test_no_extension(self) -> None:
        assert get_extension("sinextension") == ""
        # os.path.splitext(".gitignore") devuelve (".gitignore", "") → ext = ""
        assert get_extension(".gitignore") == ""

    def test_path(self) -> None:
        assert get_extension("E:\\Videos\\movie.mkv") == ".mkv"


class TestCategorizeFile:
    def test_video(self) -> None:
        assert categorize_file("pelicula.mp4") == FileCategory.VIDEO
        assert categorize_file("clip.avi") == FileCategory.VIDEO
        assert categorize_file("movie.mkv") == FileCategory.VIDEO

    def test_movie_vs_series(self) -> None:
        # Serie: S01E05
        assert categorize_file("Series.Breaking.Bad.S01E05.1080p.mkv") == FileCategory.SERIES
        # Serie: 1x05
        assert categorize_file("Lost.1x05.avi") == FileCategory.SERIES
        # Serie: "Temporada 1"
        assert categorize_file("Game of Thrones Temporada 1.mkv") == FileCategory.SERIES
        # Película: 1080p sin patrón de serie
        assert categorize_file("Inception.2010.1080p.BluRay.mkv") == FileCategory.MOVIE
        # Película: año entre paréntesis
        assert categorize_file("The Matrix (1999).mkv") == FileCategory.MOVIE
        # Video sin patrón claro → VIDEO genérico
        assert categorize_file("random_video.mp4") == FileCategory.VIDEO

    def test_audio(self) -> None:
        assert categorize_file("cancion.mp3") == FileCategory.MUSIC
        assert categorize_file("podcast.m4a") == FileCategory.MUSIC

    def test_document(self) -> None:
        assert categorize_file("informe.pdf") == FileCategory.DOCUMENT
        assert categorize_file("notas.txt") == FileCategory.DOCUMENT
        assert categorize_file("libro.epub") == FileCategory.DOCUMENT

    def test_image(self) -> None:
        assert categorize_file("foto.jpg") == FileCategory.IMAGE
        assert categorize_file("captura.png") == FileCategory.IMAGE

    def test_app(self) -> None:
        assert categorize_file("app.apk") == FileCategory.APP
        assert categorize_file("setup.exe") == FileCategory.APP

    def test_other(self) -> None:
        assert categorize_file("archivo.zip") == FileCategory.OTHER
        assert categorize_file("data.json") == FileCategory.OTHER
        assert categorize_file("desconocido.xyz") == FileCategory.OTHER

    def test_with_explicit_ext(self) -> None:
        assert categorize_file("movie", ext=".mp4") == FileCategory.VIDEO
        assert categorize_file("track", ext=".mp3") == FileCategory.MUSIC


class TestSystemFiles:
    def test_thumbs_db(self) -> None:
        assert is_system_file("Thumbs.db") is True
        assert is_system_file("thumbs.db") is True  # case insensitive

    def test_ds_store(self) -> None:
        assert is_system_file(".DS_Store") is True

    def test_desktop_ini(self) -> None:
        assert is_system_file("desktop.ini") is True

    def test_office_temp(self) -> None:
        assert is_system_file("~$documento.docx") is True

    def test_normal_file(self) -> None:
        assert is_system_file("pelicula.mp4") is False
        assert is_system_file("informe.pdf") is False

    def test_system_volume(self) -> None:
        assert is_system_file("E:\\System Volume Information\\foo") is True


class TestMatchesFilter:
    def test_glob(self) -> None:
        assert matches_filter("archivo.tmp", ["*.tmp"]) is True
        assert matches_filter("~$word.docx", ["~$*"]) is True
        assert matches_filter("Thumbs.db", ["thumbs.db", "*.tmp"]) is True

    def test_no_match(self) -> None:
        assert matches_filter("pelicula.mp4", ["*.tmp", "*.log"]) is False

    def test_case_insensitive(self) -> None:
        assert matches_filter("VIDEO.MP4", ["*.mp4"]) is True
        assert matches_filter("Video.Mp4", ["*.MP4"]) is True
