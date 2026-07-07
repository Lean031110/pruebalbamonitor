"""
Dependencias comunes para los routers de la API.

Provee:
  - get_db (sesión SQLAlchemy)
  - paginación estándar
  - filtros de fecha
  - helpers de respuesta
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, TypeVar

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.db import get_db
from lbamonitor.api.schemas.common import PaginationInfo


T = TypeVar("T")


# En v4.3 se elimina el get_session roto. Usar get_db directamente.
# (Antes retornaba Depends(get_db) en lugar de AsyncSession, lo que rompía la inyección)


def paginate(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(50, ge=1, le=500, description="Items por página"),
) -> dict:
    """Dependencia para extraer parámetros de paginación."""
    return {"page": page, "page_size": page_size}


def make_pagination(
    page: int, page_size: int, total: int
) -> PaginationInfo:
    """Construye un objeto PaginationInfo."""
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return PaginationInfo(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


def not_found(detail: str = "Recurso no encontrado") -> HTTPException:
    """Helper para 404."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "type": "https://lbamonitor/errors/not-found",
            "title": "Not Found",
            "status": 404,
            "detail": detail,
        },
    )


def bad_request(detail: str) -> HTTPException:
    """Helper para 400."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "type": "https://lbamonitor/errors/bad-request",
            "title": "Bad Request",
            "status": 400,
            "detail": detail,
        },
    )
