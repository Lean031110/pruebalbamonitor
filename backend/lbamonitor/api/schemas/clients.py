"""Schemas de clientes, VIP, membresías y recompensas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from lbamonitor.api.schemas.common import OrmModel


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ClientBase(OrmModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    observations: Optional[str] = None


class ClientUpdate(ClientBase):
    photo_path: Optional[str] = None


class ClientResponse(ClientBase):
    id: int
    device_id: int
    photo_path: Optional[str] = None
    visit_count: int
    total_spent: float
    total_gb_copied: float
    first_visit: Optional[datetime] = None
    last_visit: Optional[datetime] = None
    points: int
    tier: str


class ClientSummary(OrmModel):
    """Resumen extendido de un cliente (para vista de detalle)."""

    device_id: int
    alias: Optional[str] = None
    serial: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    client_name: Optional[str] = None
    phone: Optional[str] = None
    tier: str = "bronce"
    points: int = 0
    visit_count: int = 0
    total_spent: float = 0.0
    total_gb: float = 0.0
    first_visit: Optional[datetime] = None
    last_visit: Optional[datetime] = None
    avg_files_per_session: float = 0.0
    avg_gb_per_session: float = 0.0
    avg_duration_seconds: int = 0
    recent_sessions: list[dict] = []
    pending_rewards: list[dict] = []


# ---------------------------------------------------------------------------
# VIPEntry
# ---------------------------------------------------------------------------

class VIPEntryBase(OrmModel):
    vip_type: str = "none"  # none|vip|blocked|never_pays|free|discount|employee|business
    discount_percent: Optional[float] = None
    reason: Optional[str] = None


class VIPEntryCreate(VIPEntryBase):
    device_id: int


class VIPEntryResponse(VIPEntryBase):
    id: int
    device_id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# MembershipLevel
# ---------------------------------------------------------------------------

class MembershipLevelBase(OrmModel):
    tier: str  # bronce|plata|oro|platino|diamante
    min_visits: int = 0
    min_gb: float = 0.0
    min_spent: float = 0.0
    discount_percent: float = 0.0
    color: Optional[str] = None


class MembershipLevelUpdate(OrmModel):
    min_visits: Optional[int] = None
    min_gb: Optional[float] = None
    min_spent: Optional[float] = None
    discount_percent: Optional[float] = None
    color: Optional[str] = None


class MembershipLevelResponse(MembershipLevelBase):
    id: int


class TierDistributionItem(OrmModel):
    tier: str
    count: int


class TierProgress(OrmModel):
    current_tier: str
    next_tier: Optional[str] = None
    at_max: bool = False
    metrics: dict


# ---------------------------------------------------------------------------
# Reward
# ---------------------------------------------------------------------------

class RewardBase(OrmModel):
    reward_type: str  # free|discount|gift|bonus|frequent|month
    description: Optional[str] = None
    value: Optional[float] = None


class RewardCreate(RewardBase):
    device_id: Optional[int] = None
    expires_in_days: Optional[int] = None


class RewardResponse(RewardBase):
    id: int
    device_id: Optional[int] = None
    granted_at: datetime
    expires_at: Optional[datetime] = None
    applied: bool = False


class RewardRuleConfig(OrmModel):
    """Configuración de una regla de recompensa."""

    rule_id: str
    enabled: bool = True
    priority: int = 0
    auto_apply: bool = False
    params: dict = {}
