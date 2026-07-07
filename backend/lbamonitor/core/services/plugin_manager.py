"""
PluginManager v4.3 — carga dinámica de plugins con verificación de firma HMAC.

Mejoras de seguridad respecto a v4.0.0/v4.2:
- Verificación HMAC obligatoria: cada plugin debe tener un archivo .sig
  con la firma HMAC-SHA256 del archivo .py, firmada con PLUGINS_SIGNING_KEY.
- Si LBAMONITOR_PLUGINS_ALLOW_UNSIGNED=1 (solo dev), se permite cargar sin firma.
- Search paths restringidos a absolutos (no cwd).
- Loggeo de cada intento de carga (éxito o fallo).
- Sanitización del nombre del plugin para evitar path traversal.

Formato del archivo .sig:
    <hmac_sha256_hex_en_una_línea>

Para firmar un plugin:
    python -c "import hmac, hashlib; print(hmac.new(b'$KEY', open('plugin.py','rb').read(), hashlib.sha256).hexdigest())" > plugin.py.sig
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Callable

from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)

SUPPORTED_EVENTS = [
    "on_usb_inserted",
    "on_usb_removed",
    "on_file_copied",
    "on_file_deleted",
    "on_payment_registered",
    "on_session_started",
    "on_session_ended",
    "on_backup_created",
    "on_license_activated",
]


class PluginManager:
    def __init__(self) -> None:
        self._plugins: dict[str, dict[str, Callable]] = {}
        self._loaded = False
        self._search_paths: list[Path] = []
        # Nota: la signing key y allow_unsigned se leen en _verify_signature
        # para que se respeten los env vars seteados después del init.

    @property
    def _signing_key_prop(self) -> bytes:
        return os.environ.get("LBAMONITOR_PLUGINS_SIGNING_KEY", "").encode("utf-8")

    @property
    def _allow_unsigned_prop(self) -> bool:
        return os.environ.get("LBAMONITOR_PLUGINS_ALLOW_UNSIGNED", "0") == "1"

    def add_search_path(self, path: str | Path) -> None:
        p = Path(path).resolve()
        if p not in self._search_paths:
            self._search_paths.append(p)

    def _get_default_paths(self) -> list[Path]:
        """Search paths absolutos (no relativos al cwd)."""
        paths: list[Path] = []
        # ProgramData (Windows) — kioscos en producción
        pd_env = os.environ.get("PROGRAMDATA", "C:/ProgramData")
        # En Linux/Mac, PROGRAMDATA no existe; usar path relativo o skip
        if pd_env and Path(pd_env).is_absolute():
            pd = Path(pd_env) / "LBAMonitor" / "plugins"
            paths.append(pd)
        # Backend plugins/ (relativo a este archivo: lbamonitor/core/services/plugin_manager.py
        # → subir 3 niveles: services → core → lbamonitor → backend → plugins/)
        bp = Path(__file__).resolve().parent.parent.parent.parent / "plugins"
        paths.append(bp)
        # Custom
        paths.extend(self._search_paths)
        return paths

    def _verify_signature(self, plugin_path: Path) -> bool:
        """
        Verifica la firma HMAC del plugin.

        - Si _allow_unsigned=True y no hay signing_key, permite sin firma (dev).
        - Si hay signing_key, requiere .sig y verifica.
        - Si no hay signing_key ni allow_unsigned, rechaza todo.
        """
        signing_key = self._signing_key_prop
        allow_unsigned = self._allow_unsigned_prop

        if allow_unsigned and not signing_key:
            log.debug(f"Plugin {plugin_path.name}: carga sin firma (modo dev)")
            return True

        if not signing_key:
            log.error(
                f"Plugin {plugin_path.name}: no hay signing_key ni allow_unsigned. "
                f"Setear LBAMONITOR_PLUGINS_SIGNING_KEY o LBAMONITOR_PLUGINS_ALLOW_UNSIGNED=1 para dev."
            )
            return False

        sig_file = plugin_path.with_suffix(".py.sig")
        if not sig_file.is_file():
            log.warning(f"Plugin {plugin_path.name}: sin archivo de firma ({sig_file.name}). Saltando.")
            return False

        try:
            expected_sig = sig_file.read_text().strip()
            actual_sig = hmac.new(
                signing_key,
                plugin_path.read_bytes(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected_sig, actual_sig):
                log.error(f"Plugin {plugin_path.name}: firma inválida. Saltando.")
                return False
            return True
        except Exception as e:
            log.error(f"Plugin {plugin_path.name}: error verificando firma: {e}")
            return False

    def load_all(self) -> int:
        """Carga todos los plugins firmados de los search paths."""
        if self._loaded:
            return len(self._plugins)

        count = 0
        for sp in self._get_default_paths():
            if not sp.is_dir():
                continue
            for pf in sp.glob("*.py"):
                if pf.name.startswith("_") or pf.name.startswith("."):
                    continue
                try:
                    if self._load_plugin(pf, pf.stem):
                        count += 1
                except Exception as e:
                    log.warning(f"Error cargando {pf.name}: {e}")

        if count > 0:
            log.info(f"{count} plugin(s) cargado(s)")
            for n, e in self._plugins.items():
                log.info(f"  '{n}': {list(e.keys())}")
        else:
            log.debug("No se cargaron plugins")

        self._loaded = True
        return count

    def _load_plugin(self, fp: Path, pn: str) -> bool:
        """Carga un plugin. Devuelve True si se cargó, False si se rechazó."""
        # Sanitizar nombre del plugin (prevenir path traversal)
        safe_name = "".join(c for c in pn if c.isalnum() or c in ("_", "-"))
        if not safe_name or safe_name != pn:
            log.warning(f"Nombre de plugin inválido: {pn!r}. Saltando.")
            return False

        # Verificar firma HMAC
        if not self._verify_signature(fp):
            return False

        # Cargar módulo
        spec = importlib.util.spec_from_file_location(safe_name, fp)
        if not spec or not spec.loader:
            raise RuntimeError(f"No spec for {fp}")
        m = importlib.util.module_from_spec(spec)
        sys.modules[safe_name] = m
        spec.loader.exec_module(m)

        # Extraer handlers de eventos soportados
        events: dict[str, Callable] = {}
        for en in SUPPORTED_EVENTS:
            f = getattr(m, en, None)
            if f and callable(f):
                events[en] = f
        if events:
            self._plugins[safe_name] = events
            log.debug(f"Plugin '{safe_name}': {list(events.keys())}")
            return True
        return False

    def dispatch(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Dispara un evento a todos los plugins que lo manejen."""
        if not self._loaded:
            return
        if event_name not in SUPPORTED_EVENTS:
            return
        for pn, events in self._plugins.items():
            f = events.get(event_name)
            if not f:
                continue
            try:
                f(*args, **kwargs)
            except Exception as e:
                log.warning(f"Error en plugin '{pn}' evento '{event_name}': {e}", exc_info=True)

    def list_plugins(self) -> list[dict[str, Any]]:
        return [{"name": n, "events": list(e.keys())} for n, e in self._plugins.items()]

    def unload_all(self) -> None:
        self._plugins.clear()
        self._loaded = False


_pm: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    global _pm
    if _pm is None:
        _pm = PluginManager()
    return _pm
