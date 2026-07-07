"""Router de cobros (Billing) y patrones de pago."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import bad_request, make_pagination, not_found, paginate
from lbamonitor.api.schemas.billing import (
    BillingCreate,
    BillingResponse,
    BillingUpdate,
    PaymentPattern,
    PaymentPatternPreviewRequest,
    PaymentPatternPreviewResponse,
    PaymentPatternsResponse,
    PaymentPatternsUpdate,
    PriceCalculationResponse,
)
from lbamonitor.api.schemas.common import PaginatedResponse
from lbamonitor.core.db import get_db
from lbamonitor.core.models import User
from lbamonitor.core.repositories import BillingRepository
from lbamonitor.core.security.auth import require_operator
from lbamonitor.core.services.pricing_engine import get_pricing_engine

router = APIRouter(prefix="/billings", tags=["billings"])


@router.get("", response_model=PaginatedResponse[BillingResponse])
@router.get("/", response_model=PaginatedResponse[BillingResponse], include_in_schema=False)
async def list_billings(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(paginate),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    current_user: User = Depends(require_operator),
):
    repo = BillingRepository(db)
    billings, total = await repo.list_in_range(
        from_date=from_date,
        to_date=to_date,
        page=pagination["page"],
        page_size=pagination["page_size"],
    )
    return {
        "items": [BillingResponse.model_validate(b) for b in billings],
        "pagination": make_pagination(pagination["page"], pagination["page_size"], total),
    }


@router.post("/calculate", response_model=PriceCalculationResponse)
async def calculate_price(
    gb_copied: float = 0.0,
    files_copied: int = 0,
    vip_type: str = "none",
    tier_discount_percent: float = 0.0,
    mode: Optional[str] = None,
    current_user: User = Depends(require_operator),
):
    """Calcula el precio sugerido sin persistirlo."""
    engine = get_pricing_engine()
    calc = engine.calculate(
        mode=mode,
        gb_copied=gb_copied,
        files_copied=files_copied,
        vip_type=vip_type,
        tier_discount_percent=tier_discount_percent,
    )
    return PriceCalculationResponse(**calc.to_dict())


@router.post("", response_model=BillingResponse, status_code=201)
async def create_billing(
    payload: BillingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = BillingRepository(db)
    billing = await repo.create(
        session_id=payload.session_id,
        device_id=None,  # se infiere de la sesión
        pricing_mode=payload.pricing_mode,
        suggested_price=payload.suggested_price,
        discount_percent=payload.discount_percent,
        discount_amount=payload.discount_amount,
        tax_percent=payload.tax_percent,
        tax_amount=payload.tax_amount,
        total=payload.total,
        charged=payload.charged,
        observations=payload.observations,
        not_charged=payload.not_charged,
        created_by=payload.applied_by,
    )
    await db.commit()
    await db.refresh(billing)
    return BillingResponse.model_validate(billing)


# ---------------------------------------------------------------------------
# Patrones de pago automático
# ---------------------------------------------------------------------------

@router.get("/patterns", response_model=PaymentPatternsResponse)
async def get_payment_patterns(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Lee los patrones de pago automático desde key_values."""
    from sqlalchemy import select
    from lbamonitor.core.models import KeyValue
    import json

    result = await db.execute(
        select(KeyValue).where(KeyValue.key == "payment_patterns")
    )
    kv = result.scalar_one_or_none()
    if kv and kv.value:
        try:
            data = json.loads(kv.value)
            return PaymentPatternsResponse(
                patterns=[PaymentPattern(**p) for p in data.get("patterns", [])],
                last_drive_id=data.get("last_drive_id"),
            )
        except Exception:
            pass
    return PaymentPatternsResponse(patterns=[])


@router.put("/patterns", response_model=PaymentPatternsResponse)
async def set_payment_patterns(
    payload: PaymentPatternsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Guarda los patrones de pago automático."""
    from sqlalchemy import select
    from lbamonitor.core.models import KeyValue
    import json

    data = {
        "patterns": [p.model_dump() for p in payload.patterns],
    }
    result = await db.execute(
        select(KeyValue).where(KeyValue.key == "payment_patterns")
    )
    kv = result.scalar_one_or_none()
    if kv:
        kv.value = json.dumps(data)
    else:
        db.add(KeyValue(key="payment_patterns", value=json.dumps(data)))
    await db.commit()
    return PaymentPatternsResponse(patterns=payload.patterns)


@router.post("/patterns/preview", response_model=PaymentPatternPreviewResponse)
async def preview_payment_pattern(
    payload: PaymentPatternPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Simula el pago que se calcularía para N GB copiados."""
    patterns_resp = await get_payment_patterns(db)
    # Encontrar el patrón cuyo GbCopied sea el mayor que se cumple
    matched = None
    for p in sorted(patterns_resp.patterns, key=lambda x: x.gb_copied, reverse=True):
        if payload.gb_copied >= p.gb_copied:
            matched = p
            break
    return PaymentPatternPreviewResponse(
        gb_copied=payload.gb_copied,
        suggested_payment=matched.payment if matched else None,
        matched_pattern=matched,
    )
