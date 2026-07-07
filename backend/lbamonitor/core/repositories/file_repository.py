"""
Repositorios de archivos (Copy, Deletion, FileOperation) + agregados.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.models import Copy, Deletion, FileOperation
from lbamonitor.core.repositories.base import BaseRepository
from lbamonitor.utils.helpers import utcnow


class CopyRepository(BaseRepository[Copy]):
    model = Copy

    async def list_filtered(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        extension: Optional[str] = None,
        category: Optional[str] = None,
        inserted_drive_id: Optional[int] = None,
        session_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Copy], int]:
        q = select(Copy)
        count_q = select(func.count()).select_from(Copy)

        if from_date:
            q = q.where(Copy.copy_date_time >= from_date)
            count_q = count_q.where(Copy.copy_date_time >= from_date)
        if to_date:
            q = q.where(Copy.copy_date_time <= to_date)
            count_q = count_q.where(Copy.copy_date_time <= to_date)
        if extension:
            q = q.where(Copy.extension == extension)
            count_q = count_q.where(Copy.extension == extension)
        if category:
            q = q.where(Copy.category == category)
            count_q = count_q.where(Copy.category == category)
        if inserted_drive_id:
            q = q.where(Copy.inserted_drive_id == inserted_drive_id)
            count_q = count_q.where(Copy.inserted_drive_id == inserted_drive_id)
        if session_id:
            q = q.where(Copy.session_id == session_id)
            count_q = count_q.where(Copy.session_id == session_id)

        total = (await self.session.execute(count_q)).scalar() or 0
        q = q.order_by(Copy.copy_date_time.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(q)
        return list(result.scalars().all()), total

    async def aggregate_by_extension(
        self, from_date: Optional[datetime] = None
    ) -> list[dict]:
        q = (
            select(
                Copy.extension,
                func.count().label("count"),
                func.coalesce(func.sum(Copy.size_bytes), 0).label("total_bytes"),
            )
            .group_by(Copy.extension)
            .order_by(func.count().desc())
        )
        if from_date:
            q = q.where(Copy.copy_date_time >= from_date)
        result = await self.session.execute(q)
        return [
            {"extension": r.extension or "", "count": r.count, "total_bytes": int(r.total_bytes)}
            for r in result.all()
        ]

    async def aggregate_by_day(
        self, days: int = 30
    ) -> list[dict]:
        """Agrega copias por día en los últimos N días."""
        since = utcnow() - timedelta(days=days)
        # SQLite: func.strftime; PostgreSQL: func.date_trunc
        # Usamos func.date que funciona en ambos
        q = (
            select(
                func.date(Copy.copy_date_time).label("date"),
                func.count().label("count"),
                func.coalesce(func.sum(Copy.size_bytes), 0).label("total_bytes"),
            )
            .where(Copy.copy_date_time >= since)
            .group_by(func.date(Copy.copy_date_time))
            .order_by(func.date(Copy.copy_date_time).asc())
        )
        result = await self.session.execute(q)
        return [
            {"date": str(r.date), "count": r.count, "total_bytes": int(r.total_bytes)}
            for r in result.all()
        ]

    async def aggregate_by_hour(self, days: int = 30) -> list[dict]:
        """Agrega copias por hora del día (0-23) en los últimos N días."""
        since = utcnow() - timedelta(days=days)
        q = (
            select(
                func.strftime("%H", Copy.copy_date_time).label("hour"),
                func.count().label("count"),
                func.coalesce(func.sum(Copy.size_bytes), 0).label("total_bytes"),
            )
            .where(Copy.copy_date_time >= since)
            .group_by(func.strftime("%H", Copy.copy_date_time))
            .order_by(func.strftime("%H", Copy.copy_date_time).asc())
        )
        result = await self.session.execute(q)
        return [
            {"hour": int(r.hour), "count": r.count, "total_bytes": int(r.total_bytes)}
            for r in result.all()
        ]

    async def top_files(
        self,
        limit: int = 10,
        period: str = "all",  # all|two-weeks
    ) -> list[dict]:
        """Top archivos más copiados."""
        q = (
            select(
                Copy.file_name,
                func.count().label("count"),
                func.coalesce(func.sum(Copy.size_bytes), 0).label("total_bytes"),
            )
            .where(Copy.file_name.isnot(None))
            .group_by(Copy.file_name)
            .order_by(func.count().desc())
            .limit(limit)
        )
        if period == "two-weeks":
            since = utcnow() - timedelta(days=14)
            q = q.where(Copy.copy_date_time >= since)
        result = await self.session.execute(q)
        return [
            {"file_name": r.file_name, "count": r.count, "total_bytes": int(r.total_bytes)}
            for r in result.all()
        ]


class DeletionRepository(BaseRepository[Deletion]):
    model = Deletion

    async def aggregate_by_extension(
        self, from_date: Optional[datetime] = None
    ) -> list[dict]:
        q = (
            select(
                Deletion.extension,
                func.count().label("count"),
            )
            .group_by(Deletion.extension)
            .order_by(func.count().desc())
        )
        if from_date:
            q = q.where(Deletion.deletion_date_time >= from_date)
        result = await self.session.execute(q)
        return [
            {"extension": r.extension or "", "count": r.count}
            for r in result.all()
        ]


class FileOperationRepository(BaseRepository[FileOperation]):
    model = FileOperation
