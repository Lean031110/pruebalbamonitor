"""Formatters de presentación: moneda, bytes, duración, fechas, números."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


def format_currency(
    value: float | int | None,
    symbol: str = "₱",
    decimals: int = 2,
) -> str:
    """Formatea un valor como moneda con símbolo."""
    if value is None:
        value = 0
    return f"{value:,.{decimals}f}{symbol}"


def format_bytes(num: int | float | None) -> str:
    """Formatea bytes en B/KB/MB/GB/TB/PB."""
    if num is None or num < 0:
        return "0 B"
    if num == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while num >= 1024 and i < len(units) - 1:
        num /= 1024.0
        i += 1
    return f"{num:.2f} {units[i]}"


def format_duration(seconds: int | float | None) -> str:
    """Formatea segundos como `Xh Ym Zs`."""
    if seconds is None or seconds < 0:
        return "0s"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


def format_datetime(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Formatea un datetime."""
    if dt is None:
        return ""
    return dt.strftime(fmt)


def format_date(dt: datetime | None, fmt: str = "%Y-%m-%d") -> str:
    """Formatea un datetime como fecha."""
    if dt is None:
        return ""
    return dt.strftime(fmt)


def format_time(dt: datetime | None, fmt: str = "%H:%M:%S") -> str:
    """Formatea un datetime como hora."""
    if dt is None:
        return ""
    return dt.strftime(fmt)


def format_number(value: int | float | None, decimals: int = 0) -> str:
    """Formatea un número con separador de miles."""
    if value is None:
        return "0"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.{decimals}f}"


def parse_float(value: str | None, default: float = 0.0) -> float:
    """
    Parsea un float aceptando coma o punto decimal y separadores de miles.

    Ej: "1.234,56" -> 1234.56 ; "1,234.56" -> 1234.56 ; "1234,56" -> 1234.56
    """
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default
    # Si tiene ambos, el último es el decimal
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # Formato europeo: 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:
            # Formato anglo: 1,234.56
            s = s.replace(",", "")
    elif "," in s:
        # Solo coma: asumir decimal
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return default
