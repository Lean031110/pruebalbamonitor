"""Schemas de usuarios y operadores."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from lbamonitor.api.schemas.common import OrmModel


class UserBase(OrmModel):
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str = "operator"  # admin|manager|operator


class UserCreate(UserBase):
    password: str  # plaintext, se hashea en el servicio


class UserUpdate(OrmModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None  # si se setea, se cambia la contraseña


class UserResponse(UserBase):
    id: int
    active: bool
    created: datetime
    last_login: Optional[datetime] = None

    # Alias de compatibilidad con Uatcher
    name: Optional[str] = None
    inactive: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str
