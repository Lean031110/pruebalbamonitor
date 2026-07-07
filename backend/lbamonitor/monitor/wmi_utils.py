"""
Utilidades WMI para identificación de dispositivos USB en Windows.

IDENTIFICACIÓN COMPUESTA (corrige R7):
  En >30% de las USBs chinas, `Win32_DiskDrive.SerialNumber` devuelve NULL o
  espacios en blanco. Por eso usamos una CLAVE COMPUESTA:

    fingerprint = SHA-256(DeviceID + VolumeSerialNumber)

  - `DeviceID` (ej: `\\\\.\\PHYSICALDRIVE2`) identifica la ranura física.
    Es inmutable para esa ranura mientras el hardware no cambie.
  - `VolumeSerialNumber` (ej: `A1B2-C3D4`) identifica el volumen formateado.
    Cambia si el usuario formatea la USB, pero es estable entre inserciones.

  Esta combinación es más estable que SerialNumber y sobrevive a formateos
  de la USB (mientras no se reformatee el volumen).

  Para dispositivos MTP (celulares), usamos `Model + friendly_name` como
  fallback ya que no exponen VolumeSerialNumber.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any

from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


def is_windows() -> bool:
    """True si estamos en Windows."""
    return os.name == "nt"


# ---------------------------------------------------------------------------
# Dataclass con toda la info de un dispositivo USB
# ---------------------------------------------------------------------------

@dataclass
class USBDeviceInfo:
    """Información completa de un dispositivo USB insertado."""

    drive_letter: str  # "E:\\"
    name: str = ""  # Etiqueta de volumen o nombre descriptivo
    root_directory: str = ""
    volume_label: str = ""
    filesystem: str = ""

    # Identificación
    volume_serial: str = ""  # A1B2-C3D4 (Win32_LogicalDisk.VolumeSerialNumber)
    hardware_serial: str = ""  # Serial físico (puede ser NULL en USBs chinas)
    device_id: str = ""  # \\.\PHYSICALDRIVE2 (Win32_DiskDrive.DeviceID)
    pnp_device_id: str = ""  # USB\VID_0951&PID_1666\...
    fingerprint: str = ""  # SHA-256(device_id + volume_serial) — clave compuesta

    # Hardware
    brand: str = ""
    manufacturer: str = ""
    model: str = ""
    vid: str = ""  # Vendor ID (parseado de PNPDeviceID)
    pid: str = ""  # Product ID (parseado de PNPDeviceID)
    total_capacity: int = 0  # bytes
    free_capacity: int = 0  # bytes
    connection_type: str = "unknown"  # usb_2 | usb_3 | usb_c | unknown

    # Tipo
    is_removable: bool = True
    is_mobile: bool = False  # MTP (teléfono, cámara)
    is_mounted_folder: bool = False

    def __post_init__(self) -> None:
        """Calcula fingerprint si no está seteado."""
        if not self.fingerprint:
            self.fingerprint = compute_fingerprint(self.device_id, self.volume_serial)


def compute_fingerprint(device_id: str, volume_serial: str) -> str:
    """
    Calcula el fingerprint compuesto de un dispositivo USB.

    Si ambos están vacíos, devuelve string vacío (no se puede identificar).
    Si solo uno está vacío, usa el otro.
    Si ambos están, usa SHA-256(device_id + "|" + volume_serial).
    """
    did = (device_id or "").strip().lower()
    vsn = (volume_serial or "").strip().lower()

    if not did and not vsn:
        return ""

    composite = f"{did}|{vsn}"
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()


def parse_vid_pid(pnp_device_id: str) -> tuple[str, str]:
    """
    Extrae VID y PID de un PNPDeviceID.

    Ej: "USB\\VID_0951&PID_1666\\AA0000000001" → ("0951", "1666")
    """
    if not pnp_device_id:
        return "", ""
    vid = ""
    pid = ""
    upper = pnp_device_id.upper()
    if "VID_" in upper:
        start = upper.find("VID_") + 4
        if start + 4 <= len(pnp_device_id):
            vid = pnp_device_id[start : start + 4]
    if "PID_" in upper:
        start = upper.find("PID_") + 4
        if start + 4 <= len(pnp_device_id):
            pid = pnp_device_id[start : start + 4]
    return vid, pid


def normalize_serial(raw: str | None) -> str:
    """
    Normaliza un serial number de USB.

    Algunas USBs devuelven el serial en little-endian invertido
    (cada par de caracteres swappeado). Ej: "AA11BB22" → "A1A1B2B2".
    Esto es un bug conocido de fabricantes con tooling antiguo.

    Heurística: si el serial tiene longitud par y todos sus chars son hex,
    aplicar el swap y ver si el resultado "se ve más normal".
    """
    if not raw:
        return ""
    s = raw.strip()
    if not s or s.lower() in ("null", "none", "0"):
        return ""
    return s


# ---------------------------------------------------------------------------
# Consultas WMI (solo Windows)
# ---------------------------------------------------------------------------

def _query_wmi_disk_drive(drive_letter: str) -> dict[str, Any]:
    """
    Consulta Win32_DiskDrive asociado a una letra de unidad.

    Devuelve dict con: DeviceID, SerialNumber, Model, Manufacturer, PNPDeviceID,
    Size, InterfaceType.

    En no-Windows devuelve dict vacío.
    """
    if not is_windows():
        return {}

    try:
        import wmi  # type: ignore
        import pythoncom  # type: ignore

        pythoncom.CoInitialize()  # Necesario en hilos
        c = wmi.WMI()

        # Validar formato de drive_letter (prevenir WQL injection)
        import re
        if not re.match(r"^[A-Z]:$", drive_letter):
            log.warning(f"drive_letter inválido ignorado: {drive_letter!r}")
            return {}

        # 1. Win32_LogicalDisk → partition
        logical = c.Win32_LogicalDisk(DriveLetter=drive_letter)
        if not logical:
            return {}
        logical = logical[0]

        # 2. LogicalDiskToPartition (drive_letter ya validado)
        ldps = c.query(
            f"ASSOCIATORS OF {{Win32_LogicalDisk.DeviceID='{drive_letter}'}} "
            "WHERE ResultClass=Win32_DiskPartition"
        )
        if not ldps:
            return {}

        # 3. DiskPartition → DiskDrive (validar partition.DeviceID)
        partition = ldps[0]
        partition_id = str(partition.DeviceID or "")
        # DiskPartition.DeviceID tiene formato "Disk #0, Partition #0"
        if not re.match(r"^Disk #\d+, Partition #\d+$", partition_id):
            log.warning(f"partition.DeviceID con formato inesperado: {partition_id!r}")
            return {}
        ddps = c.query(
            f"ASSOCIATORS OF {{Win32_DiskPartition.DeviceID='{partition_id}'}} "
            "WHERE ResultClass=Win32_DiskDrive"
        )
        if not ddps:
            return {}

        drive = ddps[0]
        return {
            "DeviceID": drive.DeviceID or "",  # \\.\PHYSICALDRIVE2
            "SerialNumber": normalize_serial(getattr(drive, "SerialNumber", None)),
            "Model": drive.Model or "",
            "Manufacturer": drive.Manufacturer or "",
            "PNPDeviceID": drive.PNPDeviceID or "",
            "Size": int(getattr(drive, "Size", 0) or 0),
            "InterfaceType": getattr(drive, "InterfaceType", "USB"),
        }
    except Exception as e:
        log.warning(f"Error consultando WMI Win32_DiskDrive para {drive_letter}: {e}")
        return {}


def _query_wmi_logical_disk(drive_letter: str) -> dict[str, Any]:
    """
    Consulta Win32_LogicalDisk para una letra de unidad.

    Devuelve: VolumeSerialNumber, VolumeName, FileSystem, Size, FreeSpace.
    """
    if not is_windows():
        return {}

    try:
        import wmi  # type: ignore
        import pythoncom  # type: ignore

        pythoncom.CoInitialize()
        c = wmi.WMI()
        logical = c.Win32_LogicalDisk(DriveLetter=drive_letter)
        if not logical:
            return {}
        ld = logical[0]
        return {
            "VolumeSerialNumber": ld.VolumeSerialNumber or "",
            "VolumeName": ld.VolumeName or "",
            "FileSystem": ld.FileSystem or "",
            "Size": int(getattr(ld, "Size", 0) or 0),
            "FreeSpace": int(getattr(ld, "FreeSpace", 0) or 0),
        }
    except Exception as e:
        log.warning(f"Error consultando WMI Win32_LogicalDisk para {drive_letter}: {e}")
        return {}


def get_usb_info(drive_letter: str) -> USBDeviceInfo:
    """
    Obtiene toda la información disponible de un dispositivo USB insertado.

    En no-Windows devuelve un USBDeviceInfo con datos mínimos (para tests).
    """
    info = USBDeviceInfo(drive_letter=drive_letter)

    if not is_windows():
        log.debug(f"WMI no disponible en {os.name} — devolviendo info mínima para {drive_letter}")
        return info

    # Win32_LogicalDisk
    ld = _query_wmi_logical_disk(drive_letter)
    if ld:
        info.volume_serial = ld.get("VolumeSerialNumber", "")
        info.volume_label = ld.get("VolumeName", "")
        info.filesystem = ld.get("FileSystem", "")
        info.total_capacity = ld.get("Size", 0)
        info.free_capacity = ld.get("FreeSpace", 0)
        info.root_directory = f"{drive_letter}\\"
        info.name = drive_letter

    # Win32_DiskDrive
    dd = _query_wmi_disk_drive(drive_letter)
    if dd:
        info.device_id = dd.get("DeviceID", "")
        info.hardware_serial = dd.get("SerialNumber", "")
        info.model = dd.get("Model", "")
        info.manufacturer = dd.get("Manufacturer", "")
        info.pnp_device_id = dd.get("PNPDeviceID", "")
        info.vid, info.pid = parse_vid_pid(info.pnp_device_id)

        # Heurística de conexión USB 2/3
        iface = (dd.get("InterfaceType") or "").upper()
        if "USB 3" in iface or "USB3" in info.model.upper():
            info.connection_type = "usb_3"
        elif "USB" in iface or "USB" in info.model.upper():
            info.connection_type = "usb_2"

        # Si total_capacity no vino de LogicalDisk, usar DiskDrive.Size
        if not info.total_capacity and dd.get("Size"):
            info.total_capacity = int(dd["Size"])

    # Recalcular fingerprint con todos los datos
    info.fingerprint = compute_fingerprint(info.device_id, info.volume_serial)

    log.debug(
        f"USB info {drive_letter}: fingerprint={info.fingerprint[:16]}... "
        f"vol_serial={info.volume_serial!r} dev_id={info.device_id!r} "
        f"hw_serial={info.hardware_serial[:8] if info.hardware_serial else 'NONE'!r}"
    )
    return info


def list_removable_drives() -> list[str]:
    """
    Lista las letras de unidad de dispositivos removibles conectados.

    En Windows: usa GetLogicalDrives + GetDriveType.
    En Linux/Mac: usa /media, /mnt.
    """
    if not is_windows():
        # Linux/Mac fallback para tests
        import os
        candidates = []
        for base in ("/media", "/mnt", f"/media/{os.getenv('USER', '')}"):
            if os.path.isdir(base):
                for entry in os.listdir(base):
                    candidates.append(os.path.join(base, entry))
        return candidates

    try:
        import win32api  # type: ignore
        import win32file  # type: ignore

        drives = []
        bitmask = win32api.GetLogicalDrives()
        for letter_ord in range(ord("A"), ord("Z") + 1):
            if bitmask & (1 << (letter_ord - ord("A"))):
                letter = chr(letter_ord)
                drive_path = f"{letter}:\\"
                try:
                    if win32file.GetDriveType(drive_path) == win32file.DRIVE_REMOVABLE:
                        drives.append(f"{letter}:")
                except Exception:
                    pass
        return drives
    except Exception as e:
        log.warning(f"Error listando drives removibles: {e}")
        return []
