"""
Repositorio de usuarios con manejo de contraseñas y roles.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.models import User
from lbamonitor.core.repositories.base import BaseRepository
from lbamonitor.utils.helpers import hash_password, verify_password, utcnow


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.active == True).order_by(User.username)  # noqa: E712
        )
        return list(result.scalars().all())

    async def create_with_password(
        self,
        username: str,
        password: str,
        role: str = "operator",
        full_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> User:
        hashed = hash_password(password)
        return await self.create(
            username=username,
            password_hash=hashed,
            role=role,
            full_name=full_name,
            email=email,
            name=full_name,  # alias compat Uatcher
            active=True,
        )

    async def update_password(self, user: User, new_password: str) -> None:
        user.password_hash = hash_password(new_password)
        await self.session.flush()

    async def verify_credentials(self, username: str, password: str) -> User | None:
        """Devuelve el User si las credenciales son correctas, None si no."""
        user = await self.get_by_username(username)
        if not user or not user.active:
            return None
        if not user.password_hash:
            return None
        if not verify_password(password, user.password_hash):
            return None
        # Actualizar last_login
        user.last_login = utcnow()
        await self.session.flush()
        return user

    async def set_active(self, user_id: int, active: bool) -> User | None:
        user = await self.get_by_id(user_id)
        if user:
            user.active = active
            user.inactive = not active
            await self.session.flush()
        return user

    async def count_active_admins(self) -> int:
        """Cuenta admins activos (para no eliminar el último)."""
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .where((User.role == "admin") & (User.active == True))  # noqa: E712
        )
        return result.scalar() or 0
