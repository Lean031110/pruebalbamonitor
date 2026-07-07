"""Schemas del catálogo multimedia."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from lbamonitor.api.schemas.common import OrmModel


class CatalogEntryBase(OrmModel):
    title: str
    category: str  # movie|series|music|document|game|app|other
    year: Optional[int] = None
    genre: Optional[str] = None
    director: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    size_gb: Optional[float] = None
    rating: Optional[float] = None
    duration_minutes: Optional[int] = None
    cover_path: Optional[str] = None
    file_path: Optional[str] = None
    tags: Optional[str] = None  # CSV
    active: bool = True


class CatalogEntryCreate(CatalogEntryBase):
    pass


class CatalogEntryUpdate(OrmModel):
    title: Optional[str] = None
    category: Optional[str] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    director: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    size_gb: Optional[float] = None
    rating: Optional[float] = None
    duration_minutes: Optional[int] = None
    cover_path: Optional[str] = None
    file_path: Optional[str] = None
    tags: Optional[str] = None
    active: Optional[bool] = None


class CatalogEntryResponse(CatalogEntryBase):
    id: int
    times_copied: int = 0
    created_at: datetime
    updated_at: datetime
