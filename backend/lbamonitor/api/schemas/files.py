"""Schemas de copias y borrados de archivos."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from lbamonitor.api.schemas.common import OrmModel


class CopyResponse(OrmModel):
    id: int
    copy_date_time: datetime
    full_path: str
    extension: Optional[str] = None
    file_name: Optional[str] = None
    size_bytes: Optional[int] = None
    inserted_drive_id: Optional[int] = None
    session_id: Optional[int] = None
    category: Optional[str] = None


class CopyCreate(OrmModel):
    full_path: str
    extension: Optional[str] = None
    file_name: Optional[str] = None
    size_bytes: Optional[int] = None
    inserted_drive_id: Optional[int] = None
    session_id: Optional[int] = None
    category: Optional[str] = None


class DeletionResponse(OrmModel):
    id: int
    deletion_date_time: datetime
    full_path: str
    extension: Optional[str] = None
    file_name: Optional[str] = None
    inserted_drive_id: Optional[int] = None


# Agregados
class CopyByExtension(OrmModel):
    extension: str
    count: int
    total_bytes: int


class CopyByDay(OrmModel):
    date: str  # YYYY-MM-DD
    count: int
    total_bytes: int


class CopyByHour(OrmModel):
    hour: int  # 0-23
    count: int
    total_bytes: int


class TopFile(OrmModel):
    file_name: str
    count: int
    total_bytes: Optional[int] = None
