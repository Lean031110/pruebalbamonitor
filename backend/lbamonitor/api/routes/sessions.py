"""Router de sesiones del servicio (ServiceSession)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import make_pagination, paginate
from lbamonitor.api.schemas.common import PaginatedResponse
from lbamonitor.api.schemas.system import ServiceSessionResponse
from lbamonitor.core.db import get_db
from lbamonitor.core.models import ServiceSession, User
from lbamonitor.core.security.auth import require_operator

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=PaginatedResponse[ServiceSessionResponse])
@router.get("/", response_model=PaginatedResponse[ServiceSessionResponse], include_in_schema=False)
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(paginate),
    current_user: User = Depends(require_operator),
):
    result = await db.execute(
        select(ServiceSession)
        .order_by(ServiceSession.start_date_time.desc())
        .offset((pagination["page"] - 1) * pagination["page_size"])
        .limit(pagination["page_size"])
    )
    items = list(result.scalars().all())

    from sqlalchemy import func
    total = (await db.execute(select(func.count()).select_from(ServiceSession))).scalar() or 0

    return {
        "items": [ServiceSessionResponse.model_validate(s) for s in items],
        "pagination": make_pagination(pagination["page"], pagination["page_size"], total),
    }


@router.get("/current", response_model=Optional[ServiceSessionResponse])
async def get_current_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Devuelve la sesión activa (sin EndDateTime) si existe."""
    result = await db.execute(
        select(ServiceSession)
        .where(ServiceSession.end_date_time.is_(None))
        .order_by(ServiceSession.start_date_time.desc())
        .limit(1)
    )
    sess = result.scalar_one_or_none()
    if not sess:
        return None
    return ServiceSessionResponse.model_validate(sess)
