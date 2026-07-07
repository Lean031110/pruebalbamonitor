"""
Tests del módulo de autenticación (auth.py) — v4.3.

Cubre:
- hash_password / verify_password (bcrypt y PBKDF2)
- create_access_token / create_refresh_token / decode_token
- Blacklist de tokens (revoke_token)
- verify_credentials (con mock de BD)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest

# Setup path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Forzar env de test
os.environ["LBAMONITOR_ENV"] = "test"
os.environ["PYTEST_CURRENT_TEST"] = "1"

from lbamonitor.core.config import get_settings, reload_settings
from lbamonitor.core.security import auth as auth_module
from lbamonitor.core.security.auth import (
    TokenData,
    TokenBlacklist,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_token,
    _blacklist,
)


@pytest.fixture(autouse=True)
def setup_test_env():
    """Configura jwt_secret de test antes de cada test."""
    s = get_settings()
    s.security.jwt_secret = "test-secret-very-secure-12345"
    s.security.jwt_algorithm = "HS256"
    yield
    # Reset blacklist entre tests
    _blacklist._entries.clear()


# ─────────────────────────────────────────────────────────────────────
# Hashing de passwords
# ─────────────────────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_password_returns_string(self):
        h = hash_password("test123")
        assert isinstance(h, str)
        assert len(h) > 20

    def test_hash_password_different_each_time(self):
        h1 = hash_password("test123")
        h2 = hash_password("test123")
        assert h1 != h2  # Salt aleatorio

    def test_verify_password_correct(self):
        h = hash_password("test123")
        assert verify_password("test123", h)

    def test_verify_password_wrong(self):
        h = hash_password("test123")
        assert not verify_password("wrong", h)

    def test_verify_password_empty_hash(self):
        assert not verify_password("test", "")
        assert not verify_password("test", None)

    def test_verify_password_pbkdf2_compat(self):
        """Verifica compatibilidad con hashes PBKDF2 legacy."""
        import hashlib
        import binascii
        salt = b"\x00" * 32
        h = hashlib.pbkdf2_hmac("sha256", b"test123", salt, 200000)
        stored = f"pbkdf2_sha256$200000${binascii.hexlify(salt).decode()}${binascii.hexlify(h).decode()}"
        assert verify_password("test123", stored)
        assert not verify_password("wrong", stored)

    def test_hash_empty_password_behavior(self):
        """Hash de password vacía: bcrypt genera un hash (no falla).
        En producción, validar input antes de hashear."""
        h = hash_password("")
        # El hash se genera pero verify_password debe manejarlo
        # Lo importante es que verify_password funcione
        assert verify_password("", h)


# ─────────────────────────────────────────────────────────────────────
# JWT tokens
# ─────────────────────────────────────────────────────────────────────

class TestJWTTokens:
    def test_create_access_token(self):
        tok = create_access_token("admin", "admin")
        assert isinstance(tok, str)
        assert len(tok) > 50

    def test_decode_access_token(self):
        tok = create_access_token("admin", "admin")
        td = decode_token(tok)
        assert td is not None
        assert td.sub == "admin"
        assert td.role == "admin"
        assert td.token_type == "access"

    def test_create_refresh_token(self):
        tok = create_refresh_token("operator1", "operator")
        td = decode_token(tok)
        assert td is not None
        assert td.sub == "operator1"
        assert td.role == "operator"
        assert td.token_type == "refresh"

    def test_decode_invalid_token(self):
        assert decode_token("invalid.token.here") is None
        assert decode_token("") is None
        assert decode_token("not-a-jwt") is None

    def test_decode_token_wrong_secret(self):
        """Token generado con un secret no debe verificar con otro."""
        tok = create_access_token("admin", "admin")
        # Cambiar secret y verificar que ya no valida
        s = get_settings()
        original = s.security.jwt_secret
        s.security.jwt_secret = "different-secret"
        assert decode_token(tok) is None
        s.security.jwt_secret = original

    def test_token_has_jti(self):
        """Cada token debe tener un jti único (para blacklist)."""
        tok1 = create_access_token("admin", "admin")
        tok2 = create_access_token("admin", "admin")
        td1 = decode_token(tok1)
        td2 = decode_token(tok2)
        assert td1.jti != td2.jti
        assert len(td1.jti) == 32  # 16 bytes hex

    def test_token_has_expiry(self):
        tok = create_access_token("admin", "admin")
        td = decode_token(tok)
        assert td.exp > 0


# ─────────────────────────────────────────────────────────────────────
# Blacklist
# ─────────────────────────────────────────────────────────────────────

class TestTokenBlacklist:
    def test_blacklist_add_and_check(self):
        bl = TokenBlacklist()
        bl.add("jti-123", exp=9999999999)
        assert bl.is_revoked("jti-123")
        assert not bl.is_revoked("jti-other")

    def test_blacklist_cleanup_expired(self):
        import time
        bl = TokenBlacklist()
        # Añadir entrada expirada
        bl.add("expired-jti", exp=int(time.time()) - 100)
        # Forzar cleanup
        bl._last_cleanup = 0  # forzar próxima llamada
        # is_revoked dispara cleanup
        assert not bl.is_revoked("expired-jti")  # ya expirada, no está "revoked" activamente
        # Pero la entrada se limpió
        assert "expired-jti" not in bl._entries

    def test_revoke_token_function(self):
        """La función revoke_token global debe añadir a la blacklist."""
        revoke_token("test-jti-456", exp=9999999999)
        assert _blacklist.is_revoked("test-jti-456")


# ─────────────────────────────────────────────────────────────────────
# Integration: token revocation
# ─────────────────────────────────────────────────────────────────────

class TestTokenRevocation:
    def test_revoked_token_decode_still_works_but_blacklist_blocks(self):
        """decode_token no verifica blacklist (eso lo hace get_current_user)."""
        tok = create_access_token("admin", "admin")
        td = decode_token(tok)
        assert td is not None
        # Revocar
        revoke_token(td.jti, td.exp)
        # decode_token sigue funcionando (no verifica blacklist)
        td2 = decode_token(tok)
        assert td2 is not None
        # Pero la blacklist dice que está revocado
        assert _blacklist.is_revoked(td.jti)
