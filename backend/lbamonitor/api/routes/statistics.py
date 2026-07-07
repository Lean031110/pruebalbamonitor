"""Router de estadísticas."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.schemas.statistics import (
    BusinessInsights,
    GeneralStatistics,
    KPIs,
    SeriesPoint,
    StatisticsResponse,
    TopClient,
    TopUSB,
)
from lbamonitor.core.db import get_db
from lbamonitor.core.models import User
from lbamonitor.core.security.auth import require_operator
from lbamonitor.core.services.statistics_service import StatisticsService

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("", response_model=StatisticsResponse)
async def get_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Estadísticas completas: KPIs hoy/mes/año + series + rankings + insights."""
    svc = StatisticsService(db)
    return StatisticsResponse(
        today_kpis=KPIs(**await svc.today_kpis()),
        month_kpis=KPIs(**await svc.month_kpis()),
        year_kpis=KPIs(**await svc.year_kpis()),
        revenue_by_day=[SeriesPoint(**r) for r in await svc.revenue_by_day()],
        revenue_by_month=[SeriesPoint(**r) for r in await svc.revenue_by_month()],
        hourly_heatmap=await svc.hourly_heatmap(),
        top_clients=[TopClient(**c) for c in await svc.top_clients()],
        top_usb=[TopUSB(**u) for u in await svc.top_usb()],
        insights=BusinessInsights(**await svc.business_insights()),
    )


@router.get("/kpis/today", response_model=KPIs)
async def kpis_today(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    svc = StatisticsService(db)
    return KPIs(**await svc.today_kpis())


@router.get("/kpis/month", response_model=KPIs)
async def kpis_month(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    svc = StatisticsService(db)
    return KPIs(**await svc.month_kpis())


@router.get("/kpis/year", response_model=KPIs)
async def kpis_year(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    svc = StatisticsService(db)
    return KPIs(**await svc.year_kpis())


@router.get("/revenue/by-day", response_model=list[SeriesPoint])
async def revenue_by_day(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    svc = StatisticsService(db)
    return [SeriesPoint(**r) for r in await svc.revenue_by_day(days)]


@router.get("/revenue/by-month", response_model=list[SeriesPoint])
async def revenue_by_month(
    months: int = Query(12, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    svc = StatisticsService(db)
    return [SeriesPoint(**r) for r in await svc.revenue_by_month(months)]


@router.get("/top-clients", response_model=list[TopClient])
async def top_clients(
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    svc = StatisticsService(db)
    return [TopClient(**c) for c in await svc.top_clients(limit)]


@router.get("/top-usb", response_model=list[TopUSB])
async def top_usb(
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    svc = StatisticsService(db)
    return [TopUSB(**u) for u in await svc.top_usb(limit)]


@router.get("/insights", response_model=BusinessInsights)
async def insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    svc = StatisticsService(db)
    return BusinessInsights(**await svc.business_insights())


@router.get("/general", response_model=GeneralStatistics)
async def general_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Estadísticas generales (paridad Uatcher.GeneralStatistics)."""
    svc = StatisticsService(db)
    return GeneralStatistics(**await svc.general_statistics())
