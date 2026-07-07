"""
Plugin: Alerta de Sonido — LBAMonitor v4.2
==========================================
Reproduce un sonido del sistema Windows al ocurrir eventos críticos.
Sin dependencias externas (usa winsound de la stdlib de Windows).

Configuración (en config.toml):
  [plugins.sound_alert]
  enabled = true
  sound_on_insert = true   # Sonido al insertar USB
  sound_on_remove = true   # Sonido al extraer USB
  sound_on_payment = true  # Sonido al registrar cobro
"""
import os

def _play(sound_type: str = "SystemNotification") -> None:
    """Reproduce un sonido del sistema. No falla si winsound no está disponible."""
    if os.name != "nt":
        return
    try:
        import winsound
        sounds = {
            "SystemNotification": winsound.MB_ICONASTERISK,
            "SystemExclamation": winsound.MB_ICONEXCLAMATION,
            "SystemHand": winsound.MB_ICONHAND,
        }
        winsound.MessageBeep(sounds.get(sound_type, winsound.MB_ICONASTERISK))
    except Exception:
        pass


def on_usb_inserted(drive_letter: str, device_info: dict) -> None:
    """Beep amigable al insertar USB."""
    _play("SystemNotification")


def on_usb_removed(drive_letter: str) -> None:
    """Beep de aviso al extraer USB."""
    _play("SystemExclamation")


def on_payment_registered(inserted_id: int, amount: float) -> None:
    """Beep de éxito al registrar cobro."""
    _play("SystemNotification")


def on_session_started(session_id: int) -> None:
    """Beep al iniciar sesión del servicio."""
    _play("SystemNotification")
