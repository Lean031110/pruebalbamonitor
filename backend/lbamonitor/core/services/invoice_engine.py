"""
Generación de facturas en imagen PNG con Pillow.

Opcionalmente captura una foto de la webcam al momento de facturar
(paridad con Uatcher InvoicePictureDevice).

La factura incluye:
  - Header con BusinessInfo.Name y MarketingText
  - Fecha/hora
  - Datos del dispositivo
  - Listado tabular de archivos copiados
  - Total archivos y bytes
  - Pago cobrado
  - Footer con BusinessInfo.Address
  - (Opcional) Foto de la webcam en una esquina

PERSISTENCIA EN ESCRITORIO (v4.4):
  Cuando se genera una factura con webcam, se guardan también:
    - La foto de la webcam como JPG en
      <desktop>/LBAMonitor/<YYYY-MM-DD>/<HHMMSS>_<username>.jpg
    - El PDF de la factura en la misma carpeta con el mismo nombre base
      pero extensión .pdf
  Esto permite al operador tener un registro local de los cobros con foto,
  incluso si la BD se corrompe o se elimina.
"""
from __future__ import annotations

import asyncio
import io
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from lbamonitor.core.config import get_settings
from lbamonitor.utils.formatters import format_bytes, format_currency
from lbamonitor.utils.helpers import slugify, utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


# Colores (paleta dark)
COLOR_BG = (15, 15, 18)  # #0F0F12
COLOR_SURFACE = (26, 26, 31)
COLOR_TEXT = (228, 228, 231)
COLOR_MUTED = (161, 161, 170)
COLOR_ACCENT = (0, 120, 212)
COLOR_SUCCESS = (34, 197, 94)
COLOR_BORDER = (46, 46, 56)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Carga una fuente TrueType con fallback a default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in font_paths:
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def capture_webcam_frame() -> Optional[bytes]:
    """
    Captura un frame de la webcam (paridad Uatcher InvoicePictureDevice).

    Usa opencv-python (cv2). Si no hay cámara o falla, devuelve None.

    Devuelve bytes PNG listos para pegar en la factura.
    """
    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # type: ignore[attr-defined]
        if not cap.isOpened():
            log.debug("No se pudo abrir la webcam")
            return None

        # Calentar la cámara (algunas necesitan frames de descarte)
        for _ in range(5):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            log.debug("Webcam no devolvió frame")
            return None

        # Convertir BGR → RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        # Escalar a tamaño pequeño
        img.thumbnail((240, 180))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        log.debug("opencv-python no instalado, webcam no disponible")
        return None
    except Exception as e:
        log.warning(f"Error capturando webcam: {e}")
        return None


async def generate_invoice_image(
    drive_id: int,
    drive_name: str,
    drive_serial: Optional[str],
    drive_model: Optional[str],
    copies: list[dict],
    payment: Optional[float] = None,
    business_name: Optional[str] = None,
    business_address: Optional[str] = None,
    marketing_text: Optional[str] = None,
    include_webcam: bool = False,
    username: Optional[str] = None,
) -> bytes:
    """
    Genera la imagen PNG de la factura.

    Args:
        drive_id: ID del InsertedDrive.
        drive_name: nombre del dispositivo ("E:\\").
        drive_serial: serial del dispositivo.
        drive_model: modelo.
        copies: lista de dicts con {file_name, size_bytes, extension, copy_date_time}.
        payment: pago cobrado.
        business_name, business_address, marketing_text: info del negocio.
        include_webcam: si True, captura y pega una foto de la webcam.
        username: nombre del operador (para nombrar el archivo guardado en
            escritorio). Si es None, se usa "operador".

    Devuelve bytes PNG.

    EFECTO SECUNDARIO (v4.4):
      Si `include_webcam=True` y la webcam captura un frame, se guardan en
      el escritorio del usuario:
        - <desktop>/LBAMonitor/<YYYY-MM-DD>/<HHMMSS>_<username>.jpg (webcam)
        - <desktop>/LBAMonitor/<YYYY-MM-DD>/<HHMMSS>_<username>.pdf (factura)
      Los errores de guardado se loggean como warning pero NO rompen la
      generación del PNG (que es el contrato original de esta función).
    """
    # Captura webcam en paralelo (no bloquea)
    webcam_bytes: Optional[bytes] = None
    if include_webcam:
        webcam_bytes = await asyncio.to_thread(capture_webcam_frame)

    s = get_settings().business
    biz_name = business_name or s.name
    biz_addr = business_address or s.address
    biz_marketing = marketing_text or ""

    # Dimensiones
    width = 800
    margin = 40
    line_height = 22
    header_height = 180
    footer_height = 80
    table_row_height = 24
    max_rows_visible = 20

    # Calcular altura dinámica según número de copias
    visible_copies = copies[:max_rows_visible]
    table_height = (len(visible_copies) + 2) * table_row_height  # +2: header + separator
    height = header_height + table_height + footer_height + margin * 2

    if webcam_bytes:
        height = max(height, header_height + 220)

    img = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # Fuentes
    font_title = _load_font(28)
    font_h2 = _load_font(18)
    font_body = _load_font(14)
    font_small = _load_font(12)

    y = margin

    # Header
    draw.text((margin, y), biz_name, fill=COLOR_TEXT, font=font_title)
    y += 36
    if biz_marketing:
        draw.text((margin, y), biz_marketing, fill=COLOR_MUTED, font=font_small)
        y += 18

    now_str = utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    draw.text((margin, y), f"Fecha: {now_str}", fill=COLOR_MUTED, font=font_body)
    y += line_height
    draw.text((margin, y), f"Dispositivo: {drive_name}", fill=COLOR_TEXT, font=font_body)
    y += line_height
    if drive_model:
        draw.text((margin, y), f"Modelo: {drive_model}", fill=COLOR_MUTED, font=font_body)
        y += line_height
    if drive_serial:
        short_serial = drive_serial[:32] + "..." if len(drive_serial) > 32 else drive_serial
        draw.text((margin, y), f"Serial: {short_serial}", fill=COLOR_MUTED, font=font_body)
        y += line_height
    draw.text((margin, y), f"Inserción #{drive_id}", fill=COLOR_MUTED, font=font_body)
    y += line_height + 10

    # Separador
    draw.line([(margin, y), (width - margin, y)], fill=COLOR_BORDER, width=1)
    y += 10

    # Tabla de copias
    draw.text((margin, y), "Archivos copiados:", fill=COLOR_TEXT, font=font_h2)
    y += 28

    # Cabecera tabla
    col_name_x = margin
    col_size_x = width - margin - 100
    col_ext_x = width - margin - 200
    draw.text((col_name_x, y), "Nombre", fill=COLOR_MUTED, font=font_small)
    draw.text((col_ext_x, y), "Ext", fill=COLOR_MUTED, font=font_small)
    draw.text((col_size_x, y), "Tamaño", fill=COLOR_MUTED, font=font_small)
    y += table_row_height
    draw.line([(margin, y), (width - margin, y)], fill=COLOR_BORDER, width=1)
    y += 4

    total_bytes = 0
    for copy in visible_copies:
        name = (copy.get("file_name") or "")[:50]
        ext = (copy.get("extension") or "").ljust(6)
        size = copy.get("size_bytes") or 0
        total_bytes += size
        draw.text((col_name_x, y), name, fill=COLOR_TEXT, font=font_small)
        draw.text((col_ext_x, y), ext, fill=COLOR_MUTED, font=font_small)
        draw.text((col_size_x, y), format_bytes(size), fill=COLOR_MUTED, font=font_small)
        y += table_row_height

    if len(copies) > max_rows_visible:
        draw.text(
            (margin, y),
            f"... y {len(copies) - max_rows_visible} archivos más",
            fill=COLOR_MUTED,
            font=font_small,
        )
        y += table_row_height

    # Totales
    y += 10
    draw.line([(margin, y), (width - margin, y)], fill=COLOR_BORDER, width=1)
    y += 10
    draw.text(
        (margin, y),
        f"Total: {len(copies)} archivos • {format_bytes(total_bytes)}",
        fill=COLOR_TEXT,
        font=font_body,
    )
    y += line_height

    if payment is not None:
        s_biz = get_settings().business
        payment_str = format_currency(payment, s_biz.currency_symbol, s_biz.currency_decimals)
        draw.text((margin, y), f"Cobrado: {payment_str}", fill=COLOR_SUCCESS, font=font_h2)
        y += 28

    # Webcam (esquina inferior derecha)
    if webcam_bytes:
        try:
            cam_img = Image.open(io.BytesIO(webcam_bytes))
            # Marco
            cam_x = width - margin - 240
            cam_y = height - footer_height - 200
            draw.rectangle(
                [(cam_x - 4, cam_y - 4), (cam_x + 244, cam_y + 184)],
                fill=COLOR_SURFACE,
                outline=COLOR_ACCENT,
                width=2,
            )
            img.paste(cam_img, (cam_x, cam_y))
            draw.text((cam_x, cam_y + 186), "Foto de registro", fill=COLOR_MUTED, font=font_small)
        except Exception as e:
            log.warning(f"Error pegando webcam en factura: {e}")

    # Footer
    y_footer = height - footer_height
    draw.line([(margin, y_footer), (width - margin, y_footer)], fill=COLOR_BORDER, width=1)
    y_footer += 15
    if biz_addr:
        draw.text((margin, y_footer), biz_addr, fill=COLOR_MUTED, font=font_small)
        y_footer += 16
    draw.text((margin, y_footer), f"Generado por LBAMonitor • {now_str}", fill=COLOR_MUTED, font=font_small)

    # Convertir a bytes PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    log.info(f"Factura generada para drive #{drive_id} ({len(copies)} copias, {len(buf.getvalue())} bytes)")

    # Persistir webcam (JPG) + PDF factura en escritorio (v4.4)
    if webcam_bytes:
        try:
            await _persist_invoice_to_desktop(
                drive_id=drive_id,
                drive_name=drive_name,
                drive_serial=drive_serial,
                drive_model=drive_model,
                copies=copies,
                payment=payment,
                business_name=biz_name,
                business_address=biz_addr,
                webcam_bytes=webcam_bytes,
                username=username,
            )
        except Exception as e:
            log.warning(
                f"No se pudo persistir factura/webcam en escritorio para "
                f"drive #{drive_id}: {e}"
            )

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Persistencia en escritorio (v4.4)
# ---------------------------------------------------------------------------

def _get_desktop_folder() -> Path:
    """
    Devuelve la carpeta Desktop del usuario actual.

    - Windows: C:\\Users\\<user>\\Desktop
    - Linux:   ~/Desktop (si existe) o ~/ como fallback
    - Mac:     ~/Desktop

    Si ~/Desktop no existe en Linux/Mac, se crea ~/LBAMonitor directamente
    en home (en lugar de ~/Desktop/LBAMonitor).
    """
    home = Path.home()
    desktop = home / "Desktop"
    if desktop.is_dir():
        return desktop
    # En servidores Linux headless, ~/Desktop no existe → usar ~ directamente.
    # El caller añade /LBAMonitor/<fecha>/ encima.
    return home


def _build_invoice_desktop_path(username: Optional[str]) -> Path:
    """
    Construye la ruta destino para guardar webcam + PDF en el escritorio.

    Formato:
      <desktop>/LBAMonitor/<YYYY-MM-DD>/<HHMMSS>_<username>.{jpg,pdf}

    Crea la carpeta si no existe.
    """
    now = utcnow()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    user_part = slugify(username) if username else "operador"
    if not user_part:
        user_part = "operador"

    base = _get_desktop_folder() / "LBAMonitor" / date_str
    base.mkdir(parents=True, exist_ok=True)
    # Devuelve la ruta SIN extensión; el caller añade .jpg o .pdf
    return base / f"{time_str}_{user_part}"


async def _persist_invoice_to_desktop(
    drive_id: int,
    drive_name: str,
    drive_serial: Optional[str],
    drive_model: Optional[str],
    copies: list[dict],
    payment: Optional[float],
    business_name: str,
    business_address: str,
    webcam_bytes: bytes,
    username: Optional[str],
) -> None:
    """
    Guarda la imagen de la webcam (JPG) y el PDF de la factura en el
    escritorio del usuario.

    Se ejecuta en hilo (asyncio.to_thread) para no bloquear el event loop.
    """
    base_path = await asyncio.to_thread(_build_invoice_desktop_path, username)

    jpg_path = base_path.with_suffix(".jpg")
    pdf_path = base_path.with_suffix(".pdf")

    # 1. Guardar webcam como JPG (en hilo)
    def _save_jpg() -> Path:
        cam_img = Image.open(io.BytesIO(webcam_bytes))
        # RGB para JPG (sin canal alfa)
        if cam_img.mode in ("RGBA", "LA", "P"):
            cam_img = cam_img.convert("RGB")
        cam_img.save(jpg_path, format="JPEG", quality=90)
        return jpg_path

    saved_jpg = await asyncio.to_thread(_save_jpg)
    log.info(f"Webcam guardada en escritorio: {saved_jpg}")

    # 2. Generar PDF de la factura (en hilo; reportlab es síncrono)
    def _save_pdf() -> Path:
        # Import diferido para no cargar reportlab al importar invoice_engine
        from lbamonitor.core.services.pdf_engine import PdfEngine

        # Calcular GB copiados
        total_bytes = 0
        for c in copies:
            try:
                total_bytes += int(c.get("size_bytes", 0) or 0)
            except (TypeError, ValueError):
                pass
        gb_copied = total_bytes / (1024 ** 3)

        billing = {
            "id": drive_id,
            "device_name": drive_name,
            "device_model": drive_model or "",
            "category": "general",
            "files_copied": len(copies),
            "gb_copied": gb_copied,
            "created_by": username or "operador",
            "created_at": utcnow().isoformat(),
            "base_price": float(payment) if payment else 0.0,
            "discount_amount": 0.0,
            "discount_percent": 0.0,
            "discount_reason": "",
            "subtotal": float(payment) if payment else 0.0,
            "tax_amount": 0.0,
            "tax_percent": 0.0,
            "total": float(payment) if payment else 0.0,
            "charged": float(payment) if payment is not None else None,
            "pricing_mode": "manual",
            "observations": f"Dispositivo: {drive_name} (serial: {drive_serial or '—'})",
            "copies": copies,
            "webcam_image_path": str(saved_jpg),
        }
        business_info = {
            "name": business_name,
            "address": business_address,
        }
        return PdfEngine.generate_invoice_pdf(
            billing=billing,
            business_info=business_info,
            output_path=pdf_path,
        )

    saved_pdf = await asyncio.to_thread(_save_pdf)
    log.info(f"PDF factura guardado en escritorio: {saved_pdf}")
