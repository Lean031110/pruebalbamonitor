"""Plugin de ejemplo para LBAMonitor v4.0.0."""
from lbamonitor.utils.logging_setup import get_logger
log = get_logger("plugin.example")

def on_usb_inserted(drive_letter: str, device_info: dict) -> None:
    log.info(f"[PLUGIN] USB insertada: {drive_letter} — {device_info.get('name', '?')}")

def on_usb_removed(drive_letter: str) -> None:
    log.info(f"[PLUGIN] USB extraída: {drive_letter}")

def on_payment_registered(inserted_id: int, amount: float) -> None:
    log.info(f"[PLUGIN] Pago registrado: drive #{inserted_id} = {amount} CUP")

def on_backup_created(file_path: str, size: int) -> None:
    log.info(f"[PLUGIN] Backup creado: {file_path} ({size} bytes)")
