"""
Estado de licencia + trial de 10 días — LBAMonitor v4.4.

Funciona 100% offline. Persiste el estado en la BD (KeyValue store).

Estados:
- "trial": primeros 10 días desde la primera instalación. Funciones completas.
- "expired": pasaron 10 días sin licencia. Funciones limitadas (solo lectura).
- "licensed": licencia válida activa. Funciones completas.
- "invalid": licencia presente pero inválida/expirada. Funciones limitadas.

Limitaciones en modo "expired"/"invalid":
- No se pueden registrar nuevos cobros (solo ver historial)
- No se pueden crear usuarios
- No se pueden modificar settings de negocio
- No se pueden activar nuevas USBs (solo ver activas)
- El dashboard sigue mostrando datos

Anti-tampering:
- La fecha de primera instalación se firma con HMAC
- Se compara con la fecha actual para detectar rollback de reloj
- Si se detecta rollback, se bloquea inmediatamente
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from lbamonitor.core.config import get_settings
from lbamonitor.utils.helpers import hmac_sha256_hex, utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)

TRIAL_DAYS = 10
KEY_FIRST_INSTALL = "license.first_install"
KEY_FIRST_INSTALL_SIG = "license.first_install_sig"
KEY_LICENSE_KEY = "license.key"
KEY_LICENSE_ACTIVATED_AT = "license.activated_at"


class LicenseState:
    """Estado de licencia persistente."""

    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    async def _get_kv(self, key: str) -> str | None:
        from sqlalchemy import select
        from lbamonitor.core.models import KeyValue
        async with self._factory() as session:
            r = await session.execute(select(KeyValue).where(KeyValue.key == key))
            kv = r.scalar_one_or_none()
            return kv.value if kv else None

    async def _set_kv(self, key: str, value: str) -> None:
        from sqlalchemy import select
        from lbamonitor.core.models import KeyValue
        async with self._factory() as session:
            r = await session.execute(select(KeyValue).where(KeyValue.key == key))
            kv = r.scalar_one_or_none()
            if kv:
                kv.value = value
            else:
                session.add(KeyValue(key=key, value=value))
            await session.commit()

    async def get_first_install(self) -> datetime | None:
        """Devuelve la fecha de primera instalación (UTC)."""
        raw = await self._get_kv(KEY_FIRST_INSTALL)
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    async def _initialize_first_install(self) -> datetime:
        """Inicializa la fecha de primera instalación con firma HMAC."""
        now = utcnow()
        s = get_settings().license
        secret = s.signing_secret or "default-trial-secret"

        await self._set_kv(KEY_FIRST_INSTALL, now.isoformat())
        # Firmar para detectar tampering
        sig = hmac_sha256_hex(secret, now.isoformat())
        await self._set_kv(KEY_FIRST_INSTALL_SIG, sig)
        log.info(f"Primera instalación registrada: {now.isoformat()}")
        return now

    async def _verify_first_install_sig(self) -> bool:
        """Verifica que la fecha de instalación no fue tampered."""
        raw = await self._get_kv(KEY_FIRST_INSTALL)
        sig = await self._get_kv(KEY_FIRST_INSTALL_SIG)
        if not raw or not sig:
            return False
        s = get_settings().license
        secret = s.signing_secret or "default-trial-secret"
        expected = hmac_sha256_hex(secret, raw)
        return expected == sig

    async def get_status(self) -> dict[str, Any]:
        """
        Devuelve el estado actual de la licencia.

        Returns:
            {
                "state": "trial" | "expired" | "licensed" | "invalid",
                "days_remaining": int,  # solo en trial
                "first_install": str | None,  # ISO
                "license_key": str | None,
                "tier": str,  # trial | pro | enterprise
                "expires": str | None,
                "reason": str,
            }
        """
        s = get_settings().license

        # 1. Si hay licencia configurada, verificarla
        if s.key:
            from lbamonitor.core.services.license_engine import verify_license, compute_machine_id
            hwid = compute_machine_id()
            result = verify_license(
                s.key,
                hwid,
                secret=s.signing_secret,
                public_key_pem=s.public_key_pem,
                tolerance=s.hwid_tolerance,
            )
            if result["valid"]:
                return {
                    "state": "licensed",
                    "days_remaining": None,
                    "first_install": (await self.get_first_install()).isoformat() if await self.get_first_install() else None,
                    "license_key": s.key[:20] + "...",
                    "tier": result.get("tier", "pro"),
                    "expires": result.get("expires"),
                    "reason": "Licencia válida",
                }
            else:
                return {
                    "state": "invalid",
                    "days_remaining": 0,
                    "first_install": None,
                    "license_key": s.key[:20] + "...",
                    "tier": "trial",
                    "expires": None,
                    "reason": result.get("reason", "Licencia inválida"),
                }

        # 2. Sin licencia: evaluar trial
        first_install = await self.get_first_install()
        if not first_install:
            # Primera vez: inicializar
            first_install = await self._initialize_first_install()
        else:
            # Verificar que no fue tampered
            if not await self._verify_first_install_sig():
                log.error("¡TAMPERING DETECTADO! La fecha de instalación fue modificada.")
                return {
                    "state": "invalid",
                    "days_remaining": 0,
                    "first_install": None,
                    "license_key": None,
                    "tier": "trial",
                    "expires": None,
                    "reason": "Tampering detectado. Contacte al proveedor.",
                }

        # Calcular días restantes
        now = utcnow()
        elapsed = now - first_install
        days_elapsed = elapsed.total_seconds() / 86400
        days_remaining = max(0, TRIAL_DAYS - int(days_elapsed))

        if days_remaining > 0:
            return {
                "state": "trial",
                "days_remaining": days_remaining,
                "first_install": first_install.isoformat(),
                "license_key": None,
                "tier": "trial",
                "expires": (first_install + timedelta(days=TRIAL_DAYS)).isoformat(),
                "reason": f"Período de prueba: {days_remaining} días restantes",
            }
        else:
            return {
                "state": "expired",
                "days_remaining": 0,
                "first_install": first_install.isoformat(),
                "license_key": None,
                "tier": "trial",
                "expires": (first_install + timedelta(days=TRIAL_DAYS)).isoformat(),
                "reason": f"Período de prueba expirado. Adquiera una licencia.",
            }

    async def is_feature_allowed(self, feature: str) -> bool:
        """
        Verifica si una feature está permitida según el estado de licencia.

        Features limitadas en trial expirado / invalid:
        - "billing.create" — registrar cobros
        - "users.create" — crear usuarios
        - "settings.business.update" — modificar settings de negocio
        - "usb.activate" — activar nuevas USBs (Copiar archivos)

        Siempre permitidas (incluso en expired):
        - "billing.list" — ver historial
        - "usb.list" — ver USBs activas
        - "statistics.view" — ver estadísticas
        - "license.activate" — activar licencia
        """
        status = await self.get_status()
        state = status["state"]

        # licensed y trial = todo permitido
        if state in ("licensed", "trial"):
            return True

        # expired e invalid = solo lectura
        read_only_features = {
            "billing.list", "billing.view",
            "usb.list", "usb.view",
            "statistics.view",
            "license.activate", "license.view",
            "health",
            "auth.login",
        }
        return feature in read_only_features


# Singleton
_license_state: LicenseState | None = None


def get_license_state() -> LicenseState | None:
    return _license_state


def init_license_state(session_factory) -> LicenseState:
    global _license_state
    _license_state = LicenseState(session_factory)
    return _license_state
