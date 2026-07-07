"""
Router de autenticación: /api/auth/login, /refresh, /logout.

Esta es la pieza que faltaba en v4.0.0 y v4.2: un endpoint de login real
que use verify_credentials + create_access_token + create_refresh_token.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import get_db
from lbamonitor.core.security.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_token,
    verify_credentials,
)
from lbamonitor.core.security.rate_limiter import rate_limit
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ─────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="Nombre de usuario")
    password: str = Field(..., min_length=1, max_length=128, description="Contraseña")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Segundos hasta expiración del access token")
    user_id: int = Field(..., description="ID del usuario autenticado")
    username: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    token: str  # access token a revocar


class MessageResponse(BaseModel):
    message: str


# ─────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión",
    description="Autentica al usuario y devuelve access + refresh tokens JWT.",
)
@rate_limit(per_minute=5, block_seconds=60)  # anti brute-force
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Endpoint de login.

    - 5 intentos por minuto por IP (rate limit anti brute-force)
    - Devuelve access token (60 min) + refresh token (7 días)
    - Loggea intentos fallidos para auditoría
    """
    from lbamonitor.core.config import get_settings

    user = await verify_credentials(db, payload.username, payload.password)
    if not user:
        # Loggeo de intento fallido (sin exponer si el usuario existe)
        client_ip = request.client.host if request.client else "unknown"
        log.warning(
            f"Login fallido para username={payload.username!r} desde IP={client_ip}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    s = get_settings().security
    access_token = create_access_token(user.username, user.role)
    refresh_token = create_refresh_token(user.username, user.role)

    log.info(f"Login exitoso: username={user.username!r} role={user.role!r}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=s.jwt_expiration_minutes * 60,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refrescar access token",
    description="Intercambia un refresh token válido por un nuevo par de tokens.",
)
@rate_limit(per_minute=30)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Endpoint de refresh: intercambia un refresh token por un nuevo access token.

    - El refresh token debe ser válido y no estar en blacklist
    - Se emite un nuevo access token + nuevo refresh token (rotación)
    """
    from lbamonitor.core.config import get_settings

    token_data = decode_token(payload.refresh_token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
        )

    if token_data.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no es de tipo refresh",
        )

    # Cargar user_id desde BD
    from lbamonitor.core.repositories.user_repository import UserRepository
    user_repo = UserRepository(db)
    user = await user_repo.get_by_username(token_data.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario del refresh token no encontrado",
        )

    s = get_settings().security
    new_access = create_access_token(token_data.sub, token_data.role)
    new_refresh = create_refresh_token(token_data.sub, token_data.role)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=s.jwt_expiration_minutes * 60,
        user_id=user.id,
        username=token_data.sub,
        role=token_data.role,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Cerrar sesión",
    description="Revoca el access token actual (lo añade a la blacklist).",
)
async def logout(payload: LogoutRequest) -> MessageResponse:
    """
    Endpoint de logout: revoca el access token añadiéndolo a la blacklist.

    El cliente debe eliminar sus tokens almacenados localmente.
    """
    token_data = decode_token(payload.token)
    if not token_data:
        # Idempotente: si el token ya es inválido, igual devolvemos success
        return MessageResponse(message="Sesión cerrada")

    if token_data.jti:
        revoke_token(token_data.jti, token_data.exp)
        log.info(f"Logout: username={token_data.sub!r} jti={token_data.jti[:8]}...")

    return MessageResponse(message="Sesión cerrada correctamente")
