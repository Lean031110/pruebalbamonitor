"""Schemas Pydantic comunes: paginación, respuestas, errores."""
from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class OrmModel(BaseModel):
    """Base para modelos que se mapean desde ORM SQLAlchemy."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaginationInfo(BaseModel):
    """Metadatos de paginación."""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    has_next: bool = False
    has_prev: bool = False


class PaginatedResponse(BaseModel, Generic[T]):
    """Respuesta paginada genérica."""

    items: list[T]
    pagination: PaginationInfo


class ErrorResponse(BaseModel):
    """RFC 7807 Problem Details."""

    type: str = "https://lbamonitor/errors/generic"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class HealthResponse(BaseModel):
    """Respuesta del endpoint /api/health."""

    status: str
    name: str
    version: str
    timestamp: datetime
    platform: dict
    python: str
    config: dict
    service_session: dict | None = None
    counts: dict = Field(default_factory=dict)


class MessageResponse(BaseModel):
    """Respuesta simple con mensaje."""

    message: str
    detail: dict | None = None


class IdResponse(BaseModel):
    """Respuesta que devuelve solo el ID creado/actualizado."""

    id: int
