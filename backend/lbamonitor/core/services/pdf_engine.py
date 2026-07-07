"""
Motor de generación de PDFs con reportlab.

Tres tipos de PDF:
  1. Factura de cobro (invoice_pdf): para entregar al cliente.
  2. Servicio (service_pdf): explicativo de tarifas, membresías, reglas.
     Se auto-copia al USB la primera vez que se inserta.
  3. Reporte diario (daily_report_pdf): estilo Mirón, con KPIs del día.

Todos los métodos son estáticos, no bloquean el event loop si se
llaman dentro de `asyncio.to_thread()` (los callers son responsables
de hacer el wrap).

Convención de tipos:
  - `billing`, `business_info`, `stats` son dicts o cualquier objeto
    con `__getitem__`/atributos. Se normalizan vía `_get()`.
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from lbamonitor.core.config import get_settings
from lbamonitor.utils.formatters import format_bytes, format_currency
from lbamonitor.utils.helpers import utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Paleta de colores (mismo dark theme que la factura PNG)
# ---------------------------------------------------------------------------

COL_BG = colors.HexColor("#0F0F12")
COL_SURFACE = colors.HexColor("#1A1A1F")
COL_TEXT = colors.HexColor("#E4E4E7")
COL_MUTED = colors.HexColor("#A1A1AA")
COL_ACCENT = colors.HexColor("#0078D4")
COL_SUCCESS = colors.HexColor("#22C55E")
COL_BORDER = colors.HexColor("#2E2E38")
COL_WARN = colors.HexColor("#F59E0B")
COL_TABLE_HEADER = colors.HexColor("#1F1F28")
COL_TABLE_ROW_ALT = colors.HexColor("#15151A")

# Para PDF imprimible, mejor usar fondo blanco con texto oscuro
PDF_BG = colors.white
PDF_TEXT = colors.HexColor("#1F2937")
PDF_MUTED = colors.HexColor("#6B7280")
PDF_ACCENT = colors.HexColor("#1E40AF")
PDF_SUCCESS = colors.HexColor("#15803D")
PDF_WARN = colors.HexColor("#B45309")
PDF_BORDER = colors.HexColor("#D1D5DB")
PDF_TABLE_HEADER_BG = colors.HexColor("#1E3A8A")
PDF_TABLE_HEADER_FG = colors.white
PDF_TABLE_ROW_ALT = colors.HexColor("#F3F4F6")


# ---------------------------------------------------------------------------
# Helpers de acceso a datos (acepta dict u objeto)
# ---------------------------------------------------------------------------

def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Obtiene un atributo o key de un dict/objeto de forma segura."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_dict(obj: Any) -> dict:
    """Convierte cualquier objeto en dict (para inspección)."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    # Pydantic / dataclass / ORM
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {}


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        s = str(value)
    except Exception:
        return default
    return s


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _fmt_money(value: Any, business_info: Any = None) -> str:
    """Formatea moneda usando el símbolo de business_info o config."""
    sym = _get(business_info, "currency_symbol", None)
    decimals = _get(business_info, "currency_decimals", None)
    if sym is None or decimals is None:
        try:
            s = get_settings().business
            sym = s.currency_symbol
            decimals = s.currency_decimals
        except Exception:
            sym, decimals = "$", 2
    return format_currency(_safe_float(value), sym, _safe_int(decimals, 2))


def _fmt_dt(value: Any, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Formatea un datetime/ISO string de forma segura."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime(fmt)
    try:
        # Intentar parsear ISO string
        s = str(value)
        # ISO 8601 con 'Z'
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).strftime(fmt)
    except Exception:
        return _safe_str(value)


# ---------------------------------------------------------------------------
# Estilos de párrafo
# ---------------------------------------------------------------------------

def _build_styles() -> dict[str, ParagraphStyle]:
    """Construye el set de estilos usados por los PDFs."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title", parent=base["Title"],
            fontSize=22, leading=26, textColor=PDF_ACCENT,
            alignment=TA_LEFT, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"],
            fontSize=10, leading=12, textColor=PDF_MUTED,
            alignment=TA_LEFT, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"],
            fontSize=14, leading=18, textColor=PDF_ACCENT,
            alignment=TA_LEFT, spaceBefore=12, spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading3"],
            fontSize=12, leading=15, textColor=PDF_TEXT,
            alignment=TA_LEFT, spaceBefore=8, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"],
            fontSize=10, leading=14, textColor=PDF_TEXT,
            alignment=TA_LEFT, spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["Normal"],
            fontSize=8, leading=10, textColor=PDF_MUTED,
            alignment=TA_LEFT,
        ),
        "right": ParagraphStyle(
            "Right", parent=base["Normal"],
            fontSize=10, leading=14, textColor=PDF_TEXT,
            alignment=TA_RIGHT,
        ),
        "center": ParagraphStyle(
            "Center", parent=base["Normal"],
            fontSize=10, leading=14, textColor=PDF_TEXT,
            alignment=TA_CENTER,
        ),
        "total": ParagraphStyle(
            "Total", parent=base["Normal"],
            fontSize=14, leading=18, textColor=PDF_SUCCESS,
            alignment=TA_RIGHT, spaceBefore=8, spaceAfter=8,
        ),
        "footer": ParagraphStyle(
            "Footer", parent=base["Normal"],
            fontSize=8, leading=10, textColor=PDF_MUTED,
            alignment=TA_CENTER,
        ),
        "table_header": ParagraphStyle(
            "TableHeader", parent=base["Normal"],
            fontSize=10, leading=12, textColor=PDF_TABLE_HEADER_FG,
            alignment=TA_LEFT,
        ),
        "table_header_right": ParagraphStyle(
            "TableHeaderRight", parent=base["Normal"],
            fontSize=10, leading=12, textColor=PDF_TABLE_HEADER_FG,
            alignment=TA_RIGHT,
        ),
        "table_cell": ParagraphStyle(
            "TableCell", parent=base["Normal"],
            fontSize=9, leading=11, textColor=PDF_TEXT,
            alignment=TA_LEFT,
        ),
        "table_cell_right": ParagraphStyle(
            "TableCellRight", parent=base["Normal"],
            fontSize=9, leading=11, textColor=PDF_TEXT,
            alignment=TA_RIGHT,
        ),
    }


# ---------------------------------------------------------------------------
# Tabla helper
# ---------------------------------------------------------------------------

def _styled_table(
    data: list[list[Any]],
    col_widths: list[float] | None = None,
    header: bool = True,
    zebra: bool = True,
) -> Table:
    """Construye una Table con el estilo estándar de LBAMonitor."""
    style = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, PDF_BORDER),
    ])
    if header:
        style.add("BACKGROUND", (0, 0), (-1, 0), PDF_TABLE_HEADER_BG)
        style.add("TEXTCOLOR", (0, 0), (-1, 0), PDF_TABLE_HEADER_FG)
        style.add("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")
    if zebra:
        start_row = 1 if header else 0
        for i in range(start_row, len(data)):
            if (i - start_row) % 2 == 1:
                style.add("BACKGROUND", (0, i), (-1, i), PDF_TABLE_ROW_ALT)
    return Table(data, colWidths=col_widths, style=style, repeatRows=1 if header else 0)


# ---------------------------------------------------------------------------
# PdfEngine
# ---------------------------------------------------------------------------

class PdfEngine:
    """
    Genera PDFs de factura, servicio y reporte diario.

    Todos los métodos son estáticos y devuelven el Path del PDF generado.
    No bloquean el event loop si se llaman vía `asyncio.to_thread()`.
    """

    PAGE_SIZE = A4
    MARGIN = 1.5 * cm

    # -----------------------------------------------------------------
    # 1. Factura de cobro
    # -----------------------------------------------------------------

    @staticmethod
    def generate_invoice_pdf(
        billing: Any,
        business_info: Any,
        output_path: Union[str, Path],
    ) -> Path:
        """
        Genera PDF de factura con datos del cobro.

        Args:
            billing: dict/objeto con: id, device_id, device_name, device_model,
                     gb_copied, files_copied, category, base_price, subtotal,
                     discount_percent, discount_amount, discount_reason,
                     tax_percent, tax_amount, total, charged, pricing_mode,
                     observations, created_at, created_by, webcam_image_path,
                     copies (lista de {file_name, size_bytes, extension}).
            business_info: dict/objeto con name, address, phone, email,
                           currency_symbol, currency_decimals.
            output_path: ruta destino (si no termina en .pdf se añade).

        Returns:
            Path del PDF generado.
        """
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".pdf":
            output_path = output_path.with_suffix(".pdf")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        styles = _build_styles()
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=PdfEngine.PAGE_SIZE,
            leftMargin=PdfEngine.MARGIN,
            rightMargin=PdfEngine.MARGIN,
            topMargin=PdfEngine.MARGIN,
            bottomMargin=PdfEngine.MARGIN,
            title=f"Factura LBAMonitor #{_safe_int(_get(billing, 'id'))}",
            author=_safe_str(_get(business_info, "name", "LBAMonitor")),
        )
        story: list[Any] = []

        # ---- Header ----
        biz_name = _safe_str(_get(business_info, "name", "Mi Copistería"))
        biz_addr = _safe_str(_get(business_info, "address", ""))
        biz_phone = _safe_str(_get(business_info, "phone", ""))
        biz_email = _safe_str(_get(business_info, "email", ""))

        header_data = [[
            Paragraph(f"<b>{biz_name}</b>", styles["title"]),
            Paragraph(
                f"<b>FACTURA</b><br/>"
                f"N° {_safe_int(_get(billing, 'id'))}<br/>"
                f"Fecha: {_fmt_dt(_get(billing, 'created_at', utcnow()), '%Y-%m-%d')}<br/>"
                f"Hora: {_fmt_dt(_get(billing, 'created_at', utcnow()), '%H:%M:%S')}",
                styles["right"],
            ),
        ]]
        header_table = Table(header_data, colWidths=[10 * cm, 7 * cm])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 4))

        contact_lines = []
        if biz_addr:
            contact_lines.append(f"Dirección: {biz_addr}")
        if biz_phone:
            contact_lines.append(f"Teléfono: {biz_phone}")
        if biz_email:
            contact_lines.append(f"Email: {biz_email}")
        if contact_lines:
            story.append(Paragraph("<br/>".join(contact_lines), styles["small"]))
        story.append(Spacer(1, 10))

        # Línea separadora
        story.append(_horizontal_rule())
        story.append(Spacer(1, 8))

        # ---- Datos del dispositivo ----
        story.append(Paragraph("Datos del dispositivo", styles["h3"]))
        dev_rows = [
            ["Dispositivo", _safe_str(_get(billing, "device_name", "—"))],
            ["Modelo", _safe_str(_get(billing, "device_model", "—"))],
            ["Categoría", _safe_str(_get(billing, "category", "—"))],
            ["Archivos copiados", str(_safe_int(_get(billing, "files_copied", 0)))],
            ["GB copiados", f"{_safe_float(_get(billing, 'gb_copied', 0)):.2f} GB"],
            ["Operador", _safe_str(_get(billing, "created_by", "—"))],
        ]
        dev_table = _styled_table(
            [[Paragraph(c, styles["table_cell"]) for c in row] for row in dev_rows],
            col_widths=[5 * cm, 12 * cm],
            header=False,
            zebra=True,
        )
        story.append(dev_table)
        story.append(Spacer(1, 12))

        # ---- Detalle de archivos copiados (opcional) ----
        copies = _get(billing, "copies", None) or []
        if copies:
            story.append(Paragraph("Detalle de archivos copiados", styles["h3"]))
            max_rows = 25
            visible = list(copies)[:max_rows]
            rows = [[
                Paragraph("<b>Nombre</b>", styles["table_header"]),
                Paragraph("<b>Ext</b>", styles["table_header"]),
                Paragraph("<b>Tamaño</b>", styles["table_header_right"]),
            ]]
            for copy in visible:
                name = _safe_str(_get(copy, "file_name", ""), "—")
                ext = _safe_str(_get(copy, "extension", ""), "—")
                size = format_bytes(_safe_int(_get(copy, "size_bytes", 0)))
                rows.append([
                    Paragraph(name, styles["table_cell"]),
                    Paragraph(ext, styles["table_cell"]),
                    Paragraph(size, styles["table_cell_right"]),
                ])
            if len(copies) > max_rows:
                rows.append([
                    Paragraph(
                        f"<i>... y {len(copies) - max_rows} archivos más</i>",
                        styles["table_cell"],
                    ),
                    "",
                    "",
                ])
            copies_table = _styled_table(
                rows,
                col_widths=[10 * cm, 3 * cm, 4 * cm],
                header=True,
                zebra=True,
            )
            story.append(copies_table)
            story.append(Spacer(1, 12))

        # ---- Totales ----
        story.append(Paragraph("Resumen del cobro", styles["h3"]))

        base_price = _safe_float(_get(billing, "base_price", 0))
        discount_amount = _safe_float(_get(billing, "discount_amount", 0))
        discount_percent = _safe_float(_get(billing, "discount_percent", 0))
        discount_reason = _safe_str(_get(billing, "discount_reason", ""))
        subtotal = _safe_float(_get(billing, "subtotal", 0))
        tax_amount = _safe_float(_get(billing, "tax_amount", 0))
        tax_percent = _safe_float(_get(billing, "tax_percent", 0))
        total = _safe_float(_get(billing, "total", 0))
        charged = _get(billing, "charged", None)
        pricing_mode = _safe_str(_get(billing, "pricing_mode", ""), "")

        total_rows = [
            ["Modo de cobro", pricing_mode or "—"],
            ["Precio base", _fmt_money(base_price, business_info)],
        ]
        if discount_amount > 0:
            label = f"Descuento ({discount_percent:.1f}%)"
            if discount_reason:
                label += f" — {discount_reason}"
            total_rows.append([label, f"- {_fmt_money(discount_amount, business_info)}"])
        total_rows.append(["Subtotal", _fmt_money(subtotal, business_info)])
        if tax_amount > 0:
            total_rows.append(
                [f"Impuesto ({tax_percent:.1f}%)", _fmt_money(tax_amount, business_info)]
            )
        total_rows.append(["TOTAL", _fmt_money(total, business_info)])
        if charged is not None:
            total_rows.append(["Cobrado", _fmt_money(charged, business_info)])

        total_table_data = []
        for i, (label, value) in enumerate(total_rows):
            is_total = label == "TOTAL"
            is_charged = label == "Cobrado"
            label_style = styles["body"]
            value_style = styles["right"]
            if is_total:
                label_p = Paragraph(f"<b>{label}</b>", styles["h3"])
                value_p = Paragraph(f"<b>{value}</b>", styles["total"])
            elif is_charged:
                label_p = Paragraph(f"<b>{label}</b>", styles["body"])
                value_p = Paragraph(f"<b>{value}</b>", styles["right"])
            else:
                label_p = Paragraph(label, label_style)
                value_p = Paragraph(value, value_style)
            total_table_data.append([label_p, value_p])

        total_table = Table(
            total_table_data, colWidths=[10 * cm, 7 * cm], hAlign="RIGHT"
        )
        total_style = TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEABOVE", (0, -2), (-1, -2), 0.5, PDF_BORDER),
        ])
        # Resaltar fila TOTAL
        total_idx = len(total_rows) - 2 if charged is not None else len(total_rows) - 1
        total_style.add("BACKGROUND", (0, total_idx), (-1, total_idx), colors.HexColor("#DBEAFE"))
        total_style.add("LINEABOVE", (0, total_idx), (-1, total_idx), 1.0, PDF_ACCENT)
        if charged is not None:
            total_style.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#D1FAE5"))
            total_style.add("LINEABOVE", (0, -1), (-1, -1), 1.0, PDF_SUCCESS)
        total_table.setStyle(total_style)
        story.append(total_table)
        story.append(Spacer(1, 16))

        # ---- Webcam image (opcional) ----
        webcam_path = _get(billing, "webcam_image_path", None)
        if webcam_path and Path(webcam_path).is_file():
            try:
                img = Image(str(webcam_path))
                # Escalar a máximo 6cm de ancho
                max_w = 6 * cm
                if img.drawWidth > max_w:
                    ratio = max_w / img.drawWidth
                    img.drawWidth = max_w
                    img.drawHeight = img.drawHeight * ratio
                img.hAlign = "RIGHT"
                story.append(Paragraph("Foto de registro del cliente", styles["h3"]))
                story.append(img)
                story.append(Spacer(1, 8))
            except Exception as e:
                log.warning(f"No se pudo embeber imagen webcam en PDF: {e}")

        # ---- Observaciones ----
        obs = _safe_str(_get(billing, "observations", ""), "")
        if obs:
            story.append(Paragraph("Observaciones", styles["h3"]))
            story.append(Paragraph(obs, styles["body"]))
            story.append(Spacer(1, 8))

        # ---- Footer ----
        story.append(Spacer(1, 16))
        story.append(_horizontal_rule())
        story.append(Spacer(1, 6))
        footer_text = (
            f"Gracias por su preferencia. "
            f"Este documento es válido como comprobante de cobro. "
            f"Consérvelo para cualquier reclamo.<br/>"
            f"Generado por LBAMonitor el {_fmt_dt(utcnow())} · "
            f"Operador: {_safe_str(_get(billing, 'created_by', '—'))}"
        )
        story.append(Paragraph(footer_text, styles["footer"]))

        doc.build(story)
        log.info(f"PDF factura generado: {output_path}")
        return output_path

    # -----------------------------------------------------------------
    # 2. PDF explicativo del servicio
    # -----------------------------------------------------------------

    @staticmethod
    def generate_service_pdf(
        business_info: Any,
        output_path: Union[str, Path],
    ) -> Path:
        """
        Genera PDF explicativo del servicio (precios, reglas, membresías).

        Se auto-copia al USB la primera vez que se inserta, para que el
        cliente conozca las tarifas y promociones vigentes.

        Args:
            business_info: dict/objeto con name, address, phone, email, etc.
            output_path: ruta destino.

        Returns:
            Path del PDF generado.
        """
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".pdf":
            output_path = output_path.with_suffix(".pdf")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Cargar config de pricing
        try:
            settings = get_settings()
            pricing = settings.pricing
            biz = settings.business
        except Exception:
            pricing = None
            biz = None

        styles = _build_styles()
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=PdfEngine.PAGE_SIZE,
            leftMargin=PdfEngine.MARGIN,
            rightMargin=PdfEngine.MARGIN,
            topMargin=PdfEngine.MARGIN,
            bottomMargin=PdfEngine.MARGIN,
            title="Servicio LBAMonitor",
            author=_safe_str(_get(business_info, "name", "LBAMonitor")),
        )
        story: list[Any] = []

        # ---- Header ----
        biz_name = _safe_str(_get(business_info, "name", biz.name if biz else "Mi Copistería"))
        biz_addr = _safe_str(_get(business_info, "address", biz.address if biz else ""))
        biz_phone = _safe_str(_get(business_info, "phone", biz.phone if biz else ""))
        biz_email = _safe_str(_get(business_info, "email", biz.email if biz else ""))

        story.append(Paragraph(biz_name, styles["title"]))
        subtitle_parts = []
        if biz_addr:
            subtitle_parts.append(biz_addr)
        if biz_phone:
            subtitle_parts.append(f"Tel: {biz_phone}")
        if biz_email:
            subtitle_parts.append(biz_email)
        if subtitle_parts:
            story.append(Paragraph(" · ".join(subtitle_parts), styles["subtitle"]))
        story.append(_horizontal_rule())
        story.append(Spacer(1, 12))

        story.append(Paragraph("Información del servicio", styles["h2"]))
        story.append(Paragraph(
            "Bienvenido/a. A continuación encontrará nuestras tarifas vigentes, "
            "niveles de membresía, reglas de recompensas y promociones activas. "
            "Si tiene dudas, consulte al operador.",
            styles["body"],
        ))
        story.append(Spacer(1, 12))

        # ---- Lista de precios ----
        story.append(Paragraph("Tarifas", styles["h2"]))
        price_rows = [[
            Paragraph("<b>Modalidad</b>", styles["table_header"]),
            Paragraph("<b>Descripción</b>", styles["table_header"]),
            Paragraph("<b>Precio</b>", styles["table_header"]),
        ]]
        if pricing is not None:
            sym = biz.currency_symbol if biz else "$"
            dec = biz.currency_decimals if biz else 2
            price_rows.extend([
                [
                    Paragraph("Por GB", styles["table_cell"]),
                    Paragraph("Pago por gigabyte copiado", styles["table_cell"]),
                    Paragraph(format_currency(pricing.price_per_gb, sym, dec), styles["table_cell_right"]),
                ],
                [
                    Paragraph("Por MB", styles["table_cell"]),
                    Paragraph("Pago por megabyte copiado", styles["table_cell"]),
                    Paragraph(format_currency(pricing.price_per_mb, sym, dec), styles["table_cell_right"]),
                ],
                [
                    Paragraph("Por archivo", styles["table_cell"]),
                    Paragraph("Pago por archivo copiado", styles["table_cell"]),
                    Paragraph(format_currency(pricing.price_per_file, sym, dec), styles["table_cell_right"]),
                ],
                [
                    Paragraph("Precio fijo", styles["table_cell"]),
                    Paragraph("Tarifa plana por sesión", styles["table_cell"]),
                    Paragraph(format_currency(pricing.fixed_price, sym, dec), styles["table_cell_right"]),
                ],
                [
                    Paragraph("Mínimo / Máximo", styles["table_cell"]),
                    Paragraph("Límites aplicables a cualquier modalidad", styles["table_cell"]),
                    Paragraph(
                        f"{format_currency(pricing.min_price, sym, dec)} / "
                        f"{format_currency(pricing.max_price, sym, dec)}",
                        styles["table_cell_right"],
                    ),
                ],
            ])
        else:
            price_rows.append([
                Paragraph("Consulte al operador", styles["table_cell"]),
                Paragraph("—", styles["table_cell"]),
                Paragraph("—", styles["table_header"]),
            ])
        story.append(_styled_table(price_rows, col_widths=[4 * cm, 9 * cm, 4 * cm]))
        story.append(Spacer(1, 14))

        # ---- Niveles de membresía ----
        story.append(Paragraph("Niveles de membresía", styles["h2"]))
        story.append(Paragraph(
            "Acumule visitas, GB copiados y dinero gastado para subir de nivel "
            "y obtener descuentos permanentes en todas sus copias.",
            styles["body"],
        ))
        story.append(Spacer(1, 6))

        # Niveles por defecto (definidos en LBA v3)
        tiers = [
            ("🥉 Bronce",     0,   0,    0,    0.0,   "#CD7F32"),
            ("🥈 Plata",      5,   10,   100,  5.0,   "#C0C0C0"),
            ("🥇 Oro",        15,  50,   500,  10.0,  "#FFD700"),
            ("💎 Platino",    30,  150,  1500, 15.0,  "#E5E4E2"),
            ("💠 Diamante",   60,  400,  4000, 20.0,  "#B9F2FF"),
        ]
        tier_rows = [[
            Paragraph("<b>Nivel</b>", styles["table_header"]),
            Paragraph("<b>Visitas mín.</b>", styles["table_header"]),
            Paragraph("<b>GB mín.</b>", styles["table_header"]),
            Paragraph("<b>Gasto mín.</b>", styles["table_header"]),
            Paragraph("<b>Descuento</b>", styles["table_header"]),
        ]]
        for name, visits, gb, spent, disc, _color in tiers:
            sym = biz.currency_symbol if biz else "$"
            tier_rows.append([
                Paragraph(f"<b>{name}</b>", styles["table_cell"]),
                Paragraph(str(visits), styles["table_cell_right"]),
                Paragraph(f"{gb} GB", styles["table_cell_right"]),
                Paragraph(format_currency(spent, sym, 0), styles["table_cell_right"]),
                Paragraph(f"<b>{disc:.0f}%</b>", styles["table_cell_right"]),
            ])
        story.append(_styled_table(
            tier_rows,
            col_widths=[4 * cm, 3 * cm, 3 * cm, 4 * cm, 3 * cm],
        ))
        story.append(Spacer(1, 14))

        # ---- Reglas de recompensas ----
        story.append(Paragraph("Recompensas", styles["h2"]))
        reward_rules = [
            ("Cliente frecuente",
             "Tras 10 visitas en el mes, obtenga 1 copia gratuita hasta 4 GB."),
            ("Cliente del mes",
             "El cliente con más GB copiados en el mes recibe 20% de descuento "
             "en todas sus copias del mes siguiente."),
            ("Bonus por volumen",
             "Si copia más de 50 GB en una sola sesión, reciba 10% de descuento "
             "adicional en esa sesión."),
            ("Regalo sorpresa",
             "Al alcanzar el nivel Platino, el cliente recibe una memoria USB "
             "de regalo (sujeto a disponibilidad)."),
        ]
        for title, desc in reward_rules:
            story.append(Paragraph(f"<b>{title}.</b> {desc}", styles["body"]))
            story.append(Spacer(1, 2))
        story.append(Spacer(1, 10))

        # ---- Promociones activas ----
        story.append(Paragraph("Promociones vigentes", styles["h2"]))
        if pricing is not None and pricing.promotion_enabled and pricing.promotion_discount_percent > 0:
            story.append(Paragraph(
                f"<b>¡Promoción activa!</b> "
                f"{pricing.promotion_description or 'Descuento especial por tiempo limitado.'} "
                f"<b>Descuento adicional: {pricing.promotion_discount_percent:.1f}%</b>",
                styles["body"],
            ))
        else:
            story.append(Paragraph(
                "No hay promociones activas en este momento. "
                "Síganos en redes sociales para enterarse de las próximas ofertas.",
                styles["body"],
            ))
        story.append(Spacer(1, 14))

        # ---- VIPs ----
        story.append(Paragraph("Tratamientos VIP", styles["h2"]))
        vip_rows = [[
            Paragraph("<b>Tipo</b>", styles["table_header"]),
            Paragraph("<b>Descuento</b>", styles["table_header"]),
        ]]
        if pricing is not None:
            vip_rows.extend([
                [Paragraph("VIP", styles["table_cell"]),
                 Paragraph(f"{pricing.vip_discount_percent:.0f}%", styles["table_cell_right"])],
                [Paragraph("Empleado", styles["table_cell"]),
                 Paragraph(f"{pricing.employee_discount_percent:.0f}%", styles["table_cell_right"])],
                [Paragraph("Cortesía / Negocio", styles["table_cell"]),
                 Paragraph("100% (gratis)", styles["table_cell_right"])],
            ])
        story.append(_styled_table(vip_rows, col_widths=[10 * cm, 7 * cm]))
        story.append(Spacer(1, 14))

        # ---- Horario ----
        story.append(Paragraph("Horario de atención", styles["h2"]))
        schedule_rows = [[
            Paragraph("<b>Día</b>", styles["table_header"]),
            Paragraph("<b>Horario</b>", styles["table_header"]),
        ]]
        horario = _get(business_info, "schedule", None)
        if horario and isinstance(horario, dict):
            for dia, hora in horario.items():
                schedule_rows.append([
                    Paragraph(_safe_str(dia), styles["table_cell"]),
                    Paragraph(_safe_str(hora), styles["table_cell"]),
                ])
        else:
            default_schedule = [
                ("Lunes a Viernes", "9:00 – 18:00"),
                ("Sábados", "9:00 – 14:00"),
                ("Domingos", "Cerrado"),
            ]
            for dia, hora in default_schedule:
                schedule_rows.append([
                    Paragraph(dia, styles["table_cell"]),
                    Paragraph(hora, styles["table_cell"]),
                ])
        story.append(_styled_table(schedule_rows, col_widths=[7 * cm, 10 * cm]))
        story.append(Spacer(1, 16))

        # ---- Footer ----
        story.append(_horizontal_rule())
        story.append(Spacer(1, 6))
        footer_text = (
            f"{biz_name} · Documento informativo · "
            f"Generado por LBAMonitor el {_fmt_dt(utcnow(), '%Y-%m-%d')}.<br/>"
            "Las tarifas y promociones pueden cambiar sin previo aviso. "
            "Consulte siempre al operador antes de iniciar la copia."
        )
        story.append(Paragraph(footer_text, styles["footer"]))

        doc.build(story)
        log.info(f"PDF servicio generado: {output_path}")
        return output_path

    # -----------------------------------------------------------------
    # 3. Reporte diario (estilo Mirón)
    # -----------------------------------------------------------------

    @staticmethod
    def generate_daily_report_pdf(
        stats: Any,
        business_info: Any,
        output_path: Union[str, Path],
    ) -> Path:
        """
        Genera PDF con reporte diario de actividad (estilo Mirón).

        Args:
            stats: dict/objeto con KPIs del día. Claves esperadas:
                   range_start, range_end, transactions, revenue, discounts,
                   usb_count, sessions, gb_copied, files_copied,
                   avg_per_session, avg_per_gb, top_clients, top_files,
                   hourly_heatmap, etc.
            business_info: dict/objeto con name, address, etc.
            output_path: ruta destino.

        Returns:
            Path del PDF generado.
        """
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".pdf":
            output_path = output_path.with_suffix(".pdf")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        styles = _build_styles()
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=PdfEngine.PAGE_SIZE,
            leftMargin=PdfEngine.MARGIN,
            rightMargin=PdfEngine.MARGIN,
            topMargin=PdfEngine.MARGIN,
            bottomMargin=PdfEngine.MARGIN,
            title="Reporte diario LBAMonitor",
            author=_safe_str(_get(business_info, "name", "LBAMonitor")),
        )
        story: list[Any] = []

        # ---- Header ----
        biz_name = _safe_str(_get(business_info, "name", "Mi Copistería"))
        story.append(Paragraph(biz_name, styles["title"]))
        range_start = _get(stats, "range_start", None)
        range_end = _get(stats, "range_end", None)
        if range_start and range_end:
            period = (
                f"Reporte diario · "
                f"{_fmt_dt(range_start, '%Y-%m-%d %H:%M')} → "
                f"{_fmt_dt(range_end, '%Y-%m-%d %H:%M')}"
            )
        else:
            period = f"Reporte diario · {_fmt_dt(utcnow(), '%Y-%m-%d')}"
        story.append(Paragraph(period, styles["subtitle"]))
        story.append(_horizontal_rule())
        story.append(Spacer(1, 12))

        # ---- KPIs principales ----
        story.append(Paragraph("Resumen del día", styles["h2"]))

        kpi_data = [
            ["Transacciones", str(_safe_int(_get(stats, "transactions", 0)))],
            ["Ingresos", _fmt_money(_get(stats, "revenue", 0), business_info)],
            ["Descuentos otorgados", _fmt_money(_get(stats, "discounts", 0), business_info)],
            ["Dispositivos insertados", str(_safe_int(_get(stats, "usb_count", 0)))],
            ["Sesiones", str(_safe_int(_get(stats, "sessions", 0)))],
            ["Archivos copiados", str(_safe_int(_get(stats, "files_copied", 0)))],
            ["GB copiados", f"{_safe_float(_get(stats, 'gb_copied', 0)):.2f} GB"],
            ["Promedio por sesión", _fmt_money(_get(stats, "avg_per_session", 0), business_info)],
            ["Promedio por GB", _fmt_money(_get(stats, "avg_per_gb", 0), business_info)],
        ]
        kpi_rows = [[
            Paragraph("<b>Métrica</b>", styles["table_header"]),
            Paragraph("<b>Valor</b>", styles["table_header"]),
        ]]
        for label, value in kpi_data:
            kpi_rows.append([
                Paragraph(label, styles["table_cell"]),
                Paragraph(value, styles["table_cell_right"]),
            ])
        story.append(_styled_table(kpi_rows, col_widths=[10 * cm, 7 * cm]))
        story.append(Spacer(1, 14))

        # ---- Top clientes ----
        top_clients = _get(stats, "top_clients", None) or []
        if top_clients:
            story.append(Paragraph("Top clientes del día", styles["h2"]))
            tc_rows = [[
                Paragraph("<b>#</b>", styles["table_header"]),
                Paragraph("<b>Alias / Serial</b>", styles["table_header"]),
                Paragraph("<b>Visitas</b>", styles["table_header"]),
                Paragraph("<b>Nivel</b>", styles["table_header"]),
            ]]
            for i, c in enumerate(top_clients[:10], start=1):
                alias = _safe_str(_get(c, "alias", _get(c, "serial", "—")), "—")
                tc_rows.append([
                    Paragraph(str(i), styles["table_cell_right"]),
                    Paragraph(alias, styles["table_cell"]),
                    Paragraph(str(_safe_int(_get(c, "visit_count", 0))), styles["table_cell_right"]),
                    Paragraph(_safe_str(_get(c, "tier", "—")), styles["table_cell"]),
                ])
            story.append(_styled_table(
                tc_rows, col_widths=[1.5 * cm, 9 * cm, 3 * cm, 3.5 * cm],
            ))
            story.append(Spacer(1, 14))

        # ---- Top archivos más copiados ----
        top_files = _get(stats, "top_files", None) or []
        if top_files:
            story.append(Paragraph("Archivos más copiados", styles["h2"]))
            tf_rows = [[
                Paragraph("<b>#</b>", styles["table_header"]),
                Paragraph("<b>Nombre</b>", styles["table_header"]),
                Paragraph("<b>Veces</b>", styles["table_header"]),
                Paragraph("<b>Tamaño</b>", styles["table_header"]),
            ]]
            for i, f in enumerate(top_files[:15], start=1):
                name = _safe_str(_get(f, "file_name", _get(f, "name", "—")), "—")
                count = _safe_int(_get(f, "count", _get(f, "times_copied", 0)))
                size = format_bytes(_safe_int(_get(f, "size_bytes", _get(f, "size", 0))))
                tf_rows.append([
                    Paragraph(str(i), styles["table_cell_right"]),
                    Paragraph(name[:60], styles["table_cell"]),
                    Paragraph(str(count), styles["table_cell_right"]),
                    Paragraph(size, styles["table_cell_right"]),
                ])
            story.append(_styled_table(
                tf_rows, col_widths=[1.5 * cm, 9 * cm, 3 * cm, 3.5 * cm],
            ))
            story.append(Spacer(1, 14))

        # ---- Heatmap de horas pico ----
        heatmap = _get(stats, "hourly_heatmap", None) or _get(stats, "hourly", None) or []
        if heatmap:
            story.append(Paragraph("Distribución por hora", styles["h2"]))
            # Agregar por hora
            by_hour: dict[int, int] = {}
            for entry in heatmap:
                h = _safe_int(_get(entry, "hour", -1), -1)
                c = _safe_int(_get(entry, "count", 0))
                if 0 <= h <= 23:
                    by_hour[h] = by_hour.get(h, 0) + c
            if by_hour:
                hm_rows = [[
                    Paragraph("<b>Hora</b>", styles["table_header"]),
                    Paragraph("<b>Cantidad</b>", styles["table_header"]),
                    Paragraph("<b>Distribución</b>", styles["table_header"]),
                ]]
                max_count = max(by_hour.values()) if by_hour else 1
                for h in range(24):
                    c = by_hour.get(h, 0)
                    bar_len = int((c / max_count) * 30) if max_count > 0 else 0
                    bar = "█" * bar_len if bar_len > 0 else "—"
                    hm_rows.append([
                        Paragraph(f"{h:02d}:00", styles["table_cell"]),
                        Paragraph(str(c), styles["table_cell_right"]),
                        Paragraph(f"<font face='Courier'>{bar}</font>", styles["table_cell"]),
                    ])
                story.append(_styled_table(
                    hm_rows, col_widths=[3 * cm, 3 * cm, 11 * cm],
                ))
                story.append(Spacer(1, 14))

        # ---- Footer ----
        story.append(Spacer(1, 8))
        story.append(_horizontal_rule())
        story.append(Spacer(1, 6))
        footer_text = (
            f"{biz_name} · Reporte generado por LBAMonitor · "
            f"{_fmt_dt(utcnow())}. "
            f"Documento interno — no entregar al cliente."
        )
        story.append(Paragraph(footer_text, styles["footer"]))

        doc.build(story)
        log.info(f"PDF reporte diario generado: {output_path}")
        return output_path


# ---------------------------------------------------------------------------
# Helpers visuales
# ---------------------------------------------------------------------------

def _horizontal_rule(color=PDF_BORDER, width: float = 0.5) -> Table:
    """Devuelve una línea horizontal como Table de 1 fila."""
    t = Table([[""]], colWidths=[17 * cm], rowHeights=[0.1])
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, -1), width, color),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

def get_pdf_engine() -> type[PdfEngine]:
    """Devuelve la clase PdfEngine (todos los métodos son estáticos)."""
    return PdfEngine
