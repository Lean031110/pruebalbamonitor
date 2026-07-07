"""Router de catálogo multimedia."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import bad_request, make_pagination, not_found, paginate
from lbamonitor.api.schemas.catalog import (
    CatalogEntryCreate,
    CatalogEntryResponse,
    CatalogEntryUpdate,
)
from lbamonitor.api.schemas.common import MessageResponse, PaginatedResponse
from lbamonitor.core.db import get_db
from lbamonitor.core.models import User
from lbamonitor.core.repositories import CatalogRepository
from lbamonitor.core.security.auth import require_admin, require_operator

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/public", response_model=PaginatedResponse[CatalogEntryResponse])
async def list_catalog_public(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(paginate),
    category: str | None = None,
    query: str | None = None,
):
    """
    Catálogo público (sin auth) — solo entradas activas.

    Usado por la web pública (catálogo de audiovisuales) y el dashboard público.
    """
    repo = CatalogRepository(db)
    entries, total = await repo.list_filtered(
        category=category,
        active_only=True,
        query=query,
        page=pagination["page"],
        page_size=pagination["page_size"],
    )
    return {
        "items": [CatalogEntryResponse.model_validate(e) for e in entries],
        "pagination": make_pagination(pagination["page"], pagination["page_size"], total),
    }


@router.get("", response_model=PaginatedResponse[CatalogEntryResponse])
@router.get("/", response_model=PaginatedResponse[CatalogEntryResponse], include_in_schema=False)
async def list_catalog(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(paginate),
    category: str | None = None,
    active_only: bool = True,
    query: str | None = None,
    current_user: User = Depends(require_operator),
):
    repo = CatalogRepository(db)
    entries, total = await repo.list_filtered(
        category=category,
        active_only=active_only,
        query=query,
        page=pagination["page"],
        page_size=pagination["page_size"],
    )
    return {
        "items": [CatalogEntryResponse.model_validate(e) for e in entries],
        "pagination": make_pagination(pagination["page"], pagination["page_size"], total),
    }


@router.get("/top-copied", response_model=list[CatalogEntryResponse])
async def top_copied(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = CatalogRepository(db)
    entries = await repo.top_copied(limit=limit)
    return [CatalogEntryResponse.model_validate(e) for e in entries]


@router.get("/{entry_id}", response_model=CatalogEntryResponse)
async def get_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = CatalogRepository(db)
    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise not_found(f"Entrada de catálogo {entry_id} no encontrada")
    return CatalogEntryResponse.model_validate(entry)


@router.post("", response_model=CatalogEntryResponse, status_code=201)
async def create_entry(
    payload: CatalogEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    repo = CatalogRepository(db)
    entry = await repo.create(**payload.model_dump())
    await db.commit()
    await db.refresh(entry)
    return CatalogEntryResponse.model_validate(entry)


@router.patch("/{entry_id}", response_model=CatalogEntryResponse)
async def update_entry(
    entry_id: int,
    payload: CatalogEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    repo = CatalogRepository(db)
    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise not_found(f"Entrada {entry_id} no encontrada")
    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(entry, k, v)
    await db.commit()
    await db.refresh(entry)
    return CatalogEntryResponse.model_validate(entry)


@router.delete("/{entry_id}", response_model=MessageResponse)
async def delete_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Soft-delete: marca como inactivo."""
    repo = CatalogRepository(db)
    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise not_found(f"Entrada {entry_id} no encontrada")
    entry.active = False
    await db.commit()
    return MessageResponse(message=f"Entrada {entry_id} desactivada")
