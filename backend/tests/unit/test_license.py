"""Tests del motor de licencias."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from lbamonitor.core.services.license_engine import (
    generate_license,
    verify_license,
)


# HWID ficticio para tests (en producción vendría de compute_machine_id)
TEST_HWID = "a" * 64
TEST_SECRET = "test-secret-key-for-unit-tests"


class TestLicenseEngine:
    def test_generate_and_verify_valid(self) -> None:
        """Licencia válida se verifica OK."""
        expires = (datetime.now() + timedelta(days=365)).date().isoformat()
        lic = generate_license(
            machine_id=TEST_HWID, expires=expires, tier="pro", secret=TEST_SECRET
        )
        assert "." in lic

        result = verify_license(lic, TEST_HWID, TEST_SECRET)
        assert result["valid"] is True
        assert result["tier"] == "pro"
        assert result["expires"] == expires

    def test_verify_wrong_hwid(self) -> None:
        """Licencia con HWID distinto no valida."""
        lic = generate_license(
            machine_id=TEST_HWID, expires=None, tier="pro", secret=TEST_SECRET
        )
        result = verify_license(lic, "b" * 64, TEST_SECRET)
        assert result["valid"] is False
        assert "HWID" in result["reason"]

    def test_verify_wrong_secret(self) -> None:
        """Licencia firmada con otra clave no verifica."""
        lic = generate_license(
            machine_id=TEST_HWID, expires=None, tier="pro", secret=TEST_SECRET
        )
        result = verify_license(lic, TEST_HWID, "wrong-secret")
        assert result["valid"] is False
        assert "firma" in result["reason"].lower() or "signature" in result["reason"].lower()

    def test_verify_expired(self) -> None:
        """Licencia expirada no valida."""
        past_date = (datetime.now() - timedelta(days=1)).date().isoformat()
        lic = generate_license(
            machine_id=TEST_HWID, expires=past_date, tier="pro", secret=TEST_SECRET
        )
        result = verify_license(lic, TEST_HWID, TEST_SECRET)
        assert result["valid"] is False
        assert "expirada" in result["reason"].lower()

    def test_verify_invalid_format(self) -> None:
        """Strings malformados no validan."""
        assert verify_license("", TEST_HWID, TEST_SECRET)["valid"] is False
        assert verify_license("sinpunto", TEST_HWID, TEST_SECRET)["valid"] is False
        assert verify_license("xxx.yyy", TEST_HWID, TEST_SECRET)["valid"] is False

    def test_generate_without_secret_raises(self) -> None:
        """Generar sin clave secreta lanza error."""
        with pytest.raises(ValueError):
            generate_license(machine_id=TEST_HWID, expires=None, tier="pro", secret="")
