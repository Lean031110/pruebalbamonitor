"""Schemas de dispositivos USB / MTP / sesiones."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from lbamonitor.api.schemas.common import OrmModel


# ---------------------------------------------------------------------------
# USB Devices (registro único por fingerprint)
# ---------------------------------------------------------------------------

class USBDeviceBase(OrmModel):
    serial_number: str  # fingerprint compuesto
    alias: Optional[str] = None
    name: Optional[str] = None
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    vid: Optional[str] = None
    pid: Optional[str] = None
    total_capacity: Optional[int] = None
    connection_type: str = "unknown"


class USBDeviceUpdate(OrmModel):
    alias: Optional[str] = None
    is_known: Optional[bool] = None


class USBDeviceResponse(USBDeviceBase):
    id: int
    first_seen: datetime
    last_seen: datetime
    visit_count: int
    is_known: bool


# ---------------------------------------------------------------------------
# InsertedDrive (paridad Uatcher)
# ---------------------------------------------------------------------------

class InsertedDriveBase(OrmModel):
    name: Optional[str] = None
    root_directory: Optional[str] = None
    volume_label: Optional[str] = None
    serial_number: Optional[str] = None
    model: Optional[str] = None
    is_mobile: bool = False
    is_mounted_folder: bool = False


class InsertedDriveUpdate(OrmModel):
    payment: Optional[int] = None
    comment: Optional[str] = None
    comment_fixed: Optional[str] = None
    user_id: Optional[int] = None
    row_color: Optional[int] = None


class InsertedDriveResponse(InsertedDriveBase):
    id: int
    insertion_date_time: datetime
    space_bytes: Optional[int] = None
    available_space_bytes: Optional[int] = None
    available_space_bytes_at_the_end: Optional[int] = None
    payment: Optional[int] = None
    comment: Optional[str] = None
    comment_fixed: Optional[str] = None
    previous_insertions_counter: int = 0
    previous_payments_sum: int = 0
    row_color: int = 0
    removed_drive_id: Optional[int] = None
    user_id: Optional[int] = None
    usb_device_id: Optional[int] = None


# ---------------------------------------------------------------------------
# RemovedDrive
# ---------------------------------------------------------------------------

class RemovedDriveResponse(OrmModel):
    id: int
    removal_date_time: datetime
    name: Optional[str] = None
    root_directory: Optional[str] = None


# ---------------------------------------------------------------------------
# USBSession (LBA v3 — sesión detallada)
# ---------------------------------------------------------------------------

class USBSessionResponse(OrmModel):
    id: int
    device_id: int
    drive_letter: Optional[str] = None
    label: Optional[str] = None
    filesystem: Optional[str] = None
    total_capacity: Optional[int] = None
    free_capacity_at_connect: Optional[int] = None
    free_capacity_at_disconnect: Optional[int] = None
    connected_at: datetime
    disconnected_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    files_copied: int = 0
    files_deleted: int = 0
    bytes_copied: int = 0
    operation_count: int = 0
    avg_speed_mbps: Optional[float] = None
    max_speed_mbps: Optional[float] = None
    count_video: int = 0
    count_movie: int = 0
    count_series: int = 0
    count_music: int = 0
    count_document: int = 0
    count_image: int = 0
    count_game: int = 0
    count_app: int = 0
    count_other: int = 0
    completed: bool = False


# ---------------------------------------------------------------------------
# FileOperation
# ---------------------------------------------------------------------------

class FileOperationResponse(OrmModel):
    id: int
    session_id: int
    operation: str
    file_path: str
    file_name: Optional[str] = None
    file_ext: Optional[str] = None
    file_size: Optional[int] = None
    category: Optional[str] = None
    detected_at: datetime
