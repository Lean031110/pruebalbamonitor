"""
Plugin: Estadísticas de Sesión — LBAMonitor v4.2
=================================================
Guarda un resumen de la sesión en JSON al cerrar.
Útil para auditoría y análisis posterior.

Archivo: C:/ProgramData/LBAMonitor/exports/stats/sesion_YYYY-MM-DD_HH-MM.json
"""
import json
import os
from datetime import datetime
from pathlib import Path

_session_start: dict = {}


def on_session_started(session_id: int) -> None:
    _session_start[session_id] = datetime.now().isoformat()


def on_session_ended(session_id: int) -> None:
    _save_session_summary(session_id)


def on_payment_registered(inserted_id: int, amount: float) -> None:
    # Acumular pagos para el resumen (en memoria, best-effort)
    pass


def _save_session_summary(session_id: int) -> None:
    try:
        exports_dir = Path(
            os.environ.get("LBAMONITOR_STATS_DIR", "C:/ProgramData/LBAMonitor/exports/stats")
        )
        exports_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        filename = exports_dir / f"sesion_{now.strftime('%Y-%m-%d_%H-%M')}.json"

        summary = {
            "session_id": session_id,
            "started_at": _session_start.get(session_id),
            "ended_at": now.isoformat(),
            "generated_by": "LBAMonitor v4.2 — session_stats_plugin",
        }

        # Intentar obtener datos de la BD
        try:
            summary.update(_get_session_data_from_db(session_id))
        except Exception:
            pass

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

        print(f"[session_stats] Resumen guardado: {filename}")
    except Exception as e:
        print(f"[session_stats] Error: {e}")

    # Limpiar estado en memoria
    _session_start.pop(session_id, None)


def _get_session_data_from_db(session_id: int) -> dict:
    import sqlite3, os as os_mod
    db_path = os_mod.environ.get(
        "LBAMONITOR_DB", "C:/ProgramData/LBAMonitor/data/lbamonitor.db"
    )
    if not os_mod.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    try:
        # Cobros del día
        cur = conn.execute("""
            SELECT
                COUNT(*) as total_drives,
                COALESCE(SUM(payment), 0) as total_revenue,
                COALESCE(AVG(payment), 0) as avg_payment
            FROM inserted_drives
            WHERE date(insertion_date_time) = date('now')
        """)
        row = cur.fetchone()
        if row:
            return {
                "total_drives_today": row[0],
                "total_revenue_today": row[1],
                "avg_payment_today": round(row[2], 2),
            }
    finally:
        conn.close()
    return {}
