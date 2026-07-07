"""
Plugin: Telegram Notification.

Envía notificaciones a un chat de Telegram cuando ocurren eventos importantes.
Útil para monitoreo remoto de la copistería.

Configuración (env vars):
- LBAMONITOR_TELEGRAM_BOT_TOKEN: token del bot
- LBAMONITOR_TELEGRAM_CHAT_ID: ID del chat destino
"""
from __future__ import annotations

import json
import os
import urllib.request


def _send_telegram(text: str) -> None:
    """Envía mensaje a Telegram."""
    token = os.environ.get("LBAMONITOR_TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("LBAMONITOR_TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return  # No configurado

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        print(f"[telegram_notify] Error: {e}")


def on_usb_inserted(drive_letter: str = "", volume_label: str = "", **kwargs) -> None:
    _send_telegram(f"🔌 <b>USB insertado</b>: {drive_letter} ({volume_label})")


def on_usb_removed(drive_letter: str = "", **kwargs) -> None:
    _send_telegram(f"📤 <b>USB extraído</b>: {drive_letter}")


def on_payment_registered(amount: float = 0, device_id: int = 0, **kwargs) -> None:
    _send_telegram(f"💰 <b>Cobro registrado</b>: ${amount:.2f} (USB #{device_id})")


def on_session_started(**kwargs) -> None:
    _send_telegram("✅ <b>LBAMonitor iniciado</b>")


def on_session_ended(**kwargs) -> None:
    _send_telegram("🛑 <b>LBAMonitor detenido</b>")


def on_license_activated(tier: str = "", **kwargs) -> None:
    _send_telegram(f"🔐 <b>Licencia activada</b>: tier={tier}")


PLUGIN_NAME = "telegram_notify"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Notificaciones por Telegram (requiere bot token)"
