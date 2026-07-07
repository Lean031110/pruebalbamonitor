"""Router de copias de archivos y agregados."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import make_pagination, paginate
from lbamonitor.api.schemas.common import PaginatedResponse
from lbamonitor.api.schemas.files import (
    CopyByDay,
    CopyByExtension,
    CopyByHour,
    CopyResponse,
    TopFile,
)
from lbamonitor.core.db import get_db
from lbamonitor.core.models import User
from lbamonitor.core.repositories import CopyRepository
from lbamonitor.core.security.auth import require_operator
from lbamonitor.utils.helpers import utcnow

router = APIRouter(prefix="/copies", tags=["copies"])


@router.get("", response_model=PaginatedResponse[CopyResponse])
@router.get("/", response_model=PaginatedResponse[CopyResponse], include_in_schema=False)
async def list_copies(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(paginate),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    extension: Optional[str] = None,
    category: Optional[str] = None,
    inserted_drive_id: Optional[int] = None,
    session_id: Optional[int] = None,
    current_user: User = Depends(require_operator),
):
    repo = CopyRepository(db)
    copies, total = await repo.list_filtered(
        from_date=from_date,
        to_date=to_date,
        extension=extension,
        category=category,
        inserted_drive_id=inserted_drive_id,
        session_id=session_id,
        page=pagination["page"],
        page_size=pagination["page_size"],
    )
    return {
        "items": [CopyResponse.model_validate(c) for c in copies],
        "pagination": make_pagination(pagination["page"], pagination["page_size"], total),
    }


@router.get("/by-extension", response_model=list[CopyByExtension])
async def copies_by_extension(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = CopyRepository(db)
    since = utcnow() - timedelta(days=days)
    rows = await repo.aggregate_by_extension(from_date=since)
    return rows


@router.get("/by-day", response_model=list[CopyByDay])
async def copies_by_day(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = CopyRepository(db)
    rows = await repo.aggregate_by_day(days=days)
    return rows


@router.get("/by-hour", response_model=list[CopyByHour])
async def copies_by_hour(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = CopyRepository(db)
    rows = await repo.aggregate_by_hour(days=days)
    return rows


@router.get("/top-files", response_model=list[TopFile])
async def top_files(
    limit: int = Query(10, ge=1, le=100),
    period: str = Query("all", pattern="^(all|two-weeks)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = CopyRepository(db)
    return await repo.top_files(limit=limit, period=period)
