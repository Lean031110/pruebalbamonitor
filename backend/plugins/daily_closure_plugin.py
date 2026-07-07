"""
Plugin: Daily Closure.

Al cerrar el día (medianoche o primer USB del día siguiente),
genera un PDF con el resumen del día y lo guarda en exports/.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path


_last_closure_date: str | None = None


def on_session_started(**kwargs) -> None:
    """
    Se dispara al arrancar el servicio. Si cambió el día desde el último closure,
    genera el PDF del día anterior.
    """
    global _last_closure_date
    today = datetime.now(timezone.utc).date().isoformat()

    if _last_closure_date is None:
        _last_closure_date = today
        return

    if _last_closure_date != today:
        # Generar closure del día anterior
        try:
            _generate_daily_closure(_last_closure_date)
            _last_closure_date = today
        except Exception as e:
            print(f"[daily_closure] Error: {e}")


def on_backup_created(file_path: str, **kwargs) -> None:
    """También generar closure cuando se hace backup nocturno."""
    today = datetime.now(timezone.utc).date().isoformat()
    if _last_closure_date != today:
        try:
            _generate_daily_closure(_last_closure_date or today)
            _last_closure_date = today
        except Exception as e:
            print(f"[daily_closure] Error en backup hook: {e}")


def _generate_daily_closure(date_str: str) -> None:
    """Genera PDF de cierre del día."""
    import os
    import sys

    # Path al backend
    backend_path = Path(__file__).resolve().parent.parent
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    try:
        from lbamonitor.core.config import get_settings
        from lbamonitor.core.db import get_session_factory
        from lbamonitor.core.services.pdf_engine import PdfEngine

        s = get_settings()
        factory = get_session_factory()

        # Obtener stats del día
        async def _get_stats():
            from sqlalchemy import select, func
            from lbamonitor.core.models import Billing, InsertedDrive, Copy

            async with factory() as session:
                # Cobros del día
                start = datetime.fromisoformat(date_str + "T00:00:00+00:00")
                end = start + timedelta(days=1)

                billings = await session.execute(
                    select(Billing).where(Billing.created_at >= start, Billing.created_at < end)
                )
                billing_list = billings.scalars().all()

                total_revenue = sum(b.amount for b in billing_list)
                transactions = len(billing_list)

                usb_count = await session.scalar(
                    select(func.count(InsertedDrive.id)).where(
                        InsertedDrive.insertion_date_time >= start,
                        InsertedDrive.insertion_date_time < end,
                    )
                )

                return {
                    "date": date_str,
                    "total_revenue": total_revenue,
                    "transactions": transactions,
                    "usb_count": usb_count or 0,
                }

        stats = asyncio.run(_get_stats())

        # Generar PDF
        exports_dir = Path(s.paths.exports)
        exports_dir.mkdir(parents=True, exist_ok=True)
        output = exports_dir / f"closure_{date_str}.pdf"

        business_info = {
            "name": s.business.name,
            "address": s.business.address,
            "phone": s.business.phone,
        }

        PdfEngine.generate_daily_report_pdf(stats, business_info, output)
        print(f"[daily_closure] PDF generado: {output}")

    except Exception as e:
        print(f"[daily_closure] Error generando PDF: {e}")


PLUGIN_NAME = "daily_closure"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Genera PDF de cierre diario automático"
