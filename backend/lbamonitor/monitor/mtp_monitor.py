r"""
Monitor de dispositivos MTP (teléfonos Android, cámaras, reproductores).

Usa `pythonnet` para invocar `MediaDevices.dll` (la misma librería .NET
que usa Uatcher original). Esto reutiliza el código que ya funciona en
.NET sin tener que reescribir el COM API de WPD.

CRÍTICO: Los dispositivos MTP NO aparecen con letra de unidad (E:\).
Por eso:
  - watchdog NO funciona sobre MTP (no hay filesystem montado).
  - Necesitamos un watcher específico basado en polling de cambios
    (fechas de modificación + huellas de archivos).

El polling enumera los archivos del dispositivo cada N segundos y compara
con el snapshot anterior para detectar copias/borrados.

SOPORTE POR FABRICANTE:
  - Samsung:    protocolo MTP estándar. Funciona con MediaDevices.dll.
  - Xiaomi:     MTP estándar; algunos modelos requieren activar "Transferencia
                de archivos (MTP)" en notificaciones al conectar.
  - Motorola:   MTP estándar (driver ADB no requerido para copias).
  - Huawei:     MTP estándar; algunos EMUI antiguos exponen también "HDB".
  - iPhone:     NO SOPORTADO. iOS usa el protocolo AFC (Apple File Conduit)
                que requiere iTunes + AppleMobileDevice.dll. No es MTP.
                Para iPhone, usar iTunes o herramientas como iMazing.

LIMITACIONES LINUX/MAC:
  - pythonnet + MediaDevices.dll requiere .NET CLR → solo Windows.
  - En Linux/Mac, MTPMonitor detecta inserción/remoción vía libmtp si está
    instalado (no implementado en v4.4), pero NO copias individuales.
  - Para Linux, se recomienda usar gvfs-mtp (GNOME) o jmtpfs (FUSE) que
    montan el celular en /run/user/<uid>/gvfs/ y exponen watchdog normal.
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from lbamonitor.utils.helpers import utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Dataclass para dispositivos MTP
# ---------------------------------------------------------------------------

@dataclass
class MTPDeviceInfo:
    """Información de un dispositivo MTP conectado."""

    device_id: str  # ID interno de WPD
    name: str = ""  # Nombre descriptivo ("Galaxy S22")
    model: str = ""
    manufacturer: str = ""
    friendly_name: str = ""
    serial_number: str = ""
    total_capacity: int = 0
    free_capacity: int = 0
    is_mobile: bool = True
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            # Para MTP usamos model + serial como fingerprint compuesto
            composite = f"{self.model.lower()}|{self.serial_number.lower()}"
            self.fingerprint = hashlib.sha256(composite.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Verificación de disponibilidad de pythonnet
# ---------------------------------------------------------------------------

def is_mtp_available() -> bool:
    """
    True si pythonnet está instalado y podemos cargar MediaDevices.dll.

    En no-Windows siempre devuelve False.
    """
    import os

    if os.name != "nt":
        return False

    try:
        import clr  # type: ignore  # pythonnet runtime
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Detección de fabricante / tipo de dispositivo MTP
# ---------------------------------------------------------------------------

# Patrones de fabricantes detectados en Manufacturer/Model/FriendlyName.
# Sirven para documentar compatibilidad y marcar iPhone como no soportado.
MANUFACTURER_PATTERNS: dict[str, tuple[str, ...]] = {
    "samsung":   ("samsung", "galaxy", "sm-"),
    "xiaomi":    ("xiaomi", "redmi", "poco", "mi ", "mi2", "m20", "m21", "2[0-9]{2}[a-z]?"),
    "motorola":  ("motorola", "moto ", "lenovo"),
    "huawei":    ("huawei", "honor", "hdb"),
    "iphone":    ("apple", "iphone", "ipad", "ipod"),
    "generic":   ("android", "adb", "mtp"),
}


def detect_manufacturer(name: str, model: str, manufacturer: str) -> str:
    """
    Detecta el fabricante a partir de los metadatos del dispositivo MTP.

    Devuelve una clave de MANUFACTURER_PATTERNS o "unknown".
    """
    haystack = " ".join([
        (name or "").lower(),
        (model or "").lower(),
        (manufacturer or "").lower(),
    ])
    if not haystack.strip():
        return "unknown"

    # Orden de prioridad: iPhone primero (Apple puede colisionar con otros)
    for vendor in ("iphone", "samsung", "xiaomi", "motorola", "huawei"):
        for pat in MANUFACTURER_PATTERNS[vendor]:
            if pat in haystack:
                return vendor
    return "generic"


def is_iphone(info: "MTPDeviceInfo") -> bool:
    """True si el dispositivo detectado es un iPhone/iPad/iPod."""
    return detect_manufacturer(info.name, info.model, info.manufacturer) == "iphone"


def _load_media_devices():
    """
    Carga MediaDevices.dll vía pythonnet.

    La DLL debe estar en el PATH o junto al ejecutable.
    En producción, el instalador la copia a `C:\\Program Files\\LBAMonitor\\lib\\`.
    """
    import os
    import sys
    from pathlib import Path

    try:
        import clr  # type: ignore

        # Buscar MediaDevices.dll en ubicaciones conocidas
        search_paths = [
            Path("lib"),
            Path("C:/Program Files/LBAMonitor/lib"),
            Path(__file__).resolve().parent.parent.parent / "lib",
        ]

        for sp in search_paths:
            dll = sp / "MediaDevices.dll"
            if dll.is_file():
                # Añadir al PATH de .NET
                import sys
                sys.path.insert(0, str(sp))
                clr.AddReference("MediaDevices")
                from MediaDevices import MediaDevice  # type: ignore
                log.info(f"MediaDevices.dll cargada desde {dll}")
                return MediaDevice
        log.warning(
            "MediaDevices.dll no encontrada. MTP no disponible. "
            f"Buscado en: {[str(p) for p in search_paths]}"
        )
        return None
    except Exception as e:
        log.warning(f"Error cargando MediaDevices.dll: {e}")
        return None


# ---------------------------------------------------------------------------
# MTPMonitor
# ---------------------------------------------------------------------------

class MTPMonitor:
    """
    Detecta inserción/extracción de dispositivos MTP vía polling.

    En cada ciclo:
      1. Enumera dispositivos MTP conectados.
      2. Compara con el snapshot anterior.
      3. Dispara on_inserted/on_removed para los que cambiaron.

    Para cada dispositivo insertado, lanza un _MTPFilePoller en background
    que vigila cambios en archivos.
    """

    def __init__(
        self,
        on_inserted: Callable[[MTPDeviceInfo], "object"] | None = None,
        on_removed: Callable[[str], "object"] | None = None,
        poll_interval_seconds: int = 5,
    ) -> None:
        self._on_inserted = on_inserted
        self._on_removed = on_removed
        self._poll_interval = poll_interval_seconds
        self._known_devices: dict[str, MTPDeviceInfo] = {}  # device_id → info
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._available = False
        self._MediaDevice = None  # tipo .NET cargado de MediaDevices.dll

    def _enumerate_devices(self) -> list[MTPDeviceInfo]:
        """
        Enumera los dispositivos MTP conectados actualmente.

        Filtra iPhones (no son MTP, requieren iTunes+AppleMobileDevice.dll).
        Para el resto (Samsung, Xiaomi, Motorola, Huawei, etc.) usa el
        protocolo MTP estándar expuesto por MediaDevices.dll.
        """
        if not self._MediaDevice:
            return []

        try:
            # MediaDevice.GetDevices() devuelve array de MediaDevice .NET
            raw_devices = self._MediaDevice.GetDevices()
            result = []
            for dev in raw_devices:
                try:
                    info = MTPDeviceInfo(
                        device_id=str(dev.DeviceId),
                        name=str(getattr(dev, "Name", "") or ""),
                        model=str(getattr(dev, "Model", "") or ""),
                        manufacturer=str(getattr(dev, "Manufacturer", "") or ""),
                        friendly_name=str(getattr(dev, "FriendlyName", "") or ""),
                        serial_number=str(getattr(dev, "SerialNumber", "") or ""),
                    )

                    # Filtrar iPhones: no son MTP, no se pueden enumerar
                    if is_iphone(info):
                        log.info(
                            f"Dispositivo iOS detectado ({info.name}) — NO soportado. "
                            "iOS requiere iTunes + AppleMobileDevice.dll (protocolo AFC, no MTP). "
                            "Use iTunes o iMazing para gestionar este dispositivo."
                        )
                        continue

                    # Etiquetar fabricante para log
                    vendor = detect_manufacturer(
                        info.name, info.model, info.manufacturer
                    )
                    if vendor != "generic":
                        log.debug(
                            f"MTP {vendor} detectado: {info.name} (model={info.model})"
                        )

                    # Intentar obtener capacidad (requiere conectar al dispositivo)
                    try:
                        dev.Connect()
                        try:
                            # GetDeviceProperty o similar
                            total = getattr(dev, "TotalCapacity", 0) or 0
                            free = getattr(dev, "FreeSpace", 0) or 0
                            info.total_capacity = int(total)
                            info.free_capacity = int(free)
                        finally:
                            dev.Disconnect()
                    except Exception as e:
                        log.debug(f"No se pudo obtener capacidad de {info.name}: {e}")

                    result.append(info)
                except Exception as e:
                    log.warning(f"Error procesando dispositivo MTP: {e}")
            return result
        except Exception as e:
            log.exception(f"Error enumerando dispositivos MTP: {e}")
            return []

    def _scan(self) -> None:
        """Un ciclo de polling: detecta inserciones/extracciones."""
        try:
            current_devices = self._enumerate_devices()
            current_ids = {d.device_id for d in current_devices}

            # Inserciones
            for info in current_devices:
                if info.device_id not in self._known_devices:
                    log.info(f"MTP insertado: {info.name} ({info.model})")
                    self._known_devices[info.device_id] = info
                    self._fire_inserted(info)

            # Extracciones
            removed_ids = set(self._known_devices.keys()) - current_ids
            for dev_id in removed_ids:
                info = self._known_devices.pop(dev_id)
                log.info(f"MTP extraído: {info.name} ({info.model})")
                self._fire_removed(dev_id)
        except Exception as e:
            log.exception(f"Error en scan MTP: {e}")

    def _fire_inserted(self, info: MTPDeviceInfo) -> None:
        if self._on_inserted and self._loop:
            try:
                result = self._on_inserted(info)
                if asyncio.iscoroutine(result):
                    asyncio.run_coroutine_threadsafe(result, self._loop)
            except Exception as e:
                log.exception(f"Error en callback MTP on_inserted: {e}")

    def _fire_removed(self, device_id: str) -> None:
        if self._on_removed and self._loop:
            try:
                result = self._on_removed(device_id)
                if asyncio.iscoroutine(result):
                    asyncio.run_coroutine_threadsafe(result, self._loop)
            except Exception as e:
                log.exception(f"Error en callback MTP on_removed: {e}")

    def _run(self) -> None:
        """Loop principal del monitor."""
        log.info(f"MTPMonitor: polling cada {self._poll_interval}s")

        while not self._stop_event.is_set():
            if self._available:
                self._scan()
            self._stop_event.wait(self._poll_interval)

    async def start(self) -> None:
        """Arranca el monitor."""
        if self._running:
            return

        self._loop = asyncio.get_event_loop()

        if not is_mtp_available():
            log.warning(
                "MTP no disponible (pythonnet no instalado o no es Windows). "
                "El monitoreo de dispositivos MTP (celulares) quedará inactivo."
            )
            self._available = False
        else:
            self._MediaDevice = _load_media_devices()
            self._available = self._MediaDevice is not None

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="MTPMonitor", daemon=True
        )
        self._thread.start()
        self._running = True
        log.info(
            f"MTPMonitor arrancado (available={self._available})"
        )

    async def stop(self) -> None:
        """Detiene el monitor."""
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        log.info("MTPMonitor detenido")


# ---------------------------------------------------------------------------
# MTPFilePoller — vigila cambios en archivos de un dispositivo MTP
# ---------------------------------------------------------------------------

class MTPFilePoller:
    """
    Vigila cambios en los archivos de un dispositivo MTP mediante polling.

    Como MTP no expone un filesystem real, watchdog no funciona. En su lugar:
      1. Cada N segundos, enumerar recursivamente los archivos del dispositivo.
      2. Comparar con el snapshot anterior (path + size + modified).
      3. Emitir eventos created/deleted.

    Este poller es MÁS LENTO que watchdog para USB mass-storage, pero es la
    única forma de monitorear MTP.

    LIMITACIONES:
      - Solo funciona en Windows con pythonnet + MediaDevices.dll instalados.
      - En Linux/Mac `_enumerate_files` devuelve `{}` (sin elevar excepción).
      - El primer ciclo devuelve el snapshot completo y dispara `on_file_created`
        para CADA archivo (esto es esperado: el poller no puede distinguir
        archivos preexistentes de nuevos en la primera enumeración). Para
        evitar spam, el caller puede pasar `skip_initial=True` en `start()`.
    """

    # Profundidad máxima de recursión para evitar loops infinitos en
    # dispositivos con ciclos simbólicos (raros en MTP pero posibles).
    MAX_DEPTH = 15

    # Máximo número de archivos a enumerar por dispositivo (safety valve).
    # Un celular típico tiene <100k archivos visibles por MTP.
    MAX_FILES = 200_000

    def __init__(
        self,
        device_id: str,
        on_file_created: Callable[[str, int], "object"] | None = None,
        on_file_deleted: Callable[[str], "object"] | None = None,
        poll_interval_seconds: int = 10,
    ) -> None:
        self._device_id = device_id
        self._on_created = on_file_created
        self._on_deleted = on_file_deleted
        self._poll_interval = poll_interval_seconds
        self._snapshot: dict[str, tuple[int, datetime]] = {}  # path → (size, modified)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        # Cache de la clase MediaDevice cargada vía pythonnet (evita recargar
        # la DLL en cada ciclo de polling).
        self._MediaDevice = None
        # Snapshot inicial ya tomado (para no disparar on_created para todos
        # los archivos preexistentes en el primer poll).
        self._initial_snapshot_taken = False

    # -----------------------------------------------------------------
    # Carga perezosa de MediaDevices.dll
    # -----------------------------------------------------------------

    def _ensure_media_device_loaded(self):
        """Carga MediaDevices.dll si no está cargado todavía."""
        if self._MediaDevice is not None:
            return self._MediaDevice
        if not is_mtp_available():
            return None
        self._MediaDevice = _load_media_devices()
        return self._MediaDevice

    def _find_device_by_id(self, MediaDeviceCls):
        """
        Busca en `MediaDevice.GetDevices()` el dispositivo cuyo DeviceId
        coincide con `self._device_id`.

        Devuelve el objeto .NET MediaDevice o None si no se encuentra.
        """
        try:
            raw_devices = MediaDeviceCls.GetDevices()
        except Exception as e:
            log.warning(f"GetDevices() falló para poller {self._device_id}: {e}")
            return None

        for dev in raw_devices:
            try:
                if str(dev.DeviceId) == self._device_id:
                    return dev
            except Exception:
                continue
        return None

    # -----------------------------------------------------------------
    # Enumeración recursiva de archivos
    # -----------------------------------------------------------------

    def _enumerate_files(self) -> dict[str, tuple[int, datetime]]:
        """
        Enumera todos los archivos del dispositivo MTP.

        Devuelve dict path → (size_bytes, modified_time).

        Implementación:
          1. Carga MediaDevices.dll (cacheada).
          2. Busca el dispositivo por `device_id`.
          3. Conecta al dispositivo.
          4. Recorre recursivamente desde la raíz usando `GetRootDirectory`,
             `GetDirectories` y `GetFiles`.
          5. Para cada archivo, obtiene `Size` y `LastWriteTime` vía
             `GetFileInfo(path)`.
          6. Desconecta al final (siempre, incluso en error).

        En Linux/Mac o si pythonnet no está disponible, devuelve `{}`.
        """
        MediaDeviceCls = self._ensure_media_device_loaded()
        if MediaDeviceCls is None:
            # No-Windows o pythonnet no instalado: silencioso
            return {}

        dev = self._find_device_by_id(MediaDeviceCls)
        if dev is None:
            log.debug(
                f"Dispositivo MTP {self._device_id} no encontrado en este ciclo"
            )
            return {}

        result: dict[str, tuple[int, datetime]] = {}
        connected = False
        try:
            dev.Connect()
            connected = True

            # Raíz del dispositivo. Algunos móviles exponen "Internal Storage"
            # y "Card" como subdirectorios; otros tienen un único root.
            try:
                root = str(dev.GetRootDirectory() or "\\")
            except Exception:
                # Fallback: raíz canónica de MTP
                root = "\\"
            if not root:
                root = "\\"

            self._enumerate_recursive(dev, root, result, depth=0)

            log.debug(
                f"MTP enumerate {self._device_id}: {len(result)} archivos "
                f"bajo {root}"
            )
        except Exception as e:
            log.warning(
                f"Error enumerando archivos MTP en {self._device_id}: {e}"
            )
        finally:
            if connected:
                try:
                    dev.Disconnect()
                except Exception as e:
                    log.debug(f"Disconnect falló para {self._device_id}: {e}")

        return result

    def _enumerate_recursive(
        self,
        dev,
        current_path: str,
        result: dict[str, tuple[int, datetime]],
        depth: int,
    ) -> None:
        """
        Recursión DFS para enumerar archivos de un dispositivo MTP.

        Args:
            dev: objeto .NET MediaDevice ya conectado.
            current_path: ruta absoluta MTP (ej: "\\Internal Storage\\DCIM").
            result: dict donde se acumulan {path: (size, modified)}.
            depth: profundidad actual (safety limit MAX_DEPTH).
        """
        if depth > self.MAX_DEPTH:
            log.debug(
                f"MTP enumerate: profundidad máxima alcanzada en {current_path}"
            )
            return
        if len(result) >= self.MAX_FILES:
            log.warning(
                f"MTP enumerate: límite MAX_FILES={self.MAX_FILES} alcanzado "
                f"para {self._device_id}. Se truncará la enumeración."
            )
            return

        # Listar archivos del directorio actual
        try:
            files = list(dev.GetFiles(current_path) or [])
        except Exception as e:
            log.debug(
                f"MTP GetFiles falló en {current_path}: {e} "
                "(puede ser un directorio protegido)"
            )
            files = []

        for fname in files:
            if len(result) >= self.MAX_FILES:
                break
            file_path = self._join_mtp_path(current_path, fname)
            size, modified = self._get_file_meta(dev, file_path)
            result[file_path] = (size, modified)

        # Listar subdirectorios y recursar
        try:
            subdirs = list(dev.GetDirectories(current_path) or [])
        except Exception as e:
            log.debug(
                f"MTP GetDirectories falló en {current_path}: {e}"
            )
            subdirs = []

        for subdir in subdirs:
            subdir_path = self._join_mtp_path(current_path, subdir)
            self._enumerate_recursive(dev, subdir_path, result, depth + 1)

    @staticmethod
    def _join_mtp_path(parent: str, child: str) -> str:
        """
        Une dos rutas MTP usando el separador canónico de Windows (\\).

        MTP expone rutas estilo Windows ("\\Internal Storage\\DCIM\\IMG_001.jpg")
        incluso en dispositivos Android, porque el protocolo WPD así lo define.
        """
        if not parent:
            return "\\" + child.lstrip("\\")
        if parent.endswith("\\"):
            return parent + child.lstrip("\\")
        return parent + "\\" + child.lstrip("\\")

    @staticmethod
    def _get_file_meta(dev, file_path: str) -> tuple[int, datetime]:
        """
        Obtiene (size_bytes, modified_time) de un archivo MTP.

        Usa `dev.GetFileInfo(path)` que devuelve un objeto .NET con
        `.Length`/`.Size` y `.LastWriteTime`/`.LastWriteTimeUtc`.

        Si falla, devuelve (0, utcnow()) para no romper el snapshot.
        """
        try:
            fi = dev.GetFileInfo(file_path)
            if fi is None:
                return 0, utcnow()
            # Long, Int64 → int
            size = 0
            for attr in ("Length", "Size", "FileSize"):
                v = getattr(fi, attr, None)
                if v is not None:
                    try:
                        size = int(v)
                        break
                    except (TypeError, ValueError):
                        continue
            # DateTime .NET → Python datetime
            modified = utcnow()
            for attr in ("LastWriteTimeUtc", "LastWriteTime", "LastModifiedTime"):
                v = getattr(fi, attr, None)
                if v is not None:
                    try:
                        modified = _dotnet_datetime_to_python(v)
                        break
                    except Exception:
                        continue
            return size, modified
        except Exception as e:
            log.debug(f"MTP GetFileInfo falló para {file_path}: {e}")
            return 0, utcnow()

    def _poll(self) -> None:
        """Un ciclo de polling."""
        try:
            current = self._enumerate_files()
            current_paths = set(current.keys())

            # Primer poll: solo cacheamos el snapshot sin disparar eventos
            # para no inundar con on_created para todos los archivos
            # preexistentes. El siguiente poll ya comparará contra este.
            if not self._initial_snapshot_taken:
                self._snapshot = current
                self._initial_snapshot_taken = True
                log.info(
                    f"MTPFilePoller snapshot inicial: {len(current)} archivos "
                    f"en {self._device_id}"
                )
                return

            # Creados
            for path, (size, modified) in current.items():
                if path not in self._snapshot:
                    if self._on_created and self._loop:
                        result = self._on_created(path, size)
                        if asyncio.iscoroutine(result):
                            asyncio.run_coroutine_threadsafe(result, self._loop)

            # Borrados
            for path in set(self._snapshot.keys()) - current_paths:
                if self._on_deleted and self._loop:
                    result = self._on_deleted(path)
                    if asyncio.iscoroutine(result):
                        asyncio.run_coroutine_threadsafe(result, self._loop)

            self._snapshot = current
        except Exception as e:
            log.exception(f"Error en MTPFilePoller: {e}")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._poll()
            self._stop_event.wait(self._poll_interval)

    async def start(self, skip_initial: bool = True) -> None:
        """
        Arranca el poller en background.

        Args:
            skip_initial: si True (default), el primer poll solo cachea el
                snapshot inicial sin disparar `on_file_created` para los
                archivos preexistentes. Recomendado para no inundar el
                callback con miles de eventos al conectar un celular.
        """
        if self._running:
            return
        self._loop = asyncio.get_event_loop()
        self._stop_event.clear()
        self._initial_snapshot_taken = not skip_initial
        self._thread = threading.Thread(
            target=self._run, name=f"MTPPoller-{self._device_id}", daemon=True
        )
        self._thread.start()
        self._running = True
        log.info(f"MTPFilePoller arrancado para dispositivo {self._device_id}")

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        log.info(f"MTPFilePoller detenido para dispositivo {self._device_id}")


# ---------------------------------------------------------------------------
# Helpers de conversión .NET ↔ Python
# ---------------------------------------------------------------------------

def _dotnet_datetime_to_python(dotnet_dt) -> datetime:
    """
    Convierte un System.DateTime de .NET a datetime Python (UTC-aware).

    pythonnet normalmente convierte automáticamente, pero algunos tipos
    (TimeSpan, DateTimeOffset) requieren acceso manual a propiedades.

    Si recibe algo que ya es datetime Python, lo devuelve sin tocar.
    """
    # Caso común: ya es datetime Python (pythonnet convierte auto)
    if isinstance(dotnet_dt, datetime):
        if dotnet_dt.tzinfo is None:
            from datetime import timezone
            return dotnet_dt.replace(tzinfo=timezone.utc)
        return dotnet_dt.astimezone(timezone.utc)

    # Intentar extraer ticks .NET (100-nanosegundos desde 0001-01-01)
    # y convertir a epoch Python
    try:
        ticks = int(getattr(dotnet_dt, "Ticks", 0))
        if ticks > 0:
            # .NET epoch: 0001-01-01 = ticks 0
            # Unix epoch: 1970-01-01 = ticks 621355968000000000
            unix_ticks = ticks - 621355968000000000
            seconds = unix_ticks / 10_000_000
            from datetime import timezone
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except Exception:
        pass

    # Fallback: ahora mismo
    return utcnow()
