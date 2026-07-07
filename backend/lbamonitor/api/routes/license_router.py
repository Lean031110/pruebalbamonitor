"""Router de licencia: estado, activación, machine ID."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import get_db
from lbamonitor.api.schemas.license import (
    LicenseActivateRequest,
    LicenseActivateResponse,
    LicenseStatus,
    MachineIDResponse,
)
from lbamonitor.core.config import get_settings, reload_settings
from lbamonitor.core.security.auth import require_operator
from lbamonitor.core.models import User, KeyValue
from lbamonitor.core.services.license_engine import (
    compute_machine_id,
    verify_license,
)
from lbamonitor.utils.logging_setup import get_logger
from sqlalchemy import select

log = get_logger(__name__)

router = APIRouter(prefix="/license", tags=["license"])


@router.get("/machine-id", response_model=MachineIDResponse)
async def get_machine_id(
    current_user: User = Depends(require_operator),
):
    """Devuelve el Machine ID (HWID) calculado vía WMI."""
    hwid = compute_machine_id()
    return MachineIDResponse(
        machine_id=hwid,
        components={"hwid": hwid[:32] + "..."},
    )


@router.get("/status")
async def get_license_trial_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """
    Devuelve el estado completo de la licencia incluyendo el trial de 10 días.

    Response:
        {
            "state": "trial" | "expired" | "licensed" | "invalid",
            "days_remaining": int | null,
            "first_install": str | null,
            "license_key": str | null,
            "tier": str,
            "expires": str | null,
            "reason": str,
            "machine_id": str,
            "features_limited": bool,
        }
    """
    from lbamonitor.core.services.license_state import LicenseState
    from lbamonitor.core.db import get_session_factory

    factory = get_session_factory()
    state_mgr = LicenseState(factory)
    status = await state_mgr.get_status()
    status["machine_id"] = compute_machine_id()
    status["features_limited"] = status["state"] in ("expired", "invalid")
    return status


@router.get("", response_model=LicenseStatus)
async def get_license_status(
    current_user: User = Depends(require_operator),
):
    """Devuelve el estado actual de la licencia (legacy endpoint)."""
    s = get_settings().license
    hwid = compute_machine_id()

    # Verificar si hay licencia persistida en BD
    from lbamonitor.core.db import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        r = await session.execute(select(KeyValue).where(KeyValue.key == "license.key"))
        kv = r.scalar_one_or_none()
        persisted_key = kv.value if kv else None

    active_key = persisted_key or s.key

    if not active_key:
        return LicenseStatus(
            valid=False,
            tier="trial",
            reason="Sin licencia configurada. Período de prueba activo (10 días).",
            machine_id=hwid,
        )

    result = verify_license(
        active_key,
        hwid,
        secret=s.signing_secret,
        public_key_pem=s.public_key_pem,
        tolerance=s.hwid_tolerance,
    )
    return LicenseStatus(
        valid=result["valid"],
        tier=result.get("tier", "trial"),
        expires=result.get("expires"),
        issued_at=result.get("issued_at"),
        reason=result.get("reason", "OK"),
        machine_id=hwid,
    )


@router.post("/activate", response_model=LicenseActivateResponse)
async def activate_license(
    payload: LicenseActivateRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """
    Activa una licencia con un código recibido del licensor.

    v4.4: Persiste la licencia en KeyValue 'license.key' y recarga la config.
    """
    s = get_settings().license
    hwid = compute_machine_id()
    result = verify_license(
        payload.license_key,
        hwid,
        secret=s.signing_secret,
        public_key_pem=s.public_key_pem,
        tolerance=s.hwid_tolerance,
    )

    if result["valid"]:
        # Persistir en BD
        r = await db.execute(select(KeyValue).where(KeyValue.key == "license.key"))
        kv = r.scalar_one_or_none()
        if kv:
            kv.value = payload.license_key
        else:
            db.add(KeyValue(key="license.key", value=payload.license_key))
        # Registrar fecha de activación
        from lbamonitor.utils.helpers import utcnow
        r2 = await db.execute(select(KeyValue).where(KeyValue.key == "license.activated_at"))
        kv2 = r2.scalar_one_or_none()
        if kv2:
            kv2.value = utcnow().isoformat()
        else:
            db.add(KeyValue(key="license.activated_at", value=utcnow().isoformat()))
        await db.commit()

        # Recargar settings para que s.license.key tenga el valor nuevo
        # Nota: como get_settings está cacheado, necesitamos actualizar el campo
        s.key = payload.license_key

        log.info(f"Licencia activada: tier={result.get('tier')}, expires={result.get('expires')}")

        return LicenseActivateResponse(
            success=True,
            message="Licencia activada correctamente",
            license=LicenseStatus(
                valid=True,
                tier=result.get("tier", "pro"),
                expires=result.get("expires"),
                issued_at=result.get("issued_at"),
                reason="OK",
                machine_id=hwid,
            ),
        )
    else:
        return LicenseActivateResponse(
            success=False,
            message=f"Activación fallida: {result.get('reason', 'desconocido')}",
            license=LicenseStatus(
                valid=False,
                tier="trial",
                reason=result.get("reason", "desconocido"),
                machine_id=hwid,
            ),
        )
