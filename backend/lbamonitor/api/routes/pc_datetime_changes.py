"""Router de cambios de reloj del PC (PCDatetimeChange)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import make_pagination, paginate
from lbamonitor.api.schemas.common import PaginatedResponse
from lbamonitor.api.schemas.system import PCDatetimeChangeResponse
from lbamonitor.core.db import get_db
from lbamonitor.core.models import PCDatetimeChange, User
from lbamonitor.core.security.auth import require_operator

router = APIRouter(prefix="/pc-datetime-changes", tags=["pc-datetime-changes"])


@router.get("", response_model=PaginatedResponse[PCDatetimeChangeResponse])
@router.get("/", response_model=PaginatedResponse[PCDatetimeChangeResponse], include_in_schema=False)
async def list_changes(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(paginate),
    current_user: User = Depends(require_operator),
):
    from sqlalchemy import func
    total = (await db.execute(select(func.count()).select_from(PCDatetimeChange))).scalar() or 0
    result = await db.execute(
        select(PCDatetimeChange)
        .order_by(PCDatetimeChange.moment.desc())
        .offset((pagination["page"] - 1) * pagination["page_size"])
        .limit(pagination["page_size"])
    )
    items = list(result.scalars().all())
    return {
        "items": [PCDatetimeChangeResponse.model_validate(c) for c in items],
        "pagination": make_pagination(pagination["page"], pagination["page_size"], total),
    }
