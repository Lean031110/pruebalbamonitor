"""Router de usuarios / operadores."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import bad_request, make_pagination, not_found, paginate
from lbamonitor.api.schemas.common import IdResponse, MessageResponse, PaginatedResponse
from lbamonitor.api.schemas.users import (
    PasswordChangeRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from lbamonitor.core.db import get_db
from lbamonitor.core.models import User
from lbamonitor.core.repositories import UserRepository
from lbamonitor.core.security.auth import require_admin

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=PaginatedResponse[UserResponse])
@router.get("/", response_model=PaginatedResponse[UserResponse], include_in_schema=False)
async def list_users(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(paginate),
    current_user: User = Depends(require_admin),
):
    repo = UserRepository(db)
    users, total = await repo.list_all(**pagination)
    return {
        "items": [UserResponse.model_validate(u) for u in users],
        "pagination": make_pagination(pagination["page"], pagination["page_size"], total),
    }


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise not_found(f"Usuario {user_id} no encontrado")
    return UserResponse.model_validate(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=UserResponse, include_in_schema=False, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    repo = UserRepository(db)
    existing = await repo.get_by_username(payload.username)
    if existing:
        raise bad_request(f"Username '{payload.username}' ya existe")
    user = await repo.create_with_password(
        username=payload.username,
        password=payload.password,
        role=payload.role,
        full_name=payload.full_name,
        email=payload.email,
    )
    await db.commit()
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise not_found(f"Usuario {user_id} no encontrado")

    # Si se está desactivando un admin, verificar que no sea el último
    if payload.active is False and user.role == "admin":
        count = await repo.count_active_admins()
        if count <= 1:
            raise bad_request("No se puede desactivar el último administrador activo")

    # Actualizar campos
    if payload.full_name is not None:
        user.full_name = payload.full_name
        user.name = payload.full_name
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        user.role = payload.role
    if payload.active is not None:
        user.active = payload.active
        user.inactive = not payload.active
    if payload.password:
        await repo.update_password(user, payload.password)

    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Soft-delete: marca el usuario como inactivo."""
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise not_found(f"Usuario {user_id} no encontrado")
    if user.role == "admin":
        count = await repo.count_active_admins()
        if count <= 1:
            raise bad_request("No se puede eliminar el último administrador activo")
    user.active = False
    user.inactive = True
    await db.commit()
    return MessageResponse(message=f"Usuario {user_id} desactivado")
