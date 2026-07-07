"""
Plugin: USB Insertion Alert Popup.

Muestra un popup visual cuando se inserta un USB (además del WS).
Útil para kioscos donde el operador no tiene la app desktop abierta.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone


def on_usb_inserted(drive_letter: str, volume_label: str = "", **kwargs) -> None:
    """Muestra alerta visual al insertar USB."""
    try:
        # En Windows: usar ctypes + MessageBox (sin dependencias)
        import os
        if os.name == "nt":
            import ctypes
            msg = f"USB detectado: {drive_letter}\\"
            if volume_label:
                msg += f"\nEtiqueta: {volume_label}"
            msg += "\n\nLBAMonitor está monitoreando las copias."
            # MB_ICONINFORMATION | MB_OK | MB_TOPMOST = 0x40 | 0x00 | 0x40000
            ctypes.windll.user32.MessageBoxW(0, msg, "LBAMonitor - USB Insertado", 0x40400)
        else:
            # Linux/Mac: log
            print(f"[USB Alert] Insertado: {drive_letter} ({volume_label})")
    except Exception as e:
        print(f"[usb_alert_popup] Error: {e}")


def on_usb_removed(drive_letter: str, **kwargs) -> None:
    """Loggeo al extraer USB."""
    print(f"[USB Alert] Extraído: {drive_letter}")


# Metadata del plugin
PLUGIN_NAME = "usb_alert_popup"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Muestra popup visual al insertar USB (Windows)"
