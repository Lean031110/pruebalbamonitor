"""Router de InsertedDrives (paridad Uatcher) + copias y borrados relacionados."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import bad_request, make_pagination, not_found, paginate
from lbamonitor.api.schemas.common import MessageResponse, PaginatedResponse
from lbamonitor.api.schemas.billing import PaymentAlterationResponse, PaymentUpdateRequest
from lbamonitor.api.schemas.devices import InsertedDriveResponse, InsertedDriveUpdate
from lbamonitor.api.schemas.files import CopyResponse, DeletionResponse
from lbamonitor.core.db import get_db
from lbamonitor.core.models import User
from lbamonitor.core.repositories import InsertedDriveRepository
from lbamonitor.core.security.auth import require_operator

router = APIRouter(prefix="/inserted-drives", tags=["inserted-drives"])


@router.get("", response_model=PaginatedResponse[InsertedDriveResponse])
@router.get("/", response_model=PaginatedResponse[InsertedDriveResponse], include_in_schema=False)
async def list_inserted_drives(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(paginate),
    device_name: Optional[str] = None,
    device_serial: Optional[str] = None,
    device_model: Optional[str] = None,
    device_size: Optional[int] = None,
    min_space: Optional[int] = None,
    max_space: Optional[int] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    min_payment: Optional[int] = None,
    max_payment: Optional[int] = None,
    comment_contains: Optional[str] = None,
    user_id: Optional[int] = None,
    is_mobile: Optional[bool] = None,
    has_payment: Optional[bool] = None,
    current_user: User = Depends(require_operator),
):
    """Listado con filtros avanzados del historial (paridad Uatcher)."""
    repo = InsertedDriveRepository(db)
    drives, total = await repo.list_with_filters(
        device_name=device_name,
        device_serial=device_serial,
        device_model=device_model,
        device_size=device_size,
        min_space=min_space,
        max_space=max_space,
        from_date=from_date,
        to_date=to_date,
        min_payment=min_payment,
        max_payment=max_payment,
        comment_contains=comment_contains,
        user_id=user_id,
        is_mobile=is_mobile,
        has_payment=has_payment,
        page=pagination["page"],
        page_size=pagination["page_size"],
    )
    return {
        "items": [InsertedDriveResponse.model_validate(d) for d in drives],
        "pagination": make_pagination(pagination["page"], pagination["page_size"], total),
    }


@router.get("/active", response_model=list[InsertedDriveResponse])
async def list_active_drives(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Dispositivos actualmente insertados (sin RemovedDrive)."""
    repo = InsertedDriveRepository(db)
    drives = await repo.get_active()
    return [InsertedDriveResponse.model_validate(d) for d in drives]


@router.get("/{drive_id}", response_model=InsertedDriveResponse)
async def get_inserted_drive(
    drive_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = InsertedDriveRepository(db)
    drive = await repo.get_by_id(drive_id)
    if not drive:
        raise not_found(f"Inserción {drive_id} no encontrada")
    return InsertedDriveResponse.model_validate(drive)


@router.patch("/{drive_id}", response_model=InsertedDriveResponse)
async def update_inserted_drive(
    drive_id: int,
    payload: InsertedDriveUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = InsertedDriveRepository(db)
    drive = await repo.get_by_id(drive_id)
    if not drive:
        raise not_found(f"Inserción {drive_id} no encontrada")

    updates = payload.model_dump(exclude_unset=True)
    if "comment" in updates:
        drive.comment = updates["comment"]
    if "comment_fixed" in updates:
        drive.comment_fixed = updates["comment_fixed"]
    if "user_id" in updates:
        drive.user_id = updates["user_id"]
    if "row_color" in updates:
        drive.row_color = updates["row_color"]
    if "payment" in updates:
        # Actualizar pago (genera PaymentAlteration)
        drive = await repo.update_payment(drive, updates["payment"], updates.get("user_id"))

    await db.commit()
    await db.refresh(drive)
    return InsertedDriveResponse.model_validate(drive)


@router.patch("/{drive_id}/payment", response_model=InsertedDriveResponse)
async def update_payment(
    drive_id: int,
    payload: PaymentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Actualiza solo el pago (genera PaymentAlteration para trazabilidad)."""
    repo = InsertedDriveRepository(db)
    drive = await repo.get_by_id(drive_id)
    if not drive:
        raise not_found(f"Inserción {drive_id} no encontrada")
    drive = await repo.update_payment(drive, payload.payment, payload.user_id)
    await db.commit()
    await db.refresh(drive)
    return InsertedDriveResponse.model_validate(drive)


@router.get("/{drive_id}/copies", response_model=list[CopyResponse])
async def get_drive_copies(
    drive_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = InsertedDriveRepository(db)
    drive = await repo.get_by_id(drive_id)
    if not drive:
        raise not_found(f"Inserción {drive_id} no encontrada")
    copies = await repo.get_copies(drive_id)
    return [CopyResponse.model_validate(c) for c in copies]


@router.get("/{drive_id}/deletions", response_model=list[DeletionResponse])
async def get_drive_deletions(
    drive_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = InsertedDriveRepository(db)
    drive = await repo.get_by_id(drive_id)
    if not drive:
        raise not_found(f"Inserción {drive_id} no encontrada")
    deletions = await repo.get_deletions(drive_id)
    return [DeletionResponse.model_validate(d) for d in deletions]


@router.get("/{drive_id}/payment-alterations", response_model=list[PaymentAlterationResponse])
async def get_drive_payment_alterations(
    drive_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    from lbamonitor.core.repositories import PaymentAlterationRepository
    repo = PaymentAlterationRepository(db)
    alterations = await repo.list_by_drive(drive_id)
    return [PaymentAlterationResponse.model_validate(a) for a in alterations]


@router.get("/{drive_id}/invoice.png")
async def get_drive_invoice_png(
    drive_id: int,
    include_webcam: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Genera y devuelve la factura en formato PNG."""
    from fastapi.responses import Response
    from lbamonitor.core.services.invoice_engine import generate_invoice_image

    repo = InsertedDriveRepository(db)
    drive = await repo.get_by_id(drive_id)
    if not drive:
        raise not_found(f"Inserción {drive_id} no encontrada")

    copies = await repo.get_copies(drive_id)
    copies_data = [
        {
            "file_name": c.file_name,
            "size_bytes": c.size_bytes or 0,
            "extension": c.extension,
            "copy_date_time": c.copy_date_time,
        }
        for c in copies
    ]

    png_bytes = await generate_invoice_image(
        drive_id=drive.id,
        drive_name=drive.name or "",
        drive_serial=drive.serial_number,
        drive_model=drive.model,
        copies=copies_data,
        payment=drive.payment,
        include_webcam=include_webcam,
    )
    return Response(content=png_bytes, media_type="image/png",
                    headers={"Content-Disposition": f"inline; filename=invoice_{drive_id}.png"})
