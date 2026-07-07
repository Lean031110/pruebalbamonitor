"""Schemas de sistema: notificaciones, sesiones, cambios de reloj, backups, reportes."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from lbamonitor.api.schemas.common import OrmModel


# ---------------------------------------------------------------------------
# ServiceSession
# ---------------------------------------------------------------------------

class ServiceSessionResponse(OrmModel):
    id: int
    start_date_time: datetime
    end_date_time: Optional[datetime] = None
    alive_date_time: Optional[datetime] = None
    session_time: Optional[int] = None  # seconds


# ---------------------------------------------------------------------------
# PCDatetimeChange
# ---------------------------------------------------------------------------

class PCDatetimeChangeResponse(OrmModel):
    id: int
    moment: datetime
    to: datetime


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

class NotificationResponse(OrmModel):
    id: int
    title: str
    message: Optional[str] = None
    level: str = "info"
    category: str = "usb"
    read: bool = False
    created_at: datetime


class NotificationCreate(BaseModel):
    title: str
    message: Optional[str] = None
    level: str = "info"
    category: str = "usb"


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

class BackupRecordResponse(OrmModel):
    id: int
    file_path: str
    size_bytes: Optional[int] = None
    auto: bool = False
    notes: Optional[str] = None
    created_at: datetime


class BackupTriggerResponse(OrmModel):
    success: bool
    backup: Optional[BackupRecordResponse] = None
    message: str = ""


# ---------------------------------------------------------------------------
# ReportRecord
# ---------------------------------------------------------------------------

class ReportRecordResponse(OrmModel):
    id: int
    name: str
    report_type: str  # daily|monthly|annual|custom
    format: str  # pdf|excel|csv|html
    file_path: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    created_at: datetime
    created_by: Optional[str] = None


class ReportCreateRequest(BaseModel):
    report_type: str  # daily|monthly|annual|custom
    format: str  # pdf|excel|csv|html
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


# ---------------------------------------------------------------------------
# ActivityLog
# ---------------------------------------------------------------------------

class ActivityLogResponse(OrmModel):
    id: int
    user: Optional[str] = None
    action: str
    entity: Optional[str] = None
    entity_id: Optional[int] = None
    details: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# ErrorLog
# ---------------------------------------------------------------------------

class ErrorLogResponse(OrmModel):
    id: int
    level: str = "ERROR"
    module: Optional[str] = None
    message: str
    traceback: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# LogEntry (logs en tiempo real)
# ---------------------------------------------------------------------------

class LogEntry(BaseModel):
    timestamp: str
    level: str
    name: str
    message: str


class LogFile(BaseModel):
    name: str
    path: str
    size_bytes: int
    modified: str
