"""
Configuración central de LBAMonitor.

Lee de `config.toml` (en orden de prioridad):
  1. Ruta indicada por env var `LBAMONITOR_CONFIG`
  2. `./config.toml` (current working dir)
  3. `~/.lbamonitor/config.toml`
  4. `C:/ProgramData/LBAMonitor/config.toml` (Windows)

Y sobreescribe con variables de entorno con prefijo `LBAMONITOR_` (separadas por `__`):
  LBAMONITOR_SERVER__PORT=9000  ->  server.port = 9000
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Secciones tipadas
# ---------------------------------------------------------------------------

class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8123
    workers: int = 1
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8123",
    ])
    docs_enabled: bool = True


class DatabaseSettings(BaseModel):
    engine: str = "sqlite"  # sqlite | postgresql
    path: str = "C:/ProgramData/LBAMonitor/data/lbamonitor.db"
    host: str = "localhost"
    port: int = 5432
    user: str = "lbamonitor"
    password: str = ""
    echo: bool = False


class MonitoringSettings(BaseModel):
    mtp_poll_interval_seconds: int = 5
    fs_watcher_buffer: int = 65536
    fs_debounce_ms: int = 500
    file_type_filters: list[str] = Field(default_factory=list)
    exclude_system_files: bool = True
    exclude_patterns: list[str] = Field(
        default_factory=lambda: ["Thumbs.db", ".DS_Store", "desktop.ini", "~$*", "*.tmp"]
    )


class BackupSettings(BaseModel):
    enabled: bool = True
    hour: int = 3
    keep_days: int = 30
    destination: str = "C:/ProgramData/LBAMonitor/backups"
    on_exit: bool = False


class LoggingSettings(BaseModel):
    level: str = "INFO"
    rotation: str = "1 day"
    retention: str = "30 days"
    path: str = "C:/ProgramData/LBAMonitor/logs"
    console: bool = True


class LicenseSettings(BaseModel):
    mode: str = "trial"
    key: str = ""
    hwid_tolerance: int = 1
    # Secret HMAC para firmar/verificar licencias. Debe cargarse desde env var
    # LBAMONITOR_LICENSE__SIGNING_SECRET o config.toml. Si es "" o el default,
    # el sistema falla al arrancar en modo producción.
    signing_secret: str = ""
    # Par de claves RSA (PEM). Si se provee, se usa RSA-2048 en lugar de HMAC.
    # private_key_pem solo se necesita en tools/license_generator.
    public_key_pem: str = ""
    private_key_pem: str = ""


class SecuritySettings(BaseModel):
    # En v4.3 auth es OBLIGATORIO por defecto. Si se quiere desactivar (solo para tests)
    # usar env var LBAMONITOR_SECURITY__REQUIRE_AUTH=false
    require_auth: bool = True
    # Secret JWT. Debe cargarse desde env var LBAMONITOR_SECURITY__JWT_SECRET
    # o config.toml. Si queda como default, el sistema falla al arrancar en producción.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60
    refresh_expiration_days: int = 7
    # bcrypt password hashing (recomendado). En tests se puede usar pbkdf2.
    password_hash_algo: str = "bcrypt"
    # Lista de paths públicos (sin auth). Se reserva para /api/auth/login y /health.
    public_paths: list[str] = Field(default_factory=lambda: [
        "/api/auth/login",
        "/api/auth/refresh",
        "/health",
        "/api/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    ])


class RateLimitSettings(BaseModel):
    enabled: bool = True
    # Requests por minuto por IP
    default_per_minute: int = 60
    # Login: 5 intentos por minuto por IP (anti brute-force)
    login_per_minute: int = 5
    # Bloqueo temporal tras exceder (segundos)
    block_seconds: int = 60


class CacheSettings(BaseModel):
    enabled: bool = True
    # Máximo número de entradas en caché LRU
    max_entries: int = 1000
    # TTL por defecto (segundos)
    default_ttl: int = 60
    # Limpiar entradas expiradas cada N segundos
    cleanup_interval: int = 300


class AppearanceSettings(BaseModel):
    language: str = "es"
    theme: str = "dark"


class BusinessSettings(BaseModel):
    name: str = "Mi Copistería"
    address: str = ""
    phone: str = ""
    email: str = ""
    currency_code: str = "CUP"
    currency_symbol: str = "₱"
    currency_decimals: int = 2
    tax_percent: float = 0.0


class PricingSettings(BaseModel):
    mode: str = "per_gb"
    price_per_gb: float = 25.0
    price_per_mb: float = 0.05
    price_per_file: float = 1.0
    fixed_price: float = 50.0
    min_price: float = 5.0
    max_price: float = 5000.0
    vip_discount_percent: float = 10.0
    employee_discount_percent: float = 50.0
    promotion_enabled: bool = False
    promotion_description: str = ""
    promotion_discount_percent: float = 0.0


class PathsSettings(BaseModel):
    publicity_folder: str = ""
    publicity_automatic: bool = False
    video_folders: list[str] = Field(default_factory=list)
    exports: str = "C:/ProgramData/LBAMonitor/exports"


class Settings(BaseSettings):
    """Configuración global tipada."""

    model_config = SettingsConfigDict(
        env_prefix="LBAMONITOR_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    backup: BackupSettings = Field(default_factory=BackupSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    license: LicenseSettings = Field(default_factory=LicenseSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    appearance: AppearanceSettings = Field(default_factory=AppearanceSettings)
    business: BusinessSettings = Field(default_factory=BusinessSettings)
    pricing: PricingSettings = Field(default_factory=PricingSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)


# ---------------------------------------------------------------------------
# Localización de archivos de configuración (sistema por capas)
# ---------------------------------------------------------------------------

# 1. Config del usuario (persistente, editable, sobrevive upgrades)
USER_CONFIG_PATHS: list[Path] = [
    Path("config.toml"),
    Path.home() / ".lbamonitor" / "config.toml",
    Path("C:/ProgramData/LBAMonitor/config/config.toml"),
]

# 2. Config por defecto (solo lectura, viene con el instalador)
DEFAULT_CONFIG_PATHS: list[Path] = [
    Path("config.default.toml"),
    Path("C:/Program Files/LBAMonitor/config.default.toml"),
]


def find_user_config() -> Path | None:
    """Localiza el archivo de configuración del usuario (editabe)."""
    env_path = os.environ.get("LBAMONITOR_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
    for p in USER_CONFIG_PATHS:
        if p.is_file():
            return p
    return None


def find_default_config() -> Path | None:
    """Localiza el archivo de configuración por defecto (solo lectura)."""
    for p in DEFAULT_CONFIG_PATHS:
        if p.is_file():
            return p
    return None


def find_config_file() -> Path | None:
    """Compat: devuelve el config del usuario si existe."""
    return find_user_config()


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge recursivo: override gana sobre base."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings() -> Settings:
    """
    Carga la configuración con sistema de capas:

    1. Defaults del código (clases Pydantic)
    2. config.default.toml (solo lectura, viene con el instalador)
    3. config.toml del usuario (persistente, sobrevive upgrades)
    4. Variables de entorno con prefijo LBAMONITOR_ (sobreescribe todo)

    Las env vars siempre ganan sobre el archivo.
    """
    config_data: dict[str, Any] = {}

    # 1. Defaults del instalador
    default_file = find_default_config()
    if default_file:
        try:
            with default_file.open("rb") as f:
                config_data = _deep_merge(config_data, tomllib.load(f))
        except Exception as e:
            # No frenar el arranque por un default corrupto
            print(f"[config] Warning: no se pudo leer {default_file}: {e}")

    # 2. Config del usuario (sobreescribe defaults)
    user_file = find_user_config()
    if user_file:
        try:
            with user_file.open("rb") as f:
                config_data = _deep_merge(config_data, tomllib.load(f))
        except Exception as e:
            print(f"[config] Warning: no se pudo leer {user_file}: {e}")

    # 3. Pydantic-settings: env vars sobreescriben todo
    settings = Settings(**config_data)

    # 4. Validación de seguridad: en producción, secrets obligatorios
    _validate_security(settings)

    return settings


def _validate_security(settings: Settings) -> None:
    """
    Fail-fast si los secrets no están configurados en producción.
    Para desarrollo/tests: setear LBAMONITOR_SECURITY__REQUIRE_AUTH=false
    y usar secrets de prueba.
    """
    # Detectar si estamos en producción (no test, no dev)
    is_production = (
        os.environ.get("LBAMONITOR_ENV", "production").lower() == "production"
        and not os.environ.get("PYTEST_CURRENT_TEST")
    )

    if not is_production:
        # En dev/test: si no hay secrets, generar warnings y usar defaults seguros
        if not settings.security.jwt_secret:
            print("[config] WARNING: jwt_secret vacio. Usando secret de DEV (NO usar en produccion).")
            settings.security.jwt_secret = "dev-only-secret-change-me"
        if not settings.license.signing_secret:
            print("[config] WARNING: license.signing_secret vacio. Usando secret de DEV.")
            settings.license.signing_secret = "dev-only-license-secret"
        return

    # Producción: secrets obligatorios
    errors = []
    if not settings.security.jwt_secret or settings.security.jwt_secret == "dev-only-secret-change-me":
        errors.append(
            "security.jwt_secret no configurado. Setear env var "
            "LBAMONITOR_SECURITY__JWT_SECRET=<secret_aleatorio_64_chars>"
        )
    if not settings.license.signing_secret:
        errors.append(
            "license.signing_secret no configurado. Setear env var "
            "LBAMONITOR_LICENSE__SIGNING_SECRET=<secret_aleatorio_64_chars>"
        )
    if errors:
        msg = "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError(
            f"Configuracion de produccion invalida. Secrets faltantes:\n{msg}\n"
            f"Para desarrollo, setear LBAMONITOR_ENV=development"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton de configuración (cacheado)."""
    return load_settings()


def reload_settings() -> Settings:
    """Fuerza recarga (útil en tests o al guardar config nueva)."""
    get_settings.cache_clear()
    return get_settings()
