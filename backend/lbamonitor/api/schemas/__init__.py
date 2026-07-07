"""Schemas Pydantic de la API de LBAMonitor."""
from lbamonitor.api.schemas.common import (
    ErrorResponse,
    HealthResponse,
    IdResponse,
    MessageResponse,
    OrmModel,
    PaginatedResponse,
    PaginationInfo,
)
from lbamonitor.api.schemas.users import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from lbamonitor.api.schemas.devices import (
    FileOperationResponse,
    InsertedDriveResponse,
    InsertedDriveUpdate,
    RemovedDriveResponse,
    USBDeviceResponse,
    USBDeviceUpdate,
    USBSessionResponse,
)
from lbamonitor.api.schemas.files import (
    CopyByDay,
    CopyByExtension,
    CopyByHour,
    CopyCreate,
    CopyResponse,
    DeletionResponse,
    TopFile,
)
from lbamonitor.api.schemas.billing import (
    BillingCreate,
    BillingResponse,
    BillingUpdate,
    PaymentAlterationResponse,
    PaymentPattern,
    PaymentPatternPreviewRequest,
    PaymentPatternPreviewResponse,
    PaymentPatternsResponse,
    PaymentPatternsUpdate,
    PaymentUpdateRequest,
    PriceCalculationResponse,
)
from lbamonitor.api.schemas.clients import (
    ClientBase,
    ClientResponse,
    ClientSummary,
    ClientUpdate,
    MembershipLevelBase,
    MembershipLevelResponse,
    MembershipLevelUpdate,
    RewardCreate,
    RewardResponse,
    RewardRuleConfig,
    TierDistributionItem,
    TierProgress,
    VIPEntryCreate,
    VIPEntryResponse,
)
from lbamonitor.api.schemas.catalog import (
    CatalogEntryCreate,
    CatalogEntryResponse,
    CatalogEntryUpdate,
)
from lbamonitor.api.schemas.statistics import (
    BusinessInsights,
    GeneralStatistics,
    HourlyHeatmapPoint,
    KPIs,
    SeriesPoint,
    StatisticsResponse,
    TopClient,
    TopUSB,
)
from lbamonitor.api.schemas.settings import (
    AppearanceSettingsResponse,
    AppearanceSettingsUpdate,
    BackupSettingsResponse,
    BackupSettingsUpdate,
    BusinessInfo,
    ConfigurationResponse,
    ConfigurationUpdate,
    KeyValueResponse,
    KeyValueUpdate,
    LicenseConfigResponse,
    LoggingSettingsResponse,
    LoggingSettingsUpdate,
    LogLine,
    LogsResponse,
    MonitoringSettingsResponse,
    MonitoringSettingsUpdate,
    OrderCopiesBy,
    PricingSettingsResponse,
    PricingSettingsUpdate,
    PublicityFolder,
    RewardRuleCreate,
    RewardRuleResponse,
    RewardRuleUpdate,
    ServerSettingsResponse,
    ServerSettingsUpdate,
    SettingResponse,
    SettingsListResponse,
    VideoFolders,
)
from lbamonitor.api.schemas.license import (
    LicenseActivateRequest,
    LicenseActivateResponse,
    LicenseStatus,
    MachineIDResponse,
)
from lbamonitor.api.schemas.system import (
    ActivityLogResponse,
    BackupRecordResponse,
    BackupTriggerResponse,
    ErrorLogResponse,
    LogEntry,
    LogFile,
    NotificationCreate,
    NotificationResponse,
    PCDatetimeChangeResponse,
    ReportCreateRequest,
    ReportRecordResponse,
    ServiceSessionResponse,
)

__all__ = [
    # common
    "ErrorResponse", "HealthResponse", "IdResponse", "MessageResponse",
    "OrmModel", "PaginatedResponse", "PaginationInfo",
    # users
    "LoginRequest", "LoginResponse", "PasswordChangeRequest",
    "UserCreate", "UserResponse", "UserUpdate",
    # devices
    "FileOperationResponse", "InsertedDriveResponse", "InsertedDriveUpdate",
    "RemovedDriveResponse", "USBDeviceResponse", "USBDeviceUpdate", "USBSessionResponse",
    # files
    "CopyByDay", "CopyByExtension", "CopyByHour", "CopyCreate", "CopyResponse",
    "DeletionResponse", "TopFile",
    # billing
    "BillingCreate", "BillingResponse", "BillingUpdate",
    "PaymentAlterationResponse", "PaymentPattern", "PaymentPatternPreviewRequest",
    "PaymentPatternPreviewResponse", "PaymentPatternsResponse", "PaymentPatternsUpdate",
    "PaymentUpdateRequest", "PriceCalculationResponse",
    # clients
    "ClientBase", "ClientResponse", "ClientSummary", "ClientUpdate",
    "MembershipLevelBase", "MembershipLevelResponse", "MembershipLevelUpdate",
    "RewardCreate", "RewardResponse", "RewardRuleConfig",
    "TierDistributionItem", "TierProgress",
    "VIPEntryCreate", "VIPEntryResponse",
    # catalog
    "CatalogEntryCreate", "CatalogEntryResponse", "CatalogEntryUpdate",
    # statistics
    "BusinessInsights", "GeneralStatistics", "HourlyHeatmapPoint", "KPIs",
    "SeriesPoint", "StatisticsResponse", "TopClient", "TopUSB",
    # settings
    "BusinessInfo", "ConfigurationResponse", "ConfigurationUpdate",
    "KeyValueResponse", "KeyValueUpdate", "OrderCopiesBy", "PublicityFolder",
    "SettingResponse", "SettingsListResponse", "VideoFolders",
    "PricingSettingsResponse", "PricingSettingsUpdate",
    "MonitoringSettingsResponse", "MonitoringSettingsUpdate",
    "BackupSettingsResponse", "BackupSettingsUpdate",
    "LoggingSettingsResponse", "LoggingSettingsUpdate",
    "AppearanceSettingsResponse", "AppearanceSettingsUpdate",
    "ServerSettingsResponse", "ServerSettingsUpdate",
    "LicenseConfigResponse",
    "RewardRuleCreate", "RewardRuleResponse", "RewardRuleUpdate",
    "LogLine", "LogsResponse",
    # license
    "LicenseActivateRequest", "LicenseActivateResponse", "LicenseStatus", "MachineIDResponse",
    # system
    "ActivityLogResponse", "BackupRecordResponse", "BackupTriggerResponse",
    "ErrorLogResponse", "LogEntry", "LogFile",
    "NotificationCreate", "NotificationResponse",
    "PCDatetimeChangeResponse", "ReportCreateRequest", "ReportRecordResponse",
    "ServiceSessionResponse",
]
