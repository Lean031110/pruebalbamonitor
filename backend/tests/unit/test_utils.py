"""Tests unitarios de utilidades."""
from __future__ import annotations

from lbamonitor.utils.formatters import (
    format_bytes,
    format_currency,
    format_duration,
    format_number,
    parse_float,
)
from lbamonitor.utils.helpers import (
    generate_serial,
    hash_password,
    sha256_hex,
    slugify,
    verify_password,
)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

class TestFormatters:
    def test_format_bytes(self) -> None:
        assert format_bytes(0) == "0 B"
        assert format_bytes(1023) == "1023.00 B"
        assert format_bytes(1024) == "1.00 KB"
        assert format_bytes(1024 * 1024) == "1.00 MB"
        assert format_bytes(1024 ** 3) == "1.00 GB"
        assert format_bytes(1024 ** 4) == "1.00 TB"
        assert format_bytes(None) == "0 B"
        assert format_bytes(-100) == "0 B"

    def test_format_currency(self) -> None:
        assert format_currency(0) == "0.00₱"
        assert format_currency(1234.5) == "1,234.50₱"
        assert format_currency(1234.56, symbol="$", decimals=0) == "1,235$"
        assert format_currency(None) == "0.00₱"

    def test_format_duration(self) -> None:
        assert format_duration(0) == "0s"
        assert format_duration(45) == "45s"
        assert format_duration(90) == "1m 30s"
        assert format_duration(3661) == "1h 1m 1s"
        assert format_duration(None) == "0s"

    def test_format_number(self) -> None:
        assert format_number(1234567) == "1,234,567"
        assert format_number(1234.5, decimals=2) == "1,234.50"
        assert format_number(None) == "0"

    def test_parse_float(self) -> None:
        assert parse_float("1234.56") == 1234.56
        assert parse_float("1234,56") == 1234.56
        assert parse_float("1.234,56") == 1234.56
        assert parse_float("1,234.56") == 1234.56
        assert parse_float("") == 0.0
        assert parse_float(None) == 0.0
        assert parse_float("abc", default=-1.0) == -1.0


# ---------------------------------------------------------------------------
# Helpers de seguridad
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_and_verify(self) -> None:
        password = "S3cretP@ss!"
        hashed = hash_password(password)
        assert "$" in hashed
        assert verify_password(password, hashed) is True
        assert verify_password("wrong", hashed) is False
        assert verify_password(password, "") is False
        assert verify_password(password, "invalid") is False

    def test_hash_is_unique(self) -> None:
        """Cada hash debe tener un salt único."""
        h1 = hash_password("mipassword")
        h2 = hash_password("mipassword")
        assert h1 != h2  # salts distintos
        assert verify_password("mipassword", h1)
        assert verify_password("mipassword", h2)

    def test_empty_password_rejected(self) -> None:
        try:
            hash_password("")
            assert False, "Debería haber lanzado ValueError"
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Otros helpers
# ---------------------------------------------------------------------------

class TestOtherHelpers:
    def test_sha256_hex(self) -> None:
        assert sha256_hex("hello") == (
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )
        assert sha256_hex(b"hello") == sha256_hex("hello")
        assert len(sha256_hex("test")) == 64

    def test_slugify(self) -> None:
        assert slugify("Hola Mundo!") == "hola-mundo"
        assert slugify("  Muchos   Espacios  ") == "muchos-espacios"
        assert slugify("Config__User") == "config-user"
        assert slugify("///weird///") == "weird"

    def test_generate_serial(self) -> None:
        s1 = generate_serial(16)
        s2 = generate_serial(16)
        assert len(s1) == 16
        assert s1 != s2
        # Solo A-Z0-9
        assert all(c.isalnum() and c.isupper() or c.isdigit() for c in s1)

    def test_generate_serial_custom_length(self) -> None:
        assert len(generate_serial(8)) == 8
        assert len(generate_serial(32)) == 32
