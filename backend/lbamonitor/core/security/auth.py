"""
Servicios de autenticación y autorización para LBAMonitor v4.3.

Implementa:
- Hashing de passwords con bcrypt (fallback PBKDF2 para tests)
- Generación y verificación de JWT (access + refresh tokens)
- Blacklist de tokens revocados (en memoria, con TTL)
- Dependency `get_current_user` y `require_role` para FastAPI

Diseño:
- No usa fallbacks peligrosos (eliminado el `nojwt:` de v4.2)
- Algoritmo HS256 con secret configurable (env var obligatoria en producción)
- Access tokens: 60 min (configurable)
- Refresh tokens: 7 días (configurable)
- Blacklist en memoria con auto-expiración (suficiente para single-instance)
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.config import get_settings
from lbamonitor.core.db import get_db
from lbamonitor.core.models import User
from lbamonitor.core.repositories.user_repository import UserRepository
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────
# JWT (con fallback gracefully si python-jose no está disponible)
# ─────────────────────────────────────────────────────────────────────
try:
    from jose import JWTError, jwt
    JOSE_AVAILABLE = True
except ImportError:  # pragma: no cover
    JOSE_AVAILABLE = False
    log.warning("python-jose no instalado. Auth JWT no disponible.")

# ─────────────────────────────────────────────────────────────────────
# bcrypt (con fallback a PBKDF2 para tests sin bcrypt)
# ─────────────────────────────────────────────────────────────────────
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:  # pragma: no cover
    BCRYPT_AVAILABLE = False
    log.warning("bcrypt no instalado. Usando PBKDF2 (no recomendado para producción).")

# OAuth2 scheme para extraer token del header Authorization
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False,
)


# ─────────────────────────────────────────────────────────────────────
# Hashing de passwords
# ─────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    Hashea una password de forma segura.

    Usa bcrypt si está disponible (recomendado), sino PBKDF2-HMAC-SHA256
    con 200.000 iteraciones y salt aleatorio de 32 bytes.

    Formato bcrypt: $2b$... (empezando con $2)
    Formato PBKDF2: pbkdf2_sha256$iterations$salt_hex$hash_hex
    """
    algo = get_settings().security.password_hash_algo
    if algo == "bcrypt" and BCRYPT_AVAILABLE:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    # Fallback PBKDF2 (compatibilidad con v4.0.0 y tests)
    # Usar helpers.hash_password para garantizar compatibilidad de formatos
    from lbamonitor.utils.helpers import hash_password as _hash_pbkdf2
    return _hash_pbkdf2(password)


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifica una password contra su hash.

    Soporta:
    - bcrypt ($2...)
    - PBKDF2 pbkdf2_sha256$iterations$salt_hex$hash_hex
    - Legacy salt_hex$hash_hex (v3.0/v4.0, auto-detectado)

    Usa secrets.compare_digest para evitar timing attacks.
    """
    if not hashed:
        return False
    # Bcrypt hashes empiezan con $2
    if hashed.startswith("$2") and BCRYPT_AVAILABLE:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False
    # PBKDF2 (formato nuevo o legacy) - delegar a helpers.verify_password
    # que soporta ambos formatos
    from lbamonitor.utils.helpers import verify_password as _verify_pbkdf2
    return _verify_pbkdf2(password, hashed)


def _hash_pbkdf2(password: str, iterations: int = 200_000) -> str:
    """Hash con PBKDF2-HMAC-SHA256. Formato: pbkdf2_sha256$iterations$salt_hex$hash_hex"""
    import hashlib
    import binascii
    salt = secrets.token_bytes(32)
    hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${binascii.hexlify(salt).decode()}${binascii.hexlify(hash_bytes).decode()}"


def _verify_pbkdf2(password: str, hashed: str) -> bool:
    """Verifica hash PBKDF2 en formato pbkdf2_sha256$iterations$salt_hex$hash_hex"""
    import hashlib
    import binascii
    try:
        parts = hashed.split("$")
        if len(parts) != 4:
            return False
        algo, iterations, salt_hex, hash_hex = parts
        if algo != "pbkdf2_sha256":
            return False
        salt = binascii.unhexlify(salt_hex)
        expected_hash = binascii.unhexlify(hash_hex)
        iterations = int(iterations)
        actual_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(actual_hash, expected_hash)
    except (ValueError, TypeError, binascii.Error):
        return False


# ─────────────────────────────────────────────────────────────────────
# Token data y blacklist
# ─────────────────────────────────────────────────────────────────────

@dataclass
class TokenData:
    """Datos extraídos de un JWT verificado."""
    sub: str  # username
    role: str  # admin | operator | viewer
    token_type: str = "access"  # access | refresh
    exp: int = 0
    jti: str = ""  # JWT ID único (para blacklist)


@dataclass
class _BlacklistEntry:
    exp: int  # timestamp de expiración del token


class TokenBlacklist:
    """
    Blacklist en memoria para tokens revocados (logout).

    Auto-limpia entradas expiradas en cada llamada a `is_revoked`.
    Suficiente para single-instance. Para multi-instance, usar Redis.
    """
    def __init__(self) -> None:
        self._entries: dict[str, _BlacklistEntry] = {}
        self._last_cleanup = time.monotonic()

    def add(self, jti: str, exp: int) -> None:
        self._entries[jti] = _BlacklistEntry(exp=exp)

    def is_revoked(self, jti: str) -> bool:
        # Cleanup periódico (cada 60s)
        now = time.monotonic()
        if now - self._last_cleanup > 60:
            self._cleanup(int(time.time()))
            self._last_cleanup = now
        return jti in self._entries

    def _cleanup(self, now_ts: int) -> None:
        expired = [jti for jti, e in self._entries.items() if e.exp <= now_ts]
        for jti in expired:
            del self._entries[jti]
        if expired:
            log.debug(f"Blacklist cleanup: {len(expired)} entradas expiradas eliminadas")


# Singleton
_blacklist = TokenBlacklist()


def revoke_token(jti: str, exp: int) -> None:
    """Marca un token como revocado (logout)."""
    _blacklist.add(jti, exp)


# ─────────────────────────────────────────────────────────────────────
# Generación de tokens
# ─────────────────────────────────────────────────────────────────────

def create_access_token(
    username: str,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Genera un JWT access token.

    Args:
        username: identificador del usuario (sub)
        role: rol del usuario (admin | operator | viewer)
        extra_claims: claims adicionales opcioneles

    Returns:
        JWT codificado como string
    """
    if not JOSE_AVAILABLE:
        raise RuntimeError("python-jose no instalado. No se pueden generar tokens JWT.")

    s = get_settings().security
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=s.jwt_expiration_minutes)
    payload: dict[str, Any] = {
        "sub": username,
        "role": role,
        "token_type": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_hex(16),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_refresh_token(username: str, role: str) -> str:
    """
    Genera un JWT refresh token (vida más larga, solo para refrescar access tokens).
    """
    if not JOSE_AVAILABLE:
        raise RuntimeError("python-jose no instalado.")

    s = get_settings().security
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=s.refresh_expiration_days)
    payload = {
        "sub": username,
        "role": role,
        "token_type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> TokenData | None:
    """
    Decodifica y verifica un JWT. Devuelve None si es inválido/expirado.

    NO usa fallback peligroso: si el token no es JWT válido, devuelve None.
    """
    if not JOSE_AVAILABLE:
        log.error("python-jose no instalado. No se pueden verificar tokens.")
        return None

    s = get_settings().security
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError as e:
        log.debug(f"JWT inválido: {e}")
        return None

    sub = payload.get("sub")
    role = payload.get("role", "viewer")
    token_type = payload.get("token_type", "access")
    exp = int(payload.get("exp", 0))
    jti = payload.get("jti", "")

    if not sub:
        return None

    return TokenData(sub=sub, role=role, token_type=token_type, exp=exp, jti=jti)


# ─────────────────────────────────────────────────────────────────────
# Verificación de credenciales (login)
# ─────────────────────────────────────────────────────────────────────

async def verify_credentials(
    db: AsyncSession,
    username: str,
    password: str,
) -> User | None:
    """
    Verifica credenciales de usuario.

    Returns:
        User si las credenciales son válidas, None si no.
    """
    repo = UserRepository(db)
    user = await repo.get_by_username(username)
    if not user or not user.active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    # Actualizar último login
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    return user


# ─────────────────────────────────────────────────────────────────────
# Dependencies de FastAPI
# ─────────────────────────────────────────────────────────────────────

async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency: obtiene el usuario actual a partir del JWT del header Authorization.

    Lanza 401 si no hay token, token inválido, expirado, o en blacklist.
    Lanza 403 si el usuario está inactivo.

    Si `security.require_auth = False` (modo dev/test), devuelve un usuario
    admin dummy para permitir acceso sin token.
    """
    s = get_settings().security

    # Bypass para modo dev/test
    if not s.require_auth:
        from lbamonitor.core.models import User
        from lbamonitor.utils.helpers import utcnow
        # Devolver admin dummy (sin persistir). Usamos created=utcnow()
        # porque el modelo User usa `created`, no `created_at`.
        return User(
            id=0,
            username="dev-admin",
            role="admin",
            active=True,
            full_name="Dev Admin (no auth)",
            created=utcnow(),
        )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verificar blacklist (logout)
    if token_data.jti and _blacklist.is_revoked(token_data.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revocado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Solo access tokens pueden usarse para autenticar (no refresh)
    if token_data.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tipo de token inválido. Use un access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Cargar usuario desde BD
    repo = UserRepository(db)
    user = await repo.get_by_username(token_data.sub)
    if not user or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inválido o inactivo",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_role(*allowed_roles: str):
    """
    Factory de dependency que requiere uno de los roles indicados.

    Uso:
        @router.delete("/{user_id}")
        async def delete_user(
            user_id: int,
            current: User = Depends(require_role("admin")),
        ):
            ...
    """
    async def _check_role(current: User = Depends(get_current_user)) -> User:
        if current.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operación requiere rol: {', '.join(allowed_roles)}",
            )
        return current
    return _check_role


# Convenience: require admin
require_admin = require_role("admin")
require_operator = require_role("admin", "operator")
