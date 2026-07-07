"""
Plugin: Registro de Cobros en TXT — LBAMonitor v4.2
====================================================
Guarda cada cobro en un archivo de texto plano diario.
Útil como respaldo y para impresoras de tickets básicas.

Archivo: C:/ProgramData/LBAMonitor/exports/recibos/recibos_YYYY-MM-DD.txt
"""
import os
from datetime import datetime
from pathlib import Path


def on_payment_registered(inserted_id: int, amount: float) -> None:
    """Registra el cobro en el archivo diario de recibos."""
    _write_receipt(inserted_id, amount)


def _write_receipt(inserted_id: int, amount: float) -> None:
    try:
        exports_dir = Path(
            os.environ.get("LBAMONITOR_EXPORTS", "C:/ProgramData/LBAMonitor/exports/recibos")
        )
        exports_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        filename = exports_dir / f"recibos_{today}.txt"
        now_str = datetime.now().strftime("%H:%M:%S")

        # Intentar obtener info adicional de la BD
        extra = ""
        try:
            extra = _get_drive_info(inserted_id)
        except Exception:
            pass

        line = (
            f"[{now_str}] ID={inserted_id:05d} | "
            f"COBRO={amount:.2f} CUP {extra}\n"
        )

        with open(filename, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"[receipt_log] Error: {e}")


def _get_drive_info(inserted_id: int) -> str:
    import sqlite3, os as os_mod
    db_path = os_mod.environ.get(
        "LBAMONITOR_DB", "C:/ProgramData/LBAMonitor/data/lbamonitor.db"
    )
    if not os_mod.path.exists(db_path):
        return ""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute(
            "SELECT name, volume_label, model FROM inserted_drives WHERE id=?",
            (inserted_id,)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return f"| USB={row[0]} ETIQ={row[1] or '—'} MODELO={row[2] or '—'}"
    except Exception:
        pass
    return ""


def on_session_ended(session_id: int) -> None:
    """Escribe separador de sesión en el log de recibos."""
    try:
        exports_dir = Path(
            os.environ.get("LBAMONITOR_EXPORTS", "C:/ProgramData/LBAMonitor/exports/recibos")
        )
        exports_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        filename = exports_dir / f"recibos_{today}.txt"
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{'='*60}\n")
            f.write(f"CIERRE DE SESIÓN: {datetime.now().strftime('%H:%M:%S')} — Sesión #{session_id}\n")
            f.write(f"{'='*60}\n\n")
    except Exception:
        pass
