"""
Enums de dominio de LBAMonitor.

Incluye los enums heredados de Uatcher (FileTypeFilter, OrderCopiesBy)
y los nuevos de LBA USB Manager v3.0 (PricingMode, VIPType, etc.).
"""
from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Uatcher — enums heredados
# ---------------------------------------------------------------------------

class FileTypeFilter(str, Enum):
    """Filtros de tipo de archivo (paridad con Uatcher)."""

    ALL = "all"
    VIDEOS = "videos"
    IMAGES = "images"
    MUSIC = "music"
    DOCUMENTS = "documents"
    APPS = "apps"
    ARCHIVES = "archives"
    OTHERS = "others"


class OrderCopiesBy(str, Enum):
    """Campo por el que ordenar las copias en la UI (paridad con Uatcher)."""

    DATE = "date"
    SIZE = "size"
    NAME = "name"
    EXTENSION = "extension"


# ---------------------------------------------------------------------------
# LBA USB Manager v3.0 — enums nuevos
# ---------------------------------------------------------------------------

class USBConnectionType(str, Enum):
    """Tipo de conexión USB."""

    USB_2 = "usb_2"
    USB_3 = "usb_3"
    USB_C = "usb_c"
    UNKNOWN = "unknown"


class PricingMode(str, Enum):
    """Modo de cálculo de precio."""

    PER_GB = "per_gb"
    PER_MB = "per_mb"
    PER_FILE = "per_file"
    FIXED = "fixed"
    CUSTOM = "custom"


class VIPType(str, Enum):
    """Tipos de tratamiento VIP para un dispositivo/cliente."""

    NONE = "none"
    VIP = "vip"
    BLOCKED = "blocked"
    NEVER_PAYS = "never_pays"
    FREE = "free"
    DISCOUNT = "discount"
    EMPLOYEE = "employee"
    BUSINESS = "business"


class MembershipTier(str, Enum):
    """Niveles de membresía del programa de fidelización."""

    BRONCE = "bronce"
    PLATA = "plata"
    ORO = "oro"
    PLATINO = "platino"
    DIAMANTE = "diamante"


class OperationType(str, Enum):
    """Tipo de operación sobre un archivo."""

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class FileCategory(str, Enum):
    """Categoría automática de un archivo según su extensión."""

    VIDEO = "video"
    MOVIE = "movie"
    SERIES = "series"
    MUSIC = "music"
    DOCUMENT = "document"
    IMAGE = "image"
    GAME = "game"
    APP = "app"
    OTHER = "other"


class UserRole(str, Enum):
    """Roles de usuario."""

    ADMIN = "admin"
    MANAGER = "manager"
    OPERATOR = "operator"


class CatalogCategory(str, Enum):
    """Categorías del catálogo multimedia."""

    MOVIE = "movie"
    SERIES = "series"
    MUSIC = "music"
    DOCUMENT = "document"
    GAME = "game"
    APP = "app"
    OTHER = "other"


class NotificationLevel(str, Enum):
    """Niveles de notificación."""

    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    SUCCESS = "success"


class ReportType(str, Enum):
    """Tipos de reporte."""

    DAILY = "daily"
    MONTHLY = "monthly"
    ANNUAL = "annual"
    CUSTOM = "custom"


class ReportFormat(str, Enum):
    """Formatos de reporte."""

    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    HTML = "html"


class RewardType(str, Enum):
    """Tipos de recompensa del programa de fidelización."""

    FREE = "free"
    DISCOUNT = "discount"
    GIFT = "gift"
    BONUS = "bonus"
    FREQUENT = "frequent"
    MONTH = "month"
