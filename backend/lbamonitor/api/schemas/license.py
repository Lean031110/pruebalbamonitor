"""Schemas de licencia."""
from __future__ import annotations

from datetime import date
from pydantic import BaseModel
from typing import Optional

from lbamonitor.api.schemas.common import OrmModel


class LicenseStatus(OrmModel):
    valid: bool
    tier: str = "trial"
    expires: Optional[str] = None
    issued_at: Optional[str] = None
    reason: str = "OK"
    machine_id: str


class LicenseActivateRequest(BaseModel):
    license_key: str


class LicenseActivateResponse(OrmModel):
    success: bool
    message: str
    license: Optional[LicenseStatus] = None


class MachineIDResponse(OrmModel):
    machine_id: str
    components: dict = {}
