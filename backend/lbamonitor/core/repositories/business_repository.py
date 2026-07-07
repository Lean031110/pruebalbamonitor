"""
Repositorios de clientes, VIP, membresías, recompensas, catálogo, billing, etc.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.models import (
    Billing,
    CatalogEntry,
    Client,
    MembershipLevel,
    PaymentAlteration,
    Reward,
    USBDevice,
    VIPEntry,
)
from lbamonitor.core.repositories.base import BaseRepository
from lbamonitor.utils.helpers import utcnow


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ClientRepository(BaseRepository[Client]):
    model = Client

    async def get_by_device(self, device_id: int) -> Client | None:
        result = await self.session.execute(
            select(Client).where(Client.device_id == device_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, device_id: int) -> Client:
        client = await self.get_by_device(device_id)
        if client:
            return client
        return await self.create(device_id=device_id, first_visit=utcnow())

    async def list_top(
        self,
        limit: int = 10,
        order_by: str = "visit_count",  # visit_count|total_spent|total_gb_copied
    ) -> list[Client]:
        col = getattr(Client, order_by, Client.visit_count)
        result = await self.session.execute(
            select(Client).order_by(col.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def search(self, query: str, limit: int = 50) -> list[Client]:
        pat = f"%{query}%"
        result = await self.session.execute(
            select(Client)
            .where(or_(Client.name.ilike(pat), Client.phone.ilike(pat)))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def increment_visit(
        self,
        device_id: int,
        spent: float = 0.0,
        gb_copied: float = 0.0,
    ) -> Client:
        client = await self.get_or_create(device_id)
        client.visit_count = (client.visit_count or 0) + 1
        client.total_spent = (client.total_spent or 0) + spent
        client.total_gb_copied = (client.total_gb_copied or 0) + gb_copied
        client.last_visit = utcnow()
        # Puntos: 1 pt/GB + 1 pt/visita + 1 pt/10 pesos (acumulativo, no sobrescribe)
        client.points = (client.points or 0) + int(gb_copied) + 1 + int(spent / 10)
        await self.session.flush()
        await self.session.refresh(client)
        return client


# ---------------------------------------------------------------------------
# VIP
# ---------------------------------------------------------------------------

class VIPRepository(BaseRepository[VIPEntry]):
    model = VIPEntry

    async def get_by_device(self, device_id: int) -> VIPEntry | None:
        result = await self.session.execute(
            select(VIPEntry).where(VIPEntry.device_id == device_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        device_id: int,
        vip_type: str,
        discount_percent: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> VIPEntry:
        entry = await self.get_by_device(device_id)
        if entry:
            entry.vip_type = vip_type
            entry.discount_percent = discount_percent
            entry.reason = reason
            await self.session.flush()
            await self.session.refresh(entry)
            return entry
        return await self.create(
            device_id=device_id,
            vip_type=vip_type,
            discount_percent=discount_percent,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# MembershipLevel
# ---------------------------------------------------------------------------

class MembershipLevelRepository(BaseRepository[MembershipLevel]):
    model = MembershipLevel

    async def get_by_tier(self, tier: str) -> MembershipLevel | None:
        result = await self.session.execute(
            select(MembershipLevel).where(MembershipLevel.tier == tier)
        )
        return result.scalar_one_or_none()

    async def list_ordered(self) -> list[MembershipLevel]:
        result = await self.session.execute(
            select(MembershipLevel).order_by(MembershipLevel.id.asc())
        )
        return list(result.scalars().all())

    async def initialize_defaults(self) -> None:
        """Crea los niveles por defecto si no existen."""
        defaults = [
            ("bronce", 0, 0, 0, 0.0, "#CD7F32"),
            ("plata", 5, 10, 200, 3.0, "#C0C0C0"),
            ("oro", 15, 50, 800, 7.0, "#FFD700"),
            ("platino", 30, 150, 2500, 12.0, "#E5E4E2"),
            ("diamante", 60, 500, 8000, 20.0, "#B9F2FF"),
        ]
        for tier, visits, gb, spent, discount, color in defaults:
            existing = await self.get_by_tier(tier)
            if not existing:
                await self.create(
                    tier=tier,
                    min_visits=visits,
                    min_gb=gb,
                    min_spent=spent,
                    discount_percent=discount,
                    color=color,
                )

    async def compute_tier(
        self, visits: int, gb: float, spent: float
    ) -> str:
        """Devuelve el tier que cumple TODOS los umbrales."""
        levels = await self.list_ordered()
        # Iterar en orden inverso (diamante → bronce) y devolver el primero que cumple
        for level in reversed(levels):
            if (
                visits >= level.min_visits
                and gb >= level.min_gb
                and spent >= level.min_spent
            ):
                return level.tier
        return "bronce"

    async def tier_distribution(self) -> list[dict]:
        """Distribución de clientes por tier."""
        result = await self.session.execute(
            select(Client.tier, func.count())
            .group_by(Client.tier)
        )
        return [{"tier": r[0], "count": r[1]} for r in result.all()]


# ---------------------------------------------------------------------------
# Reward
# ---------------------------------------------------------------------------

class RewardRepository(BaseRepository[Reward]):
    model = Reward

    async def list_pending_for_client(self, device_id: int) -> list[Reward]:
        result = await self.session.execute(
            select(Reward)
            .where(
                (Reward.device_id == device_id)
                & (Reward.applied == False)  # noqa: E712
            )
            .order_by(Reward.granted_at.desc())
        )
        return list(result.scalars().all())

    async def list_recent(self, limit: int = 50) -> list[Reward]:
        result = await self.session.execute(
            select(Reward).order_by(Reward.granted_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def apply(self, reward_id: int) -> Reward | None:
        reward = await self.get_by_id(reward_id)
        if reward:
            reward.applied = True
            await self.session.flush()
            await self.session.refresh(reward)
        return reward


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

class BillingRepository(BaseRepository[Billing]):
    model = Billing

    async def get_by_session(self, session_id: int) -> Billing | None:
        result = await self.session.execute(
            select(Billing).where(Billing.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_in_range(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Billing], int]:
        q = select(Billing)
        count_q = select(func.count()).select_from(Billing)
        if from_date:
            q = q.where(Billing.created_at >= from_date)
            count_q = count_q.where(Billing.created_at >= from_date)
        if to_date:
            q = q.where(Billing.created_at <= to_date)
            count_q = count_q.where(Billing.created_at <= to_date)

        total = (await self.session.execute(count_q)).scalar() or 0
        q = q.order_by(Billing.created_at.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(q)
        return list(result.scalars().all()), total

    async def totals_in_range(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> dict:
        """Devuelve count, revenue, discounts totales en el rango."""
        q = select(
            func.count().label("count"),
            func.coalesce(func.sum(Billing.charged), 0).label("revenue"),
            func.coalesce(func.sum(Billing.discount_amount), 0).label("discounts"),
        )
        if from_date:
            q = q.where(Billing.created_at >= from_date)
        if to_date:
            q = q.where(Billing.created_at <= to_date)
        result = await self.session.execute(q)
        r = result.one()
        return {
            "count": r.count or 0,
            "revenue": float(r.revenue or 0),
            "discounts": float(r.discounts or 0),
        }


# ---------------------------------------------------------------------------
# PaymentAlteration
# ---------------------------------------------------------------------------

class PaymentAlterationRepository(BaseRepository[PaymentAlteration]):
    model = PaymentAlteration

    async def list_by_user(
        self, user_id: int, limit: int = 100
    ) -> list[PaymentAlteration]:
        result = await self.session.execute(
            select(PaymentAlteration)
            .where(PaymentAlteration.user_id == user_id)
            .order_by(PaymentAlteration.alteration_date_time.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_drive(
        self, drive_id: int
    ) -> list[PaymentAlteration]:
        result = await self.session.execute(
            select(PaymentAlteration)
            .where(PaymentAlteration.inserted_drive_id == drive_id)
            .order_by(PaymentAlteration.alteration_date_time.desc())
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# CatalogEntry
# ---------------------------------------------------------------------------

class CatalogRepository(BaseRepository[CatalogEntry]):
    model = CatalogEntry

    async def list_filtered(
        self,
        category: Optional[str] = None,
        active_only: bool = True,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[CatalogEntry], int]:
        q = select(CatalogEntry)
        count_q = select(func.count()).select_from(CatalogEntry)

        if active_only:
            q = q.where(CatalogEntry.active == True)  # noqa: E712
            count_q = count_q.where(CatalogEntry.active == True)  # noqa: E712
        if category:
            q = q.where(CatalogEntry.category == category)
            count_q = count_q.where(CatalogEntry.category == category)
        if query:
            pat = f"%{query}%"
            filt = or_(
                CatalogEntry.title.ilike(pat),
                CatalogEntry.genre.ilike(pat),
                CatalogEntry.director.ilike(pat),
                CatalogEntry.artist.ilike(pat),
                CatalogEntry.tags.ilike(pat),
            )
            q = q.where(filt)
            count_q = count_q.where(filt)

        total = (await self.session.execute(count_q)).scalar() or 0
        q = q.order_by(CatalogEntry.title.asc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(q)
        return list(result.scalars().all()), total

    async def top_copied(self, limit: int = 10) -> list[CatalogEntry]:
        result = await self.session.execute(
            select(CatalogEntry)
            .where(CatalogEntry.times_copied > 0)
            .order_by(CatalogEntry.times_copied.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def increment_copied(self, entry_id: int) -> None:
        entry = await self.get_by_id(entry_id)
        if entry:
            entry.times_copied = (entry.times_copied or 0) + 1
            await self.session.flush()
