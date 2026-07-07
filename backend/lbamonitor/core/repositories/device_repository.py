"""
Repositorio de InsertedDrive (paridad Uatcher) + USBDevice + RemovedDrive.

Incluye:
  - get_or_create_usb_device por fingerprint
  - compute_device_history (PreviousInsertionsCounter, PreviousPaymentsSum)
  - list con filtros avanzados
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.models import Copy, Deletion, InsertedDrive, RemovedDrive, USBDevice
from lbamonitor.core.repositories.base import BaseRepository
from lbamonitor.utils.helpers import utcnow


class USBDeviceRepository(BaseRepository[USBDevice]):
    model = USBDevice

    async def get_by_fingerprint(self, fingerprint: str) -> USBDevice | None:
        result = await self.session.execute(
            select(USBDevice).where(USBDevice.serial_number == fingerprint)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        fingerprint: str,
        name: Optional[str] = None,
        brand: Optional[str] = None,
        model: Optional[str] = None,
        manufacturer: Optional[str] = None,
        vid: Optional[str] = None,
        pid: Optional[str] = None,
        total_capacity: Optional[int] = None,
        connection_type: str = "unknown",
    ) -> USBDevice:
        device = await self.get_by_fingerprint(fingerprint)
        if device:
            # Actualizar last_seen y visit_count
            device.last_seen = utcnow()
            device.visit_count = (device.visit_count or 0) + 1
            device.is_known = True
            await self.session.flush()
            return device

        return await self.create(
            serial_number=fingerprint,
            name=name,
            brand=brand,
            manufacturer=manufacturer,
            model=model,
            vid=vid,
            pid=pid,
            total_capacity=total_capacity,
            connection_type=connection_type,
            first_seen=utcnow(),
            last_seen=utcnow(),
            visit_count=1,
            is_known=True,
        )

    async def search(
        self,
        query: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[USBDevice], int]:
        q = select(USBDevice)
        count_q = select(func.count()).select_from(USBDevice)

        if query:
            pattern = f"%{query}%"
            filt = or_(
                USBDevice.serial_number.ilike(pattern),
                USBDevice.alias.ilike(pattern),
                USBDevice.name.ilike(pattern),
                USBDevice.brand.ilike(pattern),
                USBDevice.model.ilike(pattern),
            )
            q = q.where(filt)
            count_q = count_q.where(filt)

        total = (await self.session.execute(count_q)).scalar() or 0
        q = q.order_by(USBDevice.last_seen.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(q)
        return list(result.scalars().all()), total


class InsertedDriveRepository(BaseRepository[InsertedDrive]):
    model = InsertedDrive

    async def get_active(self) -> list[InsertedDrive]:
        """Devuelve las inserciones que aún no han sido extraídas."""
        result = await self.session.execute(
            select(InsertedDrive)
            .where(InsertedDrive.removed_drive_id.is_(None))
            .order_by(InsertedDrive.insertion_date_time.desc())
        )
        return list(result.scalars().all())

    async def list_with_filters(
        self,
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
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[InsertedDrive], int]:
        """Listado con todos los filtros del historial (paridad Uatcher)."""
        q = select(InsertedDrive)
        count_q = select(func.count()).select_from(InsertedDrive)

        conditions = []
        if device_name:
            conditions.append(InsertedDrive.name.ilike(f"%{device_name}%"))
        if device_serial:
            conditions.append(InsertedDrive.serial_number.ilike(f"%{device_serial}%"))
        if device_model:
            conditions.append(InsertedDrive.model.ilike(f"%{device_model}%"))
        if device_size:
            conditions.append(InsertedDrive.space_bytes == device_size)
        if min_space:
            conditions.append(InsertedDrive.space_bytes >= min_space)
        if max_space:
            conditions.append(InsertedDrive.space_bytes <= max_space)
        if from_date:
            conditions.append(InsertedDrive.insertion_date_time >= from_date)
        if to_date:
            conditions.append(InsertedDrive.insertion_date_time <= to_date)
        if min_payment is not None:
            conditions.append(InsertedDrive.payment >= min_payment)
        if max_payment is not None:
            conditions.append(InsertedDrive.payment <= max_payment)
        if comment_contains:
            pat = f"%{comment_contains}%"
            conditions.append(
                or_(InsertedDrive.comment.ilike(pat), InsertedDrive.comment_fixed.ilike(pat))
            )
        if user_id:
            conditions.append(InsertedDrive.user_id == user_id)
        if is_mobile is not None:
            conditions.append(InsertedDrive.is_mobile == is_mobile)
        if has_payment is True:
            conditions.append(InsertedDrive.payment.isnot(None))
        elif has_payment is False:
            conditions.append(InsertedDrive.payment.is_(None))

        if conditions:
            filt = and_(*conditions)
            q = q.where(filt)
            count_q = count_q.where(filt)

        total = (await self.session.execute(count_q)).scalar() or 0
        q = q.order_by(InsertedDrive.insertion_date_time.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(q)
        return list(result.scalars().all()), total

    async def update_payment(
        self,
        drive: InsertedDrive,
        new_payment: int,
        user_id: Optional[int] = None,
    ) -> "InsertedDrive":
        """Actualiza el pago y registra la alteración."""
        from lbamonitor.core.models import PaymentAlteration

        old_payment = drive.payment
        drive.payment = new_payment

        # Registrar alteración
        alteration = PaymentAlteration(
            inserted_drive_id=drive.id,
            previous_payment=old_payment,
            new_payment=new_payment,
            alteration_date_time=utcnow(),
            user_id=user_id,
        )
        self.session.add(alteration)
        await self.session.flush()
        await self.session.refresh(drive)
        return drive

    async def compute_history(self, fingerprint: str) -> tuple[int, int]:
        """
        Calcula PreviousInsertionsCounter y PreviousPaymentsSum para un
        dispositivo identificado por fingerprint.
        """
        if not fingerprint:
            return 0, 0
        count_r = await self.session.execute(
            select(func.count())
            .select_from(InsertedDrive)
            .where(InsertedDrive.serial_number == fingerprint)
        )
        prev_count = count_r.scalar() or 0

        sum_r = await self.session.execute(
            select(func.coalesce(func.sum(InsertedDrive.payment), 0))
            .where(InsertedDrive.serial_number == fingerprint)
        )
        prev_sum = sum_r.scalar() or 0
        return int(prev_count), int(prev_sum)

    async def get_copies(self, drive_id: int) -> list[Copy]:
        result = await self.session.execute(
            select(Copy)
            .where(Copy.inserted_drive_id == drive_id)
            .order_by(Copy.copy_date_time.desc())
        )
        return list(result.scalars().all())

    async def get_deletions(self, drive_id: int) -> list[Deletion]:
        result = await self.session.execute(
            select(Deletion)
            .where(Deletion.inserted_drive_id == drive_id)
            .order_by(Deletion.deletion_date_time.desc())
        )
        return list(result.scalars().all())


class RemovedDriveRepository(BaseRepository[RemovedDrive]):
    model = RemovedDrive
