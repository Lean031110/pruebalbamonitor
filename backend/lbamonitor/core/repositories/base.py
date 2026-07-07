"""
Repositorio base genérico con operaciones CRUD comunes.

Todos los repositorios específicos heredan de BaseRepository para no duplicar
código de paginación, filtrado, etc.
"""
from __future__ import annotations

from typing import Any, Generic, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.models import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Repositorio genérico con CRUD básico."""

    model: Type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id_: int) -> ModelT | None:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id_)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 50,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> tuple[list[ModelT], int]:
        """
        Lista paginada.

        Devuelve (items, total).
        """
        # Total
        count_q = select(func.count()).select_from(self.model)
        total = (await self.session.execute(count_q)).scalar() or 0

        # Items paginados
        q = select(self.model)
        if order_by and hasattr(self.model, order_by):
            col = getattr(self.model, order_by)
            q = q.order_by(col.desc() if order_desc else col.asc())
        else:
            # Default: ordenar por id desc (más reciente primero)
            q = q.order_by(self.model.id.desc())

        offset = (page - 1) * page_size
        q = q.offset(offset).limit(page_size)
        result = await self.session.execute(q)
        items = list(result.scalars().all())
        return items, total

    async def create(self, **kwargs: Any) -> ModelT:
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, obj: ModelT, **kwargs: Any) -> ModelT:
        for k, v in kwargs.items():
            if v is not None and hasattr(obj, k):
                setattr(obj, k, v)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def delete_by_id(self, id_: int) -> bool:
        obj = await self.get_by_id(id_)
        if obj is None:
            return False
        await self.delete(obj)
        return True
