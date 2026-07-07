"""Utilidades de seguridad: hashing de contraseñas, generación de seriales, etc."""
from __future__ import annotations

import binascii
import hashlib
import hmac
import os
import re
import secrets
import string
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Parámetros PBKDF2 (igual que LBA USB Manager v3.0 para compatibilidad)
PBKDF2_ITERATIONS = 200_000
HASH_ALGORITHM = "sha256"
SALT_BYTES = 32
HASH_BYTES = 32


# ---------------------------------------------------------------------------
# Timestamps UTC (todas las fechas en BD se guardan en UTC)
# ---------------------------------------------------------------------------

def utcnow() -> datetime:
    """
    Devuelve el timestamp UTC actual con tzinfo.
    Todas las fechas en la BD se guardan en UTC para evitar problemas
    cuando el usuario cambia el reloj del sistema.
    La UI convierte a hora local para mostrar.
    """
    return datetime.now(timezone.utc)


def to_utc(dt: datetime | None) -> datetime | None:
    """Convierte un datetime a UTC. Si es naive, se asume que ya es UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_clock_skew_significant(
    previous: datetime,
    current: datetime,
    threshold_seconds: int = 60,
) -> tuple[bool, int]:
    """
    Compara dos timestamps UTC y determina si el salto es significativo
    (indicador de cambio de reloj del sistema).

    Devuelve (is_significant, delta_seconds).
    """
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    delta = (current - previous).total_seconds()
    return abs(delta) > threshold_seconds, int(delta)


def hash_password(password: str) -> str:
    """
    Hashea una contraseña con PBKDF2-HMAC-SHA256.

    Devuelve formato: `pbkdf2_sha256$iterations$salt_hex$hash_hex`
    (compatible con auth.verify_password de v4.3).
    """
    if not password:
        raise ValueError("La contraseña no puede estar vacía")
    salt = os.urandom(SALT_BYTES)
    h = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM, password.encode("utf-8"), salt, PBKDF2_ITERATIONS, HASH_BYTES
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """
    Verifica una contraseña contra el hash almacenado.

    Formatos soportados:
    - `pbkdf2_sha256$iterations$salt_hex$hash_hex` (v4.3+)
    - `salt_hex$hash_hex` (legacy v3.0/v4.0, sin prefijo)
    - `$2...` (bcrypt, delegado a auth.verify_password)

    Usa `secrets.compare_digest` para evitar timing attacks.
    """
    if not stored or "$" not in stored:
        return False

    # Formato nuevo: pbkdf2_sha256$iterations$salt_hex$hash_hex
    if stored.startswith("pbkdf2_sha256$"):
        try:
            parts = stored.split("$")
            if len(parts) != 4:
                return False
            algo, iterations_str, salt_hex, hash_hex = parts
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(hash_hex)
            iterations = int(iterations_str)
            h = hashlib.pbkdf2_hmac(
                HASH_ALGORITHM, password.encode("utf-8"), salt, iterations, HASH_BYTES
            )
            return secrets.compare_digest(h, expected)
        except (ValueError, binascii.Error):
            return False

    # Formato legacy: salt_hex$hash_hex (sin prefijo, asume PBKDF2 200k iteraciones)
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, binascii.Error):
        return False
    h = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM, password.encode("utf-8"), salt, PBKDF2_ITERATIONS, HASH_BYTES
    )
    return secrets.compare_digest(h, expected)


def upgrade_legacy_hash(password: str, legacy_stored: str) -> str | None:
    """
    Si una password verifica contra un hash legacy (formato salt_hex$hash_hex),
    devuelve un hash nuevo en formato pbkdf2_sha256$... para reemplazar el viejo.

    Returns:
        Nuevo hash si el legacy verifica, None si no.
    """
    if verify_password(password, legacy_stored):
        return hash_password(password)
    return None


def generate_serial(length: int = 16) -> str:
    """Genera un serial alfanumérico aleatorio."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_uuid() -> str:
    """Genera un UUID v4."""
    return str(uuid.uuid4())


def slugify(text: str) -> str:
    """Convierte un texto en slug válido para archivos."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = text.strip("-")
    return text


def ensure_dir(path: str | Path) -> Path:
    """Crea un directorio si no existe. Devuelve el Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def timestamp_filename(prefix: str = "", ext: str = "") -> str:
    """
    Genera un nombre de archivo con timestamp UTC.

    Ej: timestamp_filename("recibo", "png") -> "recibo_20260705_143025.png"
    """
    ts = utcnow().strftime("%Y%m%d_%H%M%S")
    name = f"{prefix}_{ts}" if prefix else ts
    return f"{name}.{ext.lstrip('.')}" if ext else name


def now_iso() -> str:
    """Devuelve el timestamp UTC actual en ISO 8601 con tzinfo."""
    return utcnow().isoformat()


def safe_str(value, default: str = "", max_len: int = 0) -> str:
    """Convierte a string de forma segura."""
    if value is None:
        return default
    try:
        s = str(value)
    except Exception:
        return default
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s


# ---------------------------------------------------------------------------
# Machine ID (para licencias)
# ---------------------------------------------------------------------------

def sha256_hex(data: str | bytes) -> str:
    """SHA-256 hex digest."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hmac_sha256_hex(secret: str | bytes, data: str | bytes) -> str:
    """HMAC-SHA256 hex digest."""
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hmac.new(secret, data, hashlib.sha256).hexdigest()
