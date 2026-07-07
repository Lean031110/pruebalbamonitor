"""Schemas de cobros, pagos y alteraciones."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from lbamonitor.api.schemas.common import OrmModel


# ---------------------------------------------------------------------------
# Pricing (cálculo, no persistido)
# ---------------------------------------------------------------------------

class PriceCalculationResponse(OrmModel):
    """Resultado del cálculo de precio para una sesión."""

    base_price: float
    pricing_mode: str
    discount_percent: float = 0.0
    discount_amount: float = 0.0
    discount_reason: Optional[str] = None
    subtotal: float
    tax_percent: float = 0.0
    tax_amount: float = 0.0
    suggested_price: float
    min_applied: Optional[float] = None
    max_applied: Optional[float] = None
    breakdown: dict = {}


# ---------------------------------------------------------------------------
# Billing (cobro persistido)
# ---------------------------------------------------------------------------

class BillingBase(OrmModel):
    session_id: int
    pricing_mode: Optional[str] = None
    suggested_price: Optional[float] = None
    observations: Optional[str] = None


class BillingCreate(BillingBase):
    charged: float
    discount_percent: float = 0.0
    discount_amount: float = 0.0
    tax_percent: float = 0.0
    tax_amount: float = 0.0
    total: float
    not_charged: bool = False
    applied_by: Optional[str] = None


class BillingUpdate(OrmModel):
    charged: Optional[float] = None
    observations: Optional[str] = None
    not_charged: Optional[bool] = None


class BillingResponse(BillingBase):
    id: int
    device_id: Optional[int] = None
    discount_percent: float = 0.0
    discount_amount: float = 0.0
    tax_percent: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0
    charged: Optional[float] = None
    not_charged: bool = False
    created_at: datetime
    created_by: Optional[str] = None


# ---------------------------------------------------------------------------
# PaymentAlteration (paridad Uatcher)
# ---------------------------------------------------------------------------

class PaymentAlterationResponse(OrmModel):
    id: int
    previous_payment: Optional[int] = None
    new_payment: Optional[int] = None
    alteration_date_time: datetime
    inserted_drive_id: int
    user_id: Optional[int] = None


class PaymentUpdateRequest(BaseModel):
    """Request para actualizar el pago de un InsertedDrive."""

    payment: int
    user_id: Optional[int] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Patrones de pago automático
# ---------------------------------------------------------------------------

class PaymentPattern(OrmModel):
    """Un patrón: si se copian >= GbCopied GB, el pago es `Payment`."""

    gb_copied: float
    payment: int


class PaymentPatternsResponse(OrmModel):
    patterns: list[PaymentPattern]
    last_drive_id: Optional[int] = None


class PaymentPatternsUpdate(BaseModel):
    patterns: list[PaymentPattern]


class PaymentPatternPreviewRequest(BaseModel):
    gb_copied: float


class PaymentPatternPreviewResponse(OrmModel):
    gb_copied: float
    suggested_payment: Optional[int] = None
    matched_pattern: Optional[PaymentPattern] = None
