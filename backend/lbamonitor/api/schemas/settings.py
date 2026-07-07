"""Schemas de settings (KeyValue + Configuration + BusinessInfo + PublicityFolder)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from lbamonitor.api.schemas.common import OrmModel


class KeyValueResponse(OrmModel):
    id: int
    key: str
    value: Optional[str] = None


class KeyValueUpdate(BaseModel):
    value: str


class ConfigurationResponse(OrmModel):
    id: int
    section: str
    key: str
    value: Optional[str] = None
    value_type: str = "str"
    updated_at: Optional[str] = None


class ConfigurationUpdate(BaseModel):
    value: str
    value_type: Optional[str] = None  # str|int|float|bool|json


# ---------------------------------------------------------------------------
# Tipos compuestos persistidos en KeyValue
# ---------------------------------------------------------------------------

class BusinessInfo(OrmModel):
    name: str = "Mi Copistería"
    marketing_text: str = ""
    address: str = ""


class PublicityFolder(OrmModel):
    folder_path: str = ""
    automatic: bool = False


class VideoFolders(OrmModel):
    folders: list[str] = []


class OrderCopiesBy(OrmModel):
    value: str = "date"  # date|size|name|extension


class SettingResponse(OrmModel):
    """Respuesta genérica de una setting."""

    key: str
    value: Any
    type: str = "str"


class SettingsListResponse(OrmModel):
    settings: list[SettingResponse]


# ---------------------------------------------------------------------------
# Schemas por sección — espejan las clases de core/config.py
# (Pricing / Monitoring / Backup / Logging / Appearance / Server / License)
# ---------------------------------------------------------------------------

# Pricing ---------------------------------------------------------------------

class PricingSettingsResponse(BaseModel):
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


class PricingSettingsUpdate(BaseModel):
    """Todos los campos opcionales — solo se actualizan los enviados."""

    mode: Optional[str] = Field(default=None, description="per_gb|per_mb|per_file|fixed|custom")
    price_per_gb: Optional[float] = None
    price_per_mb: Optional[float] = None
    price_per_file: Optional[float] = None
    fixed_price: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    vip_discount_percent: Optional[float] = None
    employee_discount_percent: Optional[float] = None
    promotion_enabled: Optional[bool] = None
    promotion_description: Optional[str] = None
    promotion_discount_percent: Optional[float] = None


# Monitoring ------------------------------------------------------------------

class MonitoringSettingsResponse(BaseModel):
    mtp_poll_interval_seconds: int = 5
    fs_watcher_buffer: int = 65536
    fs_debounce_ms: int = 500
    file_type_filters: list[str] = Field(default_factory=list)
    exclude_system_files: bool = True
    exclude_patterns: list[str] = Field(default_factory=list)


class MonitoringSettingsUpdate(BaseModel):
    mtp_poll_interval_seconds: Optional[int] = None
    fs_watcher_buffer: Optional[int] = None
    fs_debounce_ms: Optional[int] = None
    file_type_filters: Optional[list[str]] = None
    exclude_system_files: Optional[bool] = None
    exclude_patterns: Optional[list[str]] = None


# Backup ----------------------------------------------------------------------

class BackupSettingsResponse(BaseModel):
    enabled: bool = True
    hour: int = 3
    keep_days: int = 30
    destination: str = ""
    on_exit: bool = False


class BackupSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    hour: Optional[int] = None
    keep_days: Optional[int] = None
    destination: Optional[str] = None
    on_exit: Optional[bool] = None


# Logging ---------------------------------------------------------------------

class LoggingSettingsResponse(BaseModel):
    level: str = "INFO"
    rotation: str = "1 day"
    retention: str = "30 days"
    path: str = ""
    console: bool = True


class LoggingSettingsUpdate(BaseModel):
    level: Optional[str] = None
    rotation: Optional[str] = None
    retention: Optional[str] = None
    path: Optional[str] = None
    console: Optional[bool] = None


# Appearance ------------------------------------------------------------------

class AppearanceSettingsResponse(BaseModel):
    language: str = "es"
    theme: str = "dark"


class AppearanceSettingsUpdate(BaseModel):
    language: Optional[str] = None
    theme: Optional[str] = None


# Server ----------------------------------------------------------------------

class ServerSettingsResponse(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8123
    workers: int = 1
    cors_origins: list[str] = Field(default_factory=list)
    docs_enabled: bool = True


class ServerSettingsUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    workers: Optional[int] = None
    cors_origins: Optional[list[str]] = None
    docs_enabled: Optional[bool] = None


# License config (read-only, activation goes through /license/activate) -------

class LicenseConfigResponse(BaseModel):
    mode: str = "trial"
    hwid_tolerance: int = 1
    has_key: bool = False
    has_signing_secret: bool = False
    has_public_key: bool = False
    has_private_key: bool = False


# ---------------------------------------------------------------------------
# RewardRule — reglas de recompensa configurables (persistidas como JSON en KV)
# ---------------------------------------------------------------------------

class RewardRuleBase(BaseModel):
    """Esquema base de una regla de recompensa.

    Una RewardRule define condiciones y acciones para otorgar recompensas
    automáticamente a clientes. Se persiste como JSON en la KeyValue store
    (clave `reward_rules`) para evitar migraciones de DB.
    """

    rule_id: str = Field(..., description="Identificador único de la regla, ej. 'frequent_client_30d'")
    name: str = Field(..., description="Nombre humano")
    enabled: bool = True
    priority: int = 0
    auto_apply: bool = False
    trigger: str = Field(
        ...,
        description="Evento disparador: session_end | visit_milestone | gb_milestone | spent_milestone | monthly | manual",
    )
    condition: dict = Field(
        default_factory=dict,
        description="Condición JSON, ej. {'min_visits': 10, 'min_gb': 50}",
    )
    reward_type: str = Field(
        ...,
        description="free | discount | gift | bonus | frequent | month",
    )
    reward_value: Optional[float] = Field(
        default=None,
        description="Valor numérico (p. ej. % descuento o monto fijo)",
    )
    description: Optional[str] = None
    expires_in_days: Optional[int] = None


class RewardRuleCreate(RewardRuleBase):
    pass


class RewardRuleUpdate(BaseModel):
    """Todos los campos opcionales — solo se actualizan los enviados."""

    name: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    auto_apply: Optional[bool] = None
    trigger: Optional[str] = None
    condition: Optional[dict] = None
    reward_type: Optional[str] = None
    reward_value: Optional[float] = None
    description: Optional[str] = None
    expires_in_days: Optional[int] = None


class RewardRuleResponse(RewardRuleBase):
    """Respuesta de una regla de recompensa (idem a base, pero semántica de salida)."""

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Logs (admin)
# ---------------------------------------------------------------------------

class LogLine(BaseModel):
    """Una línea de log parseada."""

    timestamp: str
    level: str
    module: str
    message: str


class LogsResponse(BaseModel):
    """Respuesta paginada/filtrada de logs."""

    file: str
    level: str
    search: Optional[str] = None
    total: int
    limit: int
    items: list[LogLine]
