"""Router de settings (KeyValue + BusinessInfo + PublicityFolder + secciones tipadas)."""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.api.deps import bad_request, not_found
from lbamonitor.api.schemas.common import MessageResponse
from lbamonitor.api.schemas.settings import (
    AppearanceSettingsResponse,
    AppearanceSettingsUpdate,
    BackupSettingsResponse,
    BackupSettingsUpdate,
    BusinessInfo,
    ConfigurationResponse,
    ConfigurationUpdate,
    KeyValueResponse,
    KeyValueUpdate,
    LicenseConfigResponse,
    LoggingSettingsResponse,
    LoggingSettingsUpdate,
    MonitoringSettingsResponse,
    MonitoringSettingsUpdate,
    OrderCopiesBy,
    PricingSettingsResponse,
    PricingSettingsUpdate,
    PublicityFolder,
    RewardRuleCreate,
    RewardRuleResponse,
    RewardRuleUpdate,
    ServerSettingsResponse,
    ServerSettingsUpdate,
    SettingResponse,
    SettingsListResponse,
    VideoFolders,
)
from lbamonitor.core.config import get_settings, reload_settings
from lbamonitor.core.db import get_db
from lbamonitor.core.models import KeyValue, User
from lbamonitor.core.security.auth import require_admin, require_operator
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

async def _get_kv(db: AsyncSession, key: str) -> Optional[KeyValue]:
    result = await db.execute(select(KeyValue).where(KeyValue.key == key))
    return result.scalar_one_or_none()


async def _set_kv(db: AsyncSession, key: str, value: str) -> None:
    kv = await _get_kv(db, key)
    if kv:
        kv.value = value
    else:
        db.add(KeyValue(key=key, value=value))


def _section_dict(settings_obj: Any) -> dict:
    """Convierte una sub-sección de Settings (Pydantic BaseModel) a dict."""
    if hasattr(settings_obj, "model_dump"):
        return settings_obj.model_dump()
    return dict(settings_obj)


def _apply_to_settings(section: str, data: dict) -> None:
    """Mutate in-memory cached Settings so consumers (PricingEngine, etc.) see the change."""
    try:
        s = get_settings()
        sub = getattr(s, section, None)
        if sub is None:
            return
        for k, v in data.items():
            if hasattr(sub, k):
                setattr(sub, k, v)
    except Exception as e:  # pragma: no cover — best-effort
        log.warning(f"_apply_to_settings({section}) failed: {e}")


async def _persist_section(
    db: AsyncSession,
    section: str,
    payload_dict: dict,
    response_model_cls: type,
) -> Any:
    """
    Persiste una sección tipada en KeyValue bajo la clave ``config.<section>``.

    Estrategia:
    1. Lee el JSON actual de la KV (si existe).
    2. Mergea (deep) los campos enviados sobre los existentes.
    3. Persiste el JSON resultante.
    4. Aplica los cambios al objeto Settings en memoria (para que PricingEngine
       y otros servicios que lean ``get_settings().<section>`` vean el cambio).
    5. Devuelve el modelo de respuesta con la configuración final.

    Nota: NO llamamos a ``reload_settings()`` porque limpiaría el cache y
    re-leería desde config.toml/env vars, perdiendo los cambios aplicados.
    La mutación in-memory + persistencia KV garantiza que:
      - En esta sesión del proceso: todos los consumidores ven el nuevo valor.
      - Tras reinicio: el GET correspondiente leerá de KV y devolverá lo guardado.
    """
    kv_key = f"config.{section}"
    existing = await _get_kv(db, kv_key)
    current: dict = {}
    if existing and existing.value:
        try:
            current = json.loads(existing.value) or {}
        except Exception:
            current = {}
    # Deep merge: payload sobrescribe current
    merged = _deep_merge(current, payload_dict)
    await _set_kv(db, kv_key, json.dumps(merged, ensure_ascii=False))
    await db.commit()
    # Aplicar al Settings in-memory
    _apply_to_settings(section, merged)
    return response_model_cls(**merged)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _section_response(settings_obj: Any, response_model_cls: type) -> Any:
    """Construye la respuesta a partir de un objeto Settings (sub-sección)."""
    return response_model_cls(**_section_dict(settings_obj))


async def _read_section_or_default(
    db: AsyncSession,
    section: str,
    settings_obj: Any,
    response_model_cls: type,
) -> Any:
    """Lee la sección desde KV; si no existe, devuelve el valor por defecto de Settings."""
    kv = await _get_kv(db, f"config.{section}")
    if kv and kv.value:
        try:
            data = json.loads(kv.value)
            # Sincronizar también al objeto in-memory por si se reinició el proceso
            # y la KV tiene valores más nuevos que config.toml.
            _apply_to_settings(section, data)
            return response_model_cls(**data)
        except Exception:
            pass
    return _section_response(settings_obj, response_model_cls)


# ---------------------------------------------------------------------------
# Tipos compuestos (RUTAS ESPECÍFICAS PRIMERO para que no las captura /{key})
# ---------------------------------------------------------------------------

# BusinessInfo
@router.get("/business-info", response_model=BusinessInfo)
async def get_business_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    s = get_settings().business
    kv = await _get_kv(db, "business_info")
    if kv and kv.value:
        try:
            return BusinessInfo(**json.loads(kv.value))
        except Exception:
            pass
    return BusinessInfo(name=s.name, marketing_text="", address=s.address)


@router.put("/business-info", response_model=BusinessInfo)
async def set_business_info(
    payload: BusinessInfo,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    await _set_kv(db, "business_info", payload.model_dump_json())
    await db.commit()
    return payload


# PublicityFolder
@router.get("/publicity-folder", response_model=PublicityFolder)
async def get_publicity_folder(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    s = get_settings().paths
    kv = await _get_kv(db, "publicity_folder")
    if kv and kv.value:
        try:
            return PublicityFolder(**json.loads(kv.value))
        except Exception:
            pass
    return PublicityFolder(folder_path=s.publicity_folder, automatic=s.publicity_automatic)


@router.put("/publicity-folder", response_model=PublicityFolder)
async def set_publicity_folder(
    payload: PublicityFolder,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    await _set_kv(db, "publicity_folder", payload.model_dump_json())
    await db.commit()
    return payload


# VideoFolders
@router.get("/video-folders", response_model=VideoFolders)
async def get_video_folders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    s = get_settings().paths
    kv = await _get_kv(db, "video_folders")
    if kv and kv.value:
        try:
            return VideoFolders(**json.loads(kv.value))
        except Exception:
            pass
    return VideoFolders(folders=s.video_folders)


@router.put("/video-folders", response_model=VideoFolders)
async def set_video_folders(
    payload: VideoFolders,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    await _set_kv(db, "video_folders", payload.model_dump_json())
    await db.commit()
    return payload


# OrderCopiesBy
@router.get("/order-copies-by", response_model=OrderCopiesBy)
async def get_order_copies_by(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    kv = await _get_kv(db, "order_copies_by")
    if kv and kv.value:
        return OrderCopiesBy(value=kv.value)
    return OrderCopiesBy(value="date")


@router.put("/order-copies-by", response_model=OrderCopiesBy)
async def set_order_copies_by(
    payload: OrderCopiesBy,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if payload.value not in ("date", "size", "name", "extension"):
        raise bad_request("order_copies_by debe ser: date|size|name|extension")
    await _set_kv(db, "order_copies_by", payload.value)
    await db.commit()
    return payload


# PaymentHidden
@router.get("/payment-hidden", response_model=SettingResponse)
async def get_payment_hidden(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    kv = await _get_kv(db, "payment_hidden")
    val = kv.value == "true" if kv else False
    return SettingResponse(key="payment_hidden", value=val, type="bool")


@router.put("/payment-hidden", response_model=SettingResponse)
async def set_payment_hidden(
    payload: SettingResponse,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    val = "true" if payload.value else "false"
    await _set_kv(db, "payment_hidden", val)
    await db.commit()
    return SettingResponse(key="payment_hidden", value=payload.value, type="bool")


# ---------------------------------------------------------------------------
# Secciones tipadas: pricing / monitoring / backup / logging / appearance / server
# ---------------------------------------------------------------------------

# --- Pricing ----------------------------------------------------------------
VALID_PRICING_MODES = {"per_gb", "per_mb", "per_file", "fixed", "custom"}


@router.get("/pricing", response_model=PricingSettingsResponse)
async def get_pricing(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Devuelve la configuración actual de precios y descuentos."""
    return await _read_section_or_default(
        db, "pricing", get_settings().pricing, PricingSettingsResponse
    )


@router.put("/pricing", response_model=PricingSettingsResponse)
async def update_pricing(
    payload: PricingSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualiza campos de pricing (per_gb, descuentos VIP, promociones, etc.)."""
    data = payload.model_dump(exclude_unset=True)
    if "mode" in data and data["mode"] not in VALID_PRICING_MODES:
        raise bad_request(f"mode debe ser uno de {sorted(VALID_PRICING_MODES)}")
    if "min_price" in data and "max_price" in data and data["min_price"] > data["max_price"]:
        raise bad_request("min_price no puede ser mayor que max_price")
    if "vip_discount_percent" in data and not (0 <= data["vip_discount_percent"] <= 100):
        raise bad_request("vip_discount_percent debe estar entre 0 y 100")
    if "employee_discount_percent" in data and not (0 <= data["employee_discount_percent"] <= 100):
        raise bad_request("employee_discount_percent debe estar entre 0 y 100")
    if "promotion_discount_percent" in data and not (0 <= data["promotion_discount_percent"] <= 100):
        raise bad_request("promotion_discount_percent debe estar entre 0 y 100")
    return await _persist_section(db, "pricing", data, PricingSettingsResponse)


# --- Monitoring -------------------------------------------------------------
@router.get("/monitoring", response_model=MonitoringSettingsResponse)
async def get_monitoring(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Devuelve la configuración actual de monitoreo (intervalos, filtros)."""
    return await _read_section_or_default(
        db, "monitoring", get_settings().monitoring, MonitoringSettingsResponse
    )


@router.put("/monitoring", response_model=MonitoringSettingsResponse)
async def update_monitoring(
    payload: MonitoringSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualiza intervalos de polling, filtros de archivos, etc."""
    data = payload.model_dump(exclude_unset=True)
    if "mtp_poll_interval_seconds" in data and data["mtp_poll_interval_seconds"] < 1:
        raise bad_request("mtp_poll_interval_seconds debe ser >= 1")
    if "fs_watcher_buffer" in data and data["fs_watcher_buffer"] < 1024:
        raise bad_request("fs_watcher_buffer debe ser >= 1024")
    if "fs_debounce_ms" in data and data["fs_debounce_ms"] < 0:
        raise bad_request("fs_debounce_ms debe ser >= 0")
    return await _persist_section(db, "monitoring", data, MonitoringSettingsResponse)


# --- Backup -----------------------------------------------------------------
@router.get("/backup", response_model=BackupSettingsResponse)
async def get_backup(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Devuelve la configuración actual de backups (hora, días, destino)."""
    return await _read_section_or_default(
        db, "backup", get_settings().backup, BackupSettingsResponse
    )


@router.put("/backup", response_model=BackupSettingsResponse)
async def update_backup(
    payload: BackupSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualiza hora de backup, días a conservar, destino, etc."""
    data = payload.model_dump(exclude_unset=True)
    if "hour" in data and not (0 <= data["hour"] <= 23):
        raise bad_request("hour debe estar entre 0 y 23")
    if "keep_days" in data and data["keep_days"] < 1:
        raise bad_request("keep_days debe ser >= 1")
    return await _persist_section(db, "backup", data, BackupSettingsResponse)


# --- Logging ----------------------------------------------------------------
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "TRACE"}


@router.get("/logging", response_model=LoggingSettingsResponse)
async def get_logging(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Devuelve la configuración actual de logging (nivel, rotación, path)."""
    return await _read_section_or_default(
        db, "logging", get_settings().logging, LoggingSettingsResponse
    )


@router.put("/logging", response_model=LoggingSettingsResponse)
async def update_logging(
    payload: LoggingSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualiza nivel de log, rotación, retención, path, etc."""
    data = payload.model_dump(exclude_unset=True)
    if "level" in data and data["level"].upper() not in VALID_LOG_LEVELS:
        raise bad_request(f"level debe ser uno de {sorted(VALID_LOG_LEVELS)}")
    if "level" in data:
        data["level"] = data["level"].upper()
    return await _persist_section(db, "logging", data, LoggingSettingsResponse)


# --- Appearance -------------------------------------------------------------
VALID_LANGS = {"es", "en", "pt"}
VALID_THEMES = {"dark", "light", "auto"}


@router.get("/appearance", response_model=AppearanceSettingsResponse)
async def get_appearance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Devuelve idioma y tema de la UI."""
    return await _read_section_or_default(
        db, "appearance", get_settings().appearance, AppearanceSettingsResponse
    )


@router.put("/appearance", response_model=AppearanceSettingsResponse)
async def update_appearance(
    payload: AppearanceSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualiza idioma y tema de la UI."""
    data = payload.model_dump(exclude_unset=True)
    if "language" in data and data["language"] not in VALID_LANGS:
        raise bad_request(f"language debe ser uno de {sorted(VALID_LANGS)}")
    if "theme" in data and data["theme"] not in VALID_THEMES:
        raise bad_request(f"theme debe ser uno de {sorted(VALID_THEMES)}")
    return await _persist_section(db, "appearance", data, AppearanceSettingsResponse)


# --- Server -----------------------------------------------------------------
@router.get("/server", response_model=ServerSettingsResponse)
async def get_server(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Devuelve host/port/workers/CORS/docs_enabled."""
    return await _read_section_or_default(
        db, "server", get_settings().server, ServerSettingsResponse
    )


@router.put("/server", response_model=ServerSettingsResponse)
async def update_server(
    payload: ServerSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualiza host/port/workers/CORS/docs_enabled.

    Nota: los cambios de host/port/workers requieren reiniciar el servidor
    para que surtan efecto.
    """
    data = payload.model_dump(exclude_unset=True)
    if "port" in data and not (1 <= data["port"] <= 65535):
        raise bad_request("port debe estar entre 1 y 65535")
    if "workers" in data and data["workers"] < 1:
        raise bad_request("workers debe ser >= 1")
    return await _persist_section(db, "server", data, ServerSettingsResponse)


# --- License config (read-only) ---------------------------------------------
@router.get("/license-config", response_model=LicenseConfigResponse)
async def get_license_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Devuelve la configuración de licencia (read-only).

    Para activar una licencia, usar ``POST /api/license/activate``.
    """
    s = get_settings().license
    # Verificar si hay licencia persistida en BD
    kv = await _get_kv(db, "license.key")
    has_key = bool((kv and kv.value) or s.key)
    return LicenseConfigResponse(
        mode=s.mode,
        hwid_tolerance=s.hwid_tolerance,
        has_key=has_key,
        has_signing_secret=bool(s.signing_secret),
        has_public_key=bool(s.public_key_pem),
        has_private_key=bool(s.private_key_pem),
    )


# ---------------------------------------------------------------------------
# RewardRules (persistidas como JSON en KV: clave ``reward_rules``)
# ---------------------------------------------------------------------------

def _default_reward_rules() -> list[dict]:
    """Reglas por defecto si no existe ninguna en BD."""
    return [
        {
            "rule_id": "frequent_client_30d",
            "name": "Cliente frecuente (30 días)",
            "enabled": True,
            "priority": 10,
            "auto_apply": False,
            "trigger": "visit_milestone",
            "condition": {"min_visits": 10, "window_days": 30},
            "reward_type": "discount",
            "reward_value": 15.0,
            "description": "10% descuento tras 10 visitas en 30 días",
            "expires_in_days": 30,
        },
        {
            "rule_id": "gb_milestone_500",
            "name": "Recompensa 500 GB copiados",
            "enabled": True,
            "priority": 20,
            "auto_apply": True,
            "trigger": "gb_milestone",
            "condition": {"min_gb": 500},
            "reward_type": "free",
            "reward_value": 1.0,
            "description": "1 copia gratis tras 500 GB acumulados",
            "expires_in_days": 60,
        },
        {
            "rule_id": "spent_milestone_5000",
            "name": "Recompensa 5000 gastados",
            "enabled": True,
            "priority": 30,
            "auto_apply": True,
            "trigger": "spent_milestone",
            "condition": {"min_spent": 5000},
            "reward_type": "bonus",
            "reward_value": 100.0,
            "description": "100 puntos bonus tras 5000 acumulados",
            "expires_in_days": None,
        },
        {
            "rule_id": "monthly_top_client",
            "name": "Cliente del mes",
            "enabled": False,
            "priority": 50,
            "auto_apply": False,
            "trigger": "monthly",
            "condition": {"rank": 1},
            "reward_type": "gift",
            "reward_value": None,
            "description": "Cliente con más gasto en el mes recibe un regalo",
            "expires_in_days": 30,
        },
    ]


async def _read_reward_rules(db: AsyncSession) -> list[dict]:
    kv = await _get_kv(db, "reward_rules")
    if kv and kv.value:
        try:
            data = json.loads(kv.value)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return _default_reward_rules()


async def _write_reward_rules(db: AsyncSession, rules: list[dict]) -> None:
    await _set_kv(db, "reward_rules", json.dumps(rules, ensure_ascii=False))
    await db.commit()


@router.get("/reward-rules", response_model=list[RewardRuleResponse])
async def list_reward_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Lista todas las reglas de recompensa configuradas."""
    rules = await _read_reward_rules(db)
    return [RewardRuleResponse(**r) for r in rules]


@router.post("/reward-rules", response_model=RewardRuleResponse, status_code=201)
async def create_reward_rule(
    payload: RewardRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Crea una nueva regla de recompensa."""
    rules = await _read_reward_rules(db)
    # Validar uniqueness de rule_id
    if any(r.get("rule_id") == payload.rule_id for r in rules):
        raise bad_request(f"Ya existe una regla con rule_id={payload.rule_id!r}")
    new_rule = payload.model_dump()
    rules.append(new_rule)
    await _write_reward_rules(db, rules)
    return RewardRuleResponse(**new_rule)


@router.put("/reward-rules/{rule_id}", response_model=RewardRuleResponse)
async def update_reward_rule(
    rule_id: str,
    payload: RewardRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Actualiza una regla de recompensa existente."""
    rules = await _read_reward_rules(db)
    idx = next((i for i, r in enumerate(rules) if r.get("rule_id") == rule_id), None)
    if idx is None:
        raise not_found(f"Regla {rule_id!r} no encontrada")
    updates = payload.model_dump(exclude_unset=True)
    rules[idx].update(updates)
    await _write_reward_rules(db, rules)
    return RewardRuleResponse(**rules[idx])


@router.delete("/reward-rules/{rule_id}", response_model=MessageResponse)
async def delete_reward_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Elimina una regla de recompensa."""
    rules = await _read_reward_rules(db)
    new_rules = [r for r in rules if r.get("rule_id") != rule_id]
    if len(new_rules) == len(rules):
        raise not_found(f"Regla {rule_id!r} no encontrada")
    await _write_reward_rules(db, new_rules)
    return MessageResponse(message=f"Regla {rule_id!r} eliminada")


# ---------------------------------------------------------------------------
# KeyValue genérico (DESPUÉS de las rutas específicas)
# ---------------------------------------------------------------------------

@router.get("", response_model=list[KeyValueResponse])
async def list_keyvalues(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    result = await db.execute(select(KeyValue).order_by(KeyValue.key))
    return [KeyValueResponse.model_validate(kv) for kv in result.scalars().all()]


@router.get("/{key}", response_model=KeyValueResponse)
async def get_keyvalue(
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    result = await db.execute(select(KeyValue).where(KeyValue.key == key))
    kv = result.scalar_one_or_none()
    if not kv:
        raise not_found(f"Setting '{key}' no encontrada")
    return KeyValueResponse.model_validate(kv)


@router.put("/{key}", response_model=KeyValueResponse)
async def set_keyvalue(
    key: str,
    payload: KeyValueUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(KeyValue).where(KeyValue.key == key))
    kv = result.scalar_one_or_none()
    if kv:
        kv.value = payload.value
    else:
        kv = KeyValue(key=key, value=payload.value)
        db.add(kv)
    await db.commit()
    await db.refresh(kv)
    return KeyValueResponse.model_validate(kv)
