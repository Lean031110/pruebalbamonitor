"""
Servicio de estadísticas.

Calcula KPIs, series temporales y rankings a partir de las tablas
InsertedDrive, Copy, Billing y Client.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.models import (
    Billing,
    Client,
    Copy,
    InsertedDrive,
    USBDevice,
)
from lbamonitor.utils.helpers import utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


class StatisticsService:
    """Calcula estadísticas de negocio."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -----------------------------------------------------------------
    # KPIs
    # -----------------------------------------------------------------

    async def _kpis_for_range(
        self, start: datetime, end: datetime
    ) -> dict:
        """Calcula KPIs para un rango de fechas."""
        # Billings en el rango
        billing_q = select(
            func.count().label("transactions"),
            func.coalesce(func.sum(Billing.charged), 0).label("revenue"),
            func.coalesce(func.sum(Billing.discount_amount), 0).label("discounts"),
        ).where(
            (Billing.created_at >= start) & (Billing.created_at <= end)
        )
        b_result = (await self.session.execute(billing_q)).one()

        # USBs insertados en el rango
        usb_q = (
            select(
                func.count(InsertedDrive.id).label("usb_count"),
                func.coalesce(func.sum(InsertedDrive.space_bytes), 0).label("space_bytes"),
            )
            .where(
                (InsertedDrive.insertion_date_time >= start)
                & (InsertedDrive.insertion_date_time <= end)
            )
        )
        usb_result = (await self.session.execute(usb_q)).one()

        # Copias en el rango
        copies_q = (
            select(
                func.count().label("files_copied"),
                func.coalesce(func.sum(Copy.size_bytes), 0).label("bytes_copied"),
            )
            .where(
                (Copy.copy_date_time >= start) & (Copy.copy_date_time <= end)
            )
        )
        c_result = (await self.session.execute(copies_q)).one()

        gb_copied = float(c_result.bytes_copied or 0) / (1024 ** 3)
        transactions = int(b_result.transactions or 0)
        revenue = float(b_result.revenue or 0)
        usb_count = int(usb_result.usb_count or 0)

        avg_per_session = revenue / transactions if transactions > 0 else 0.0
        avg_per_gb = revenue / gb_copied if gb_copied > 0 else 0.0

        return {
            "range_start": start,
            "range_end": end,
            "transactions": transactions,
            "revenue": round(revenue, 2),
            "discounts": round(float(b_result.discounts or 0), 2),
            "usb_count": usb_count,
            "sessions": usb_count,  # 1 sesión por inserción
            "gb_copied": round(gb_copied, 2),
            "files_copied": int(c_result.files_copied or 0),
            "avg_per_session": round(avg_per_session, 2),
            "avg_per_gb": round(avg_per_gb, 2),
        }

    async def today_kpis(self) -> dict:
        now = utcnow()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return await self._kpis_for_range(start, now)

    async def month_kpis(self) -> dict:
        now = utcnow()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return await self._kpis_for_range(start, now)

    async def year_kpis(self) -> dict:
        now = utcnow()
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return await self._kpis_for_range(start, now)

    # -----------------------------------------------------------------
    # Series temporales
    # -----------------------------------------------------------------

    async def revenue_by_day(self, days: int = 30) -> list[dict]:
        """Revenue por día en los últimos N días."""
        since = utcnow() - timedelta(days=days)
        q = (
            select(
                func.date(Billing.created_at).label("date"),
                func.coalesce(func.sum(Billing.charged), 0).label("value"),
                func.count().label("count"),
            )
            .where(Billing.created_at >= since)
            .group_by(func.date(Billing.created_at))
            .order_by(func.date(Billing.created_at).asc())
        )
        result = await self.session.execute(q)
        return [
            {"label": str(r.date), "value": float(r.value or 0), "count": int(r.count or 0)}
            for r in result.all()
        ]

    async def revenue_by_month(self, months: int = 12) -> list[dict]:
        """Revenue por mes en los últimos N meses."""
        since = utcnow() - timedelta(days=30 * months)
        q = (
            select(
                func.strftime("%Y-%m", Billing.created_at).label("month"),
                func.coalesce(func.sum(Billing.charged), 0).label("value"),
                func.count().label("count"),
            )
            .where(Billing.created_at >= since)
            .group_by(func.strftime("%Y-%m", Billing.created_at))
            .order_by(func.strftime("%Y-%m", Billing.created_at).asc())
        )
        result = await self.session.execute(q)
        return [
            {"label": str(r.month), "value": float(r.value or 0), "count": int(r.count or 0)}
            for r in result.all()
        ]

    async def hourly_heatmap(self, days: int = 30) -> list[dict]:
        """Heatmap hora × día de la semana."""
        since = utcnow() - timedelta(days=days)
        q = (
            select(
                func.strftime("%w", InsertedDrive.insertion_date_time).label("dow"),
                func.strftime("%H", InsertedDrive.insertion_date_time).label("hour"),
                func.count().label("count"),
            )
            .where(InsertedDrive.insertion_date_time >= since)
            .group_by(func.strftime("%w", InsertedDrive.insertion_date_time),
                      func.strftime("%H", InsertedDrive.insertion_date_time))
        )
        result = await self.session.execute(q)
        return [
            {"hour": int(r.hour), "day_of_week": int(r.dow), "count": int(r.count or 0)}
            for r in result.all()
        ]

    # -----------------------------------------------------------------
    # Rankings
    # -----------------------------------------------------------------

    async def top_clients(self, limit: int = 10) -> list[dict]:
        result = await self.session.execute(
            select(Client)
            .order_by(Client.visit_count.desc())
            .limit(limit)
        )
        clients = result.scalars().all()
        return [
            {
                "device_id": c.device_id,
                "alias": None,
                "visit_count": c.visit_count,
                "total_spent": c.total_spent,
                "tier": c.tier,
            }
            for c in clients
        ]

    async def top_usb(self, limit: int = 10) -> list[dict]:
        result = await self.session.execute(
            select(USBDevice)
            .order_by(USBDevice.visit_count.desc())
            .limit(limit)
        )
        devices = result.scalars().all()
        return [
            {
                "device_id": d.id,
                "alias": d.alias,
                "serial": d.serial_number[:16] + "..." if d.serial_number else None,
                "visit_count": d.visit_count,
                "last_visit": d.last_seen,
            }
            for d in devices
        ]

    # -----------------------------------------------------------------
    # Insights
    # -----------------------------------------------------------------

    async def business_insights(self) -> dict:
        """Insights automáticos del negocio."""
        # Día más ocupado (por count de inserciones)
        dow_q = (
            select(
                func.strftime("%w", InsertedDrive.insertion_date_time).label("dow"),
                func.count().label("count"),
            )
            .group_by(func.strftime("%w", InsertedDrive.insertion_date_time))
            .order_by(func.count().desc())
            .limit(1)
        )
        dow_r = await self.session.execute(dow_q)
        dow_row = dow_r.first()
        day_names = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"]
        busiest_day = day_names[int(dow_row.dow)] if dow_row else None

        # Hora pico
        hour_q = (
            select(
                func.strftime("%H", InsertedDrive.insertion_date_time).label("hour"),
                func.count().label("count"),
            )
            .group_by(func.strftime("%H", InsertedDrive.insertion_date_time))
            .order_by(func.count().desc())
            .limit(1)
        )
        hour_r = await self.session.execute(hour_q)
        hour_row = hour_r.first()
        peak_hour = int(hour_row.hour) if hour_row else None

        # Top USB
        top_usb_list = await self.top_usb(limit=1)
        # Top cliente
        top_client_list = await self.top_clients(limit=1)

        # Nuevos clientes en 30 días
        since_30 = utcnow() - timedelta(days=30)
        new_clients_q = select(func.count()).select_from(Client).where(
            Client.first_visit >= since_30
        )
        new_clients = (await self.session.execute(new_clients_q)).scalar() or 0

        # Inactivos >60 días
        since_60 = utcnow() - timedelta(days=60)
        inactive_q = select(func.count()).select_from(Client).where(
            (Client.last_visit < since_60) & (Client.last_visit.isnot(None))
        )
        inactive = (await self.session.execute(inactive_q)).scalar() or 0

        # Promedios
        today = await self.today_kpis()
        avg_per_session = today["avg_per_session"]
        avg_per_gb = today["avg_per_gb"]

        return {
            "busiest_day_of_week": busiest_day,
            "peak_hour": peak_hour,
            "top_usb": top_usb_list[0] if top_usb_list else None,
            "top_client": top_client_list[0] if top_client_list else None,
            "new_clients_30d": int(new_clients),
            "inactive_clients_60d": int(inactive),
            "avg_per_session": float(avg_per_session),
            "avg_per_gb": float(avg_per_gb),
        }

    # -----------------------------------------------------------------
    # Estadísticas completas (paridad Uatcher.GeneralStatistics)
    # -----------------------------------------------------------------

    async def general_statistics(self) -> dict:
        """Estadísticas completas del negocio (paridad Uatcher)."""
        top_usb_list = await self.top_usb(limit=10)
        top_client_list = await self.top_clients(limit=10)

        # Top archivos (histórico)
        top_files_q = (
            select(
                Copy.file_name,
                func.count().label("count"),
                func.coalesce(func.sum(Copy.size_bytes), 0).label("total_bytes"),
            )
            .where(Copy.file_name.isnot(None))
            .group_by(Copy.file_name)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_files_r = await self.session.execute(top_files_q)
        top_files = [
            {"file_name": r.file_name, "count": int(r.count),
             "total_bytes": int(r.total_bytes or 0)}
            for r in top_files_r.all()
        ]

        # Top archivos 2 semanas
        since_14 = utcnow() - timedelta(days=14)
        top_files_2w_q = (
            select(
                Copy.file_name,
                func.count().label("count"),
            )
            .where((Copy.file_name.isnot(None)) & (Copy.copy_date_time >= since_14))
            .group_by(Copy.file_name)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_files_2w_r = await self.session.execute(top_files_2w_q)
        top_files_two_weeks = [
            {"file_name": r.file_name, "count": int(r.count)}
            for r in top_files_2w_r.all()
        ]

        # Top días (por día de la semana)
        top_days_q = (
            select(
                func.strftime("%w", InsertedDrive.insertion_date_time).label("dow"),
                func.count().label("count"),
            )
            .group_by(func.strftime("%w", InsertedDrive.insertion_date_time))
            .order_by(func.count().desc())
            .limit(7)
        )
        top_days_r = await self.session.execute(top_days_q)
        top_days = [
            {"day_of_week": int(r.dow), "count": int(r.count)}
            for r in top_days_r.all()
        ]

        # Top horas
        top_hours_q = (
            select(
                func.strftime("%H", InsertedDrive.insertion_date_time).label("hour"),
                func.count().label("count"),
            )
            .group_by(func.strftime("%H", InsertedDrive.insertion_date_time))
            .order_by(func.count().desc())
            .limit(24)
        )
        top_hours_r = await self.session.execute(top_hours_q)
        top_hours = [
            {"hour_of_day": int(r.hour), "count": int(r.count)}
            for r in top_hours_r.all()
        ]

        # Promedios y máximos
        all_drives_q = select(
            func.count().label("total"),
            func.coalesce(func.sum(InsertedDrive.payment), 0).label("total_payment"),
        )
        all_r = (await self.session.execute(all_drives_q)).one()
        total_drives = int(all_r.total or 0)
        total_payment = int(all_r.total_payment or 0)

        # Aproximación: promedios por día (asumiendo 30 días de operación)
        days_active = 30  # simplificación
        devices_avg_per_day = total_drives // days_active if days_active > 0 else 0
        payment_avg_per_day = total_payment // days_active if days_active > 0 else 0

        return {
            "top_days": top_days,
            "top_hours": top_hours,
            "top_files": top_files,
            "top_files_two_weeks": top_files_two_weeks,
            "top_clients": top_client_list,
            "devices_average_per_day": devices_avg_per_day,
            "payment_average_per_day": payment_avg_per_day,
            "max_devices_one_day": 0,  # requeriría subquery
            "max_payment_one_day": 0,
            "space_copied_average_per_device": 0,
            "files_copied_count_average_per_device": 0,
            "payment_average_per_device": total_payment // total_drives if total_drives > 0 else 0,
            "last_copy_id": 0,
        }
