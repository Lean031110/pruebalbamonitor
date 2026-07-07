"""Router de clientes (clients), VIP, membresías y recompensas."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import bad_request, make_pagination, not_found, paginate
from lbamonitor.api.schemas.clients import (
    ClientResponse,
    ClientUpdate,
    MembershipLevelResponse,
    MembershipLevelUpdate,
    RewardCreate,
    RewardResponse,
    TierDistributionItem,
    TierProgress,
    VIPEntryCreate,
    VIPEntryResponse,
)
from lbamonitor.api.schemas.common import MessageResponse, PaginatedResponse
from lbamonitor.core.db import get_db
from lbamonitor.core.models import User
from lbamonitor.core.repositories import (
    ClientRepository,
    MembershipLevelRepository,
    RewardRepository,
    VIPRepository,
)
from lbamonitor.core.security.auth import require_admin, require_operator
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["clients"])


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

@router.get("/clients", response_model=PaginatedResponse[ClientResponse])
async def list_clients(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(paginate),
    current_user: User = Depends(require_operator),
):
    repo = ClientRepository(db)
    clients, total = await repo.list_all(**pagination)
    return {
        "items": [ClientResponse.model_validate(c) for c in clients],
        "pagination": make_pagination(pagination["page"], pagination["page_size"], total),
    }


@router.get("/clients/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = ClientRepository(db)
    client = await repo.get_by_id(client_id)
    if not client:
        raise not_found(f"Cliente {client_id} no encontrado")
    return ClientResponse.model_validate(client)


@router.patch("/clients/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = ClientRepository(db)
    client = await repo.get_by_id(client_id)
    if not client:
        raise not_found(f"Cliente {client_id} no encontrado")
    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(client, k, v)
    await db.commit()
    await db.refresh(client)
    return ClientResponse.model_validate(client)


# ---------------------------------------------------------------------------
# VIP
# ---------------------------------------------------------------------------

@router.get("/vip", response_model=list[VIPEntryResponse])
async def list_vip(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = VIPRepository(db)
    entries, _ = await repo.list_all(page=1, page_size=500)
    return [VIPEntryResponse.model_validate(e) for e in entries]


@router.post("/vip", response_model=VIPEntryResponse, status_code=201)
async def create_vip(
    payload: VIPEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = VIPRepository(db)
    entry = await repo.upsert(
        device_id=payload.device_id,
        vip_type=payload.vip_type,
        discount_percent=payload.discount_percent,
        reason=payload.reason,
    )
    await db.commit()
    await db.refresh(entry)
    return VIPEntryResponse.model_validate(entry)


@router.delete("/vip/{device_id}", response_model=MessageResponse)
async def delete_vip(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = VIPRepository(db)
    entry = await repo.get_by_device(device_id)
    if not entry:
        raise not_found(f"VIP para dispositivo {device_id} no encontrado")
    await repo.delete(entry)
    await db.commit()
    return MessageResponse(message=f"VIP eliminado para dispositivo {device_id}")


# ---------------------------------------------------------------------------
# Membresías
# ---------------------------------------------------------------------------

@router.get("/memberships/levels", response_model=list[MembershipLevelResponse])
async def list_membership_levels(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = MembershipLevelRepository(db)
    # Inicializar defaults si no existen
    await repo.initialize_defaults()
    await db.commit()
    levels = await repo.list_ordered()
    return [MembershipLevelResponse.model_validate(l) for l in levels]


@router.get("/memberships", response_model=list[MembershipLevelResponse])
async def list_memberships(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Alias de ``GET /memberships/levels`` (sin inicializar defaults)."""
    repo = MembershipLevelRepository(db)
    levels = await repo.list_ordered()
    if not levels:
        await repo.initialize_defaults()
        await db.commit()
        levels = await repo.list_ordered()
    return [MembershipLevelResponse.model_validate(l) for l in levels]


@router.patch("/memberships/levels/{tier}", response_model=MembershipLevelResponse)
async def update_membership_level(
    tier: str,
    payload: MembershipLevelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = MembershipLevelRepository(db)
    level = await repo.get_by_tier(tier)
    if not level:
        raise not_found(f"Nivel {tier} no encontrado")
    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(level, k, v)
    await db.commit()
    await db.refresh(level)
    return MembershipLevelResponse.model_validate(level)


@router.put("/memberships/{tier}", response_model=MembershipLevelResponse)
async def update_membership(
    tier: str,
    payload: MembershipLevelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualiza min_visits / min_gb / min_spent / discount_percent / color.

    Requiere rol ``admin``.
    """
    repo = MembershipLevelRepository(db)
    level = await repo.get_by_tier(tier)
    if not level:
        raise not_found(f"Nivel {tier} no encontrado")
    updates = payload.model_dump(exclude_unset=True)
    if "discount_percent" in updates and not (0 <= updates["discount_percent"] <= 100):
        raise bad_request("discount_percent debe estar entre 0 y 100")
    if "min_visits" in updates and updates["min_visits"] < 0:
        raise bad_request("min_visits debe ser >= 0")
    if "min_gb" in updates and updates["min_gb"] < 0:
        raise bad_request("min_gb debe ser >= 0")
    if "min_spent" in updates and updates["min_spent"] < 0:
        raise bad_request("min_spent debe ser >= 0")
    for k, v in updates.items():
        setattr(level, k, v)
    await db.commit()
    await db.refresh(level)
    return MembershipLevelResponse.model_validate(level)


@router.post("/memberships/initialize", response_model=MessageResponse)
async def initialize_default_memberships(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Crea los 5 niveles por defecto (bronce, plata, oro, platino, diamante).

    No sobrescribe los niveles ya existentes. Requiere rol ``admin``.
    """
    repo = MembershipLevelRepository(db)
    before = len(await repo.list_ordered())
    await repo.initialize_defaults()
    await db.commit()
    after = len(await repo.list_ordered())
    created = after - before
    msg = (
        f"{created} nivel(es) creado(s). Total actual: {after}"
        if created > 0
        else f"Los 5 niveles ya existen. Total: {after}"
    )
    log.info(f"initialize_default_memberships by user={current_user.username}: {msg}")
    return MessageResponse(message=msg, detail={"created": created, "total": after})


@router.get("/memberships/distribution", response_model=list[TierDistributionItem])
async def membership_distribution(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = MembershipLevelRepository(db)
    return await repo.tier_distribution()


@router.post("/memberships/recompute", response_model=MessageResponse)
async def recompute_memberships(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Recomputa el tier de todos los clientes según sus métricas actuales."""
    repo_client = ClientRepository(db)
    repo_level = MembershipLevelRepository(db)
    clients, _ = await repo_client.list_all(page=1, page_size=10000)
    updated = 0
    for client in clients:
        new_tier = await repo_level.compute_tier(
            client.visit_count or 0,
            client.total_gb_copied or 0,
            client.total_spent or 0,
        )
        if client.tier != new_tier:
            client.tier = new_tier
            updated += 1
    await db.commit()
    return MessageResponse(
        message=f"{updated} clientes actualizados de {len(clients)} totales"
    )


# ---------------------------------------------------------------------------
# Recompensas
# ---------------------------------------------------------------------------

@router.get("/rewards", response_model=list[RewardResponse])
async def list_rewards(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = RewardRepository(db)
    rewards = await repo.list_recent(limit=limit)
    return [RewardResponse.model_validate(r) for r in rewards]


@router.post("/rewards", response_model=RewardResponse, status_code=201)
async def create_reward(
    payload: RewardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = RewardRepository(db)
    from datetime import timedelta
    from lbamonitor.utils.helpers import utcnow
    expires_at = None
    if payload.expires_in_days:
        expires_at = utcnow() + timedelta(days=payload.expires_in_days)
    reward = await repo.create(
        device_id=payload.device_id,
        reward_type=payload.reward_type,
        description=payload.description,
        value=payload.value,
        expires_at=expires_at,
    )
    await db.commit()
    await db.refresh(reward)
    return RewardResponse.model_validate(reward)


@router.post("/rewards/{reward_id}/apply", response_model=RewardResponse)
async def apply_reward(
    reward_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    repo = RewardRepository(db)
    reward = await repo.apply(reward_id)
    if not reward:
        raise not_found(f"Recompensa {reward_id} no encontrada")
    await db.commit()
    await db.refresh(reward)
    return RewardResponse.model_validate(reward)
