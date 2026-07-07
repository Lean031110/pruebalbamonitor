"""
Motor de licencias: Machine ID por WMI + licencia HMAC/RSA firmada.

Funciona 100% offline (sin activación online).

Modelo:
  1. En la máquina cliente: compute_machine_id() → SHA-256 de varios componentes WMI.
  2. El usuario envía ese Machine ID al licensor (por WhatsApp/recarga/email).
  3. El licensor genera una licencia firmada (HMAC o RSA) con su clave secreta.
  4. La licencia se persiste en key_values.license.
  5. Al arrancar, el servicio verifica que la licencia coincide con el HWID local.

Soporta:
  - HMAC-SHA256 con secret compartido (rápido, simple)
  - RSA-2048 con public_key_pem (más seguro, no requiere compartir secret)
  - Tolerancia configurable: número de caracteres HWID que pueden diferir
    (Levenshtein distance) sin invalidar la licencia. Útil cuando un componente
    de hardware cambia ligeramente (BIOS update, RAM swap, etc.)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from lbamonitor.utils.helpers import hmac_sha256_hex, sha256_hex, utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Machine ID
# ---------------------------------------------------------------------------

def _query_wmi_class(class_name: str, fields: list[str]) -> dict[str, str]:
    """
    Consulta una clase WMI y devuelve los campos pedidos.

    En Linux/Mac devuelve dict vacío (no WMI disponible).
    """
    if not _is_windows():
        return {}

    try:
        import wmi  # type: ignore
        c = wmi.WMI()
        result = {}
        for cls in getattr(c, class_name, None)() or []:
            for f in fields:
                val = getattr(cls, f, None)
                if val is not None:
                    result[f] = str(val)
            if result:
                break  # Solo el primer objeto
        return result
    except Exception as e:
        log.warning(f"No se pudo consultar WMI {class_name}: {e}")
        return {}


def _is_windows() -> bool:
    import os
    return os.name == "nt"


def compute_machine_id() -> str:
    """
    Calcula el Machine ID (HWID) estable de esta máquina.

    Combina:
      - Win32_Processor.ProcessorId
      - Win32_BIOS.SerialNumber
      - Win32_BaseBoard.SerialNumber
      - Win32_ComputerSystemProduct.UUID

    Devuelve SHA-256 hex del JSON canónico con todos los campos.

    En máquinas no-Windows devuelve un hash de hostname (solo para desarrollo).
    """
    components: dict[str, str] = {}

    if _is_windows():
        # CPU
        cpu = _query_wmi_class("Win32_Processor", ["ProcessorId", "Name", "Manufacturer"])
        components["cpu"] = cpu.get("ProcessorId", "") or cpu.get("Name", "")

        # BIOS
        bios = _query_wmi_class(
            "Win32_BIOS",
            ["Manufacturer", "SerialNumber", "SMBIOSBIOSVersion", "IdentificationCode"],
        )
        components["bios"] = bios.get("SerialNumber", "") or bios.get("Manufacturer", "")

        # BaseBoard
        board = _query_wmi_class(
            "Win32_BaseBoard", ["Manufacturer", "SerialNumber", "Model"]
        )
        components["board"] = board.get("SerialNumber", "") or board.get("Manufacturer", "")

        # ComputerSystemProduct UUID
        csp = _query_wmi_class(
            "Win32_ComputerSystemProduct", ["UUID", "IdentifyingNumber"]
        )
        components["uuid"] = csp.get("UUID", "") or csp.get("IdentifyingNumber", "")
    else:
        import platform
        components["hostname"] = platform.node() or "unknown"

    # Limpiar valores vacíos / placeholder
    cleaned = {}
    placeholders = {
        "", "to be filled by o.e.m.", "none", "default string",
        "system serial number", "0", "00000000-0000-0000-0000-000000000000",
    }
    for k, v in components.items():
        if v and v.lower().strip() not in placeholders:
            cleaned[k] = v.strip()

    # JSON canónico ordenado
    canonical = json.dumps(cleaned, sort_keys=True, ensure_ascii=False)
    hwid = sha256_hex(canonical)
    log.debug(f"HWID components: {cleaned}")
    log.debug(f"HWID = {hwid}")
    return hwid


# ---------------------------------------------------------------------------
# Licencia HMAC (esquema simple, offline)
# ---------------------------------------------------------------------------

def generate_license(
    machine_id: str,
    expires: str | None,
    tier: str = "pro",
    secret: str = "",
    private_key_pem: str = "",
) -> str:
    """
    Genera una licencia firmada.

    Si se provee `private_key_pem`, usa RSA-2048 (más seguro, no comparte secret).
    Si no, usa HMAC-SHA256 con `secret`.

    Formato del payload: JSON con {hwid, expires, tier, issued_at}.
    La licencia final es base64(payload_json) + "." + signature_hex (HMAC) o
    base64(payload_json) + "." + base64(signature_rsa).

    Uso: el licensor ejecuta esto en su PC y le entrega el string al cliente.
    """
    if not secret and not private_key_pem:
        raise ValueError("Se requiere `secret` (HMAC) o `private_key_pem` (RSA)")

    payload: dict[str, Any] = {
        "hwid": machine_id,
        "tier": tier,
        "issued_at": utcnow().isoformat(),
    }
    if expires:
        payload["expires"] = expires

    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    import base64
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii").rstrip("=")

    if private_key_pem:
        # RSA signature
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode("utf-8"), password=None
            )
            signature = private_key.sign(
                payload_b64.encode("ascii"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            sig_b64 = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
            license_str = f"{payload_b64}.{sig_b64}"
            log.info(f"Licencia RSA generada para HWID={machine_id[:16]}... tier={tier}")
            return license_str
        except ImportError:
            log.warning("cryptography no instalado. Fallback a HMAC.")
            if not secret:
                raise ValueError("RSA requiere librería `cryptography`. Instalar o usar HMAC.")

    # HMAC
    signature = hmac_sha256_hex(secret, payload_b64)
    license_str = f"{payload_b64}.{signature}"
    log.info(f"Licencia HMAC generada para HWID={machine_id[:16]}... tier={tier}")
    return license_str


def _hamming_distance_hex(a: str, b: str) -> int:
    """
    Distancia de Hamming sobre strings hex: cuenta caracteres diferentes.
    Más eficiente que Levenshtein para HWID (misma longitud siempre).
    """
    if len(a) != len(b):
        return max(len(a), len(b))  # Diferentes longitudes = máxima distancia
    return sum(c1 != c2 for c1, c2 in zip(a, b))


def verify_license(
    license_str: str,
    machine_id: str,
    secret: str = "",
    public_key_pem: str = "",
    tolerance: int = 0,
) -> dict[str, Any]:
    """
    Verifica una licencia contra el HWID local.

    Args:
        license_str: string de licencia (formato `payload.signature`).
        machine_id: HWID local.
        secret: clave secreta HMAC (debe coincidir con la usada al generar).
        public_key_pem: clave pública RSA PEM (alternativa a HMAC).
        tolerance: número de caracteres HWID que pueden diferir sin invalidar.
                   0 = comparación exacta. Recomendado: 0-4.

    Devuelve dict con: valid (bool), tier, expires, issued_at, reason (str).
    """
    import base64
    import secrets as sec

    if not license_str or "." not in license_str:
        return {"valid": False, "reason": "Formato de licencia inválido"}

    try:
        payload_b64, signature = license_str.split(".", 1)
        # Re-pad base64
        padding = "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception as e:
        return {"valid": False, "reason": f"Payload inválido: {e}"}

    # Verificar firma (RSA o HMAC)
    if public_key_pem:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.exceptions import InvalidSignature
            public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
            sig_bytes = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
            try:
                public_key.verify(
                    sig_bytes,
                    payload_b64.encode("ascii"),
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
                sig_valid = True
            except InvalidSignature:
                sig_valid = False
        except ImportError:
            return {"valid": False, "reason": "cryptography no instalado (requerido para RSA)"}
    elif secret:
        expected_sig = hmac_sha256_hex(secret, payload_b64)
        sig_valid = sec.compare_digest(expected_sig, signature)
    else:
        return {"valid": False, "reason": "No se proveyó `secret` ni `public_key_pem`"}

    if not sig_valid:
        return {"valid": False, "reason": "Firma inválida"}

    # Verificar HWID con tolerancia
    license_hwid = payload.get("hwid", "")
    if tolerance > 0:
        distance = _hamming_distance_hex(license_hwid, machine_id)
        if distance > tolerance:
            return {
                "valid": False,
                "reason": (
                    f"HWID no coincide (distancia={distance}, tolerancia={tolerance}). "
                    f"Licencia para {license_hwid[:16]}..."
                ),
            }
    else:
        # Comparación exacta (default)
        if license_hwid != machine_id:
            return {
                "valid": False,
                "reason": f"HWID no coincide (licencia para {license_hwid[:16]}...)",
            }

    # Verificar expiración (en UTC)
    expires = payload.get("expires")
    if expires:
        try:
            exp_date = datetime.fromisoformat(expires)
            # Si es naive, asumir UTC
            if exp_date.tzinfo is None:
                exp_date = exp_date.replace(tzinfo=timezone.utc)
            if utcnow() > exp_date:
                return {"valid": False, "reason": f"Licencia expirada el {expires}"}
        except ValueError:
            log.warning(f"Fecha de expiración inválida en licencia: {expires}")

    return {
        "valid": True,
        "tier": payload.get("tier", "pro"),
        "expires": expires,
        "issued_at": payload.get("issued_at"),
        "reason": "OK",
    }
