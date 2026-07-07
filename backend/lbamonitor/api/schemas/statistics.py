"""Schemas de estadísticas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from lbamonitor.api.schemas.common import OrmModel


class KPIs(OrmModel):
    """KPIs para un rango de fechas."""

    range_start: datetime
    range_end: datetime
    transactions: int = 0
    revenue: float = 0.0
    discounts: float = 0.0
    usb_count: int = 0
    sessions: int = 0
    gb_copied: float = 0.0
    files_copied: int = 0
    avg_per_session: float = 0.0
    avg_per_gb: float = 0.0


class SeriesPoint(OrmModel):
    """Punto de una serie temporal."""

    label: str
    value: float
    count: int = 0


class HourlyHeatmapPoint(OrmModel):
    """Heatmap hora × día de la semana."""

    hour: int  # 0-23
    day_of_week: int  # 0-6 (lunes=0)
    count: int


class TopClient(OrmModel):
    device_id: int
    alias: Optional[str] = None
    visit_count: int
    total_spent: float
    tier: str = "bronce"


class TopUSB(OrmModel):
    device_id: int
    alias: Optional[str] = None
    serial: Optional[str] = None
    visit_count: int
    last_visit: Optional[datetime] = None


class BusinessInsights(OrmModel):
    """Insights automáticos del negocio."""

    busiest_day_of_week: Optional[str] = None  # "lunes", "martes", ...
    peak_hour: Optional[int] = None  # 0-23
    top_usb: Optional[TopUSB] = None
    top_client: Optional[TopClient] = None
    new_clients_30d: int = 0
    inactive_clients_60d: int = 0
    avg_per_session: float = 0.0
    avg_per_gb: float = 0.0


class GeneralStatistics(OrmModel):
    """Estadísticas completas (paridad con Uatcher.GeneralStatistics)."""

    top_days: list[dict] = []
    top_hours: list[dict] = []
    top_files: list[dict] = []
    top_files_two_weeks: list[dict] = []
    top_clients: list[TopClient] = []
    devices_average_per_day: int = 0
    payment_average_per_day: float = 0.0
    max_devices_one_day: int = 0
    max_payment_one_day: float = 0.0
    space_copied_average_per_device: int = 0
    files_copied_count_average_per_device: int = 0
    payment_average_per_device: float = 0.0
    last_copy_id: int = 0


class StatisticsResponse(OrmModel):
    """Respuesta del endpoint /api/statistics."""

    today_kpis: KPIs
    month_kpis: KPIs
    year_kpis: KPIs
    revenue_by_day: list[SeriesPoint] = []
    revenue_by_month: list[SeriesPoint] = []
    hourly_heatmap: list[HourlyHeatmapPoint] = []
    top_clients: list[TopClient] = []
    top_usb: list[TopUSB] = []
    insights: BusinessInsights
