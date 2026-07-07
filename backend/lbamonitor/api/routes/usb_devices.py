"""Router de USBDevices (registro único por fingerprint)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import make_pagination, not_found, paginate
from lbamonitor.api.schemas.common import PaginatedResponse
from lbamonitor.api.schemas.devices import USBDeviceResponse, USBDeviceUpdate
from lbamonitor.core.db import get_db
from lbamonitor.core.models import User
from lbamonitor.core.repositories import USBDeviceRepository
from lbamonitor.core.security.auth import require_operator

router = APIRouter(prefix="/usb-devices", tags=["usb-devices"])


@router.get("", response_model=PaginatedResponse[USBDeviceResponse])
@router.get("/", response_model=PaginatedResponse[USBDeviceResponse], include_in_schema=False)
async def list_devices(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(paginate),
    query: str | None = None,
    current_user: User = Depends(require_operator),
):
    repo = USBDeviceRepository(db)
    devices, total = await repo.search(query=query, **pagination)
    return {
        "items": [USBDeviceResponse.model_validate(d) for d in devices],
        "pagination": make_pagination(pagination["page"], pagination["page_size"], total),
    }


@router.get("/{device_id}", response_model=USBDeviceResponse)
async def get_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = USBDeviceRepository(db)
    device = await repo.get_by_id(device_id)
    if not device:
        raise not_found(f"Dispositivo {device_id} no encontrado")
    return USBDeviceResponse.model_validate(device)


@router.patch("/{device_id}", response_model=USBDeviceResponse)
async def update_device(
    device_id: int,
    payload: USBDeviceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = USBDeviceRepository(db)
    device = await repo.get_by_id(device_id)
    if not device:
        raise not_found(f"Dispositivo {device_id} no encontrado")
    if payload.alias is not None:
        device.alias = payload.alias
    if payload.is_known is not None:
        device.is_known = payload.is_known
    await db.commit()
    await db.refresh(device)
    return USBDeviceResponse.model_validate(device)
