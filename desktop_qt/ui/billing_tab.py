"""Tab Billing — Cobros del operador.

Funcionalidades:
- Tabla de USBs insertados activos (con botón "Cobrar" por cada uno)
- Diálogo de cobro con info del dispositivo, archivos copiados, cálculo
  automático de precio sugerido, comentario, selector de cliente VIP,
  botón "Tomar foto" (webcam) y "Ver historial" del dispositivo.
- Tabla de cobros del día (fecha, dispositivo, monto, operador)
- Resumen del día: total cobrado, número de transacciones, GB totales
- Botón "Exportar reporte del día a PDF"

Endpoints usados:
- GET  /api/inserted-drives/active
- GET  /api/inserted-drives/{id}/copies
- GET  /api/inserted-drives/{id}/payment-alterations
- PATCH /api/inserted-drives/{id}/payment
- POST /api/billings/calculate
- GET  /api/billings?from_date=...&to_date=...
- GET  /api/clients (para selector VIP)
- GET  /api/vip (para saber qué dispositivos son VIP)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_qt.api.client import APIError, get_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_bytes(b: Optional[float]) -> str:
    if not b:
        return "—"
    b = float(b)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(b) < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"


def _today_iso_range() -> tuple[str, str]:
    """Devuelve (from_date, to_date) ISO para el día actual (UTC)."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


# ---------------------------------------------------------------------------
# Diálogo de cobro
# ---------------------------------------------------------------------------

class PaymentDialog(QDialog):
    """Diálogo de cobro individual para un dispositivo insertado."""

    def __init__(self, drive: dict, client, parent=None):
        super().__init__(parent)
        self._drive = drive
        self._client = client
        self._copies: list[dict] = []
        self._vips: dict[int, dict] = {}  # device_id → vip info
        self._clients: list[dict] = []
        self._suggested: float = 0.0
        self._photo_path: Optional[str] = None
        self.setWindowTitle(f"Cobro — USB #{drive.get('id', '?')}")
        self.setMinimumSize(640, 620)
        self._setup_ui()
        self._load_data()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # --- Info del dispositivo ---
        info_frame = QFrame()
        info_frame.setObjectName("card")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(14, 12, 14, 12)

        d = self._drive
        title = QLabel(f"USB #{d.get('id', '?')} — {d.get('name') or d.get('drive_letter', '')}")
        title.setObjectName("page_title")
        info_layout.addWidget(title)

        details = (
            f"Modelo: {d.get('model', '—')}  |  "
            f"Serial: {d.get('serial_number') or d.get('serial', '—')}  |  "
            f"Capacidad: {_fmt_bytes(d.get('space_bytes'))}  |  "
            f"Libre: {_fmt_bytes(d.get('available_space_bytes'))}"
        )
        info_layout.addWidget(QLabel(details))
        layout.addWidget(info_frame)

        # --- Lista de archivos copiados ---
        layout.addWidget(QLabel("Archivos copiados:"))
        self.copies_table = QTableWidget(0, 4)
        self.copies_table.setHorizontalHeaderLabels(["Archivo", "Ext", "Categoría", "Tamaño"])
        self.copies_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.copies_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.copies_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.copies_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.copies_table.setAlternatingRowColors(True)
        self.copies_table.setMinimumHeight(160)
        layout.addWidget(self.copies_table)

        # --- Cálculo sugerido + input ---
        form_frame = QFrame()
        form_layout = QFormLayout(form_frame)
        form_layout.setContentsMargins(0, 8, 0, 8)

        self.suggested_label = QLabel("Calculando…")
        form_layout.addRow("Precio sugerido:", self.suggested_label)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0, 999999)
        self.amount_input.setDecimals(2)
        self.amount_input.setSuffix(" CUP")
        self.amount_input.setValue(0)
        form_layout.addRow("Monto a cobrar:", self.amount_input)

        self.vip_combo = QComboBox()
        self.vip_combo.addItem("(sin cliente VIP)", None)
        form_layout.addRow("Cliente VIP:", self.vip_combo)

        self.comment_edit = QLineEdit()
        self.comment_edit.setPlaceholderText("Comentario opcional…")
        form_layout.addRow("Comentario:", self.comment_edit)

        layout.addWidget(form_frame)

        # --- Botones de acción ---
        btn_row = QHBoxLayout()

        photo_btn = QPushButton("Tomar foto")
        photo_btn.clicked.connect(self._take_photo)
        btn_row.addWidget(photo_btn)

        history_btn = QPushButton("Ver historial")
        history_btn.clicked.connect(self._view_history)
        btn_row.addWidget(history_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        confirm_btn = QPushButton("Confirmar cobro")
        confirm_btn.setObjectName("success")
        confirm_btn.clicked.connect(self._confirm)
        btn_row.addWidget(confirm_btn)

        layout.addLayout(btn_row)

    # -------------------------------------------------------------- Datos
    def _load_data(self):
        """Carga copies + VIPs + clientes y calcula el precio sugerido."""
        drive_id = self._drive.get("id")
        if not drive_id:
            return

        # 1. Copies
        try:
            self._copies = self._client.get(f"/api/inserted-drives/{drive_id}/copies") or []
        except Exception:
            self._copies = []
        self._populate_copies()

        # 2. VIPs y clients (paralelo via dos GET)
        try:
            self._clients = self._client.get("/api/clients", {"page": 1, "page_size": 500}) \
                .get("items", []) if isinstance(
                self._client.get("/api/clients", {"page": 1, "page_size": 500}), dict
            ) else []
        except Exception:
            self._clients = []

        try:
            vips = self._client.get("/api/vip") or []
            self._vips = {v.get("device_id"): v for v in vips if v.get("device_id")}
        except Exception:
            self._vips = {}

        # Llenar combo VIP: combinar clients conocidos + VIPs por device_id
        for c in self._clients:
            label = c.get("name") or f"Cliente #{c.get('id')}"
            if c.get("phone"):
                label += f"  ·  {c.get('phone')}"
            self.vip_combo.addItem(label, c)

        # 3. Cálculo sugerido vía /api/billings/calculate
        gb_copied = 0.0
        files_copied = len(self._copies)
        total_bytes = sum((c.get("size_bytes") or 0) for c in self._copies)
        if total_bytes > 0:
            gb_copied = total_bytes / (1024 ** 3)

        vip_type = "none"
        device_id = self._drive.get("device_id") or self._drive.get("id")
        vip_info = self._vips.get(device_id) if device_id else None
        if vip_info:
            vip_type = vip_info.get("vip_type", "none")

        try:
            params = {
                "gb_copied": gb_copied,
                "files_copied": files_copied,
                "vip_type": vip_type,
            }
            calc = self._client.post("/api/billings/calculate", params=params) or {}
            self._suggested = float(calc.get("suggested_price", 0) or 0)
            self.suggested_label.setText(
                f"{self._suggested:.2f} CUP"
                f"  (modo: {calc.get('pricing_mode', '?')})"
            )
            self.amount_input.setValue(self._suggested)
        except Exception as e:
            self.suggested_label.setText(f"Error cálculo: {e}")
            # Fallback: estimación tosca 25 CUP/GB
            self._suggested = max(5.0, gb_copied * 25.0)
            self.amount_input.setValue(self._suggested)

    def _populate_copies(self):
        self.copies_table.setRowCount(len(self._copies))
        for i, c in enumerate(self._copies):
            self.copies_table.setItem(i, 0, QTableWidgetItem(c.get("file_name", "")))
            self.copies_table.setItem(i, 1, QTableWidgetItem(c.get("extension", "")))
            self.copies_table.setItem(i, 2, QTableWidgetItem(c.get("category", "—")))
            self.copies_table.setItem(i, 3, QTableWidgetItem(_fmt_bytes(c.get("size_bytes"))))

    # -------------------------------------------------------------- Acciones
    def _take_photo(self):
        """Toma una foto con la webcam (best-effort, opcional)."""
        try:
            # OpenCV es opcional — si no está disponible, no fallar.
            import cv2  # type: ignore
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                QMessageBox.warning(self, "Webcam", "No se pudo abrir la cámara.")
                return
            ret, frame = cap.read()
            cap.release()
            if not ret:
                QMessageBox.warning(self, "Webcam", "No se pudo capturar imagen.")
                return
            import os
            import tempfile
            fd, path = tempfile.mkstemp(prefix="lbam_photo_", suffix=".png")
            os.close(fd)
            cv2.imwrite(path, frame)
            self._photo_path = path
            QMessageBox.information(self, "Webcam", f"Foto guardada:\n{path}")
        except ImportError:
            QMessageBox.information(
                self, "Webcam",
                "OpenCV no está instalado. La foto es opcional y se puede omitir.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Webcam", f"Error: {e}")

    def _view_history(self):
        """Muestra historial de alteraciones de pago del dispositivo."""
        drive_id = self._drive.get("id")
        if not drive_id:
            return
        try:
            alterations = self._client.get(
                f"/api/inserted-drives/{drive_id}/payment-alterations"
            ) or []
        except Exception as e:
            QMessageBox.warning(self, "Historial", f"Error: {e}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Historial — USB #{drive_id}")
        dlg.setMinimumSize(560, 360)
        v = QVBoxLayout(dlg)
        table = QTableWidget(len(alterations), 4)
        table.setHorizontalHeaderLabels(["Fecha", "Pago anterior", "Pago nuevo", "Usuario"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setAlternatingRowColors(True)
        for i, a in enumerate(alterations):
            table.setItem(i, 0, QTableWidgetItem(str(a.get("alteration_date_time", ""))[:19]))
            table.setItem(i, 1, QTableWidgetItem(str(a.get("previous_payment", "—"))))
            table.setItem(i, 2, QTableWidgetItem(str(a.get("new_payment", "—"))))
            table.setItem(i, 3, QTableWidgetItem(str(a.get("user_id", "—"))))
        v.addWidget(table)
        dlg.exec()

    def _confirm(self):
        amount = self.amount_input.value()
        if amount < 0:
            QMessageBox.warning(self, "Error", "El monto no puede ser negativo.")
            return
        drive_id = self._drive.get("id")
        if not drive_id:
            QMessageBox.warning(self, "Error", "ID de dispositivo inválido.")
            return

        try:
            user_id = getattr(self._client, "user_id", None)
            payload = {"payment": int(round(amount))}
            if user_id is not None:
                payload["user_id"] = user_id
            comment = self.comment_edit.text().strip()
            if comment:
                payload["reason"] = comment
            self._client.patch(f"/api/inserted-drives/{drive_id}/payment", payload)

            # Guardar comentario en el drive (campo comment)
            if comment:
                try:
                    self._client.patch(
                        f"/api/inserted-drives/{drive_id}", {"comment": comment}
                    )
                except Exception:
                    pass

            QMessageBox.information(self, "Cobro", f"Cobro de {amount:.2f} CUP registrado ✓")
            self.accept()
        except APIError as e:
            QMessageBox.warning(self, "Error", f"HTTP {e.status}: {e.detail}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo registrar: {e}")


# ---------------------------------------------------------------------------
# Tab principal
# ---------------------------------------------------------------------------

class BillingTab(QWidget):
    """Tab de cobros: USBs activos + cobros del día + resumen."""

    def __init__(self, signals):
        super().__init__()
        self._client = get_client()
        self.signals = signals
        self._setup_ui()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # --- Header con botón refresh ---
        header_row = QHBoxLayout()
        title = QLabel("Cobros")
        title.setObjectName("page_title")
        header_row.addWidget(title)
        header_row.addStretch()
        refresh_btn = QPushButton("Refrescar")
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)
        export_btn = QPushButton("Exportar PDF del día")
        export_btn.setObjectName("primary")
        export_btn.clicked.connect(self._export_pdf)
        header_row.addWidget(export_btn)
        layout.addLayout(header_row)

        # --- Resumen del día ---
        summary_grid = QGridLayout()
        summary_grid.setSpacing(10)
        self.lbl_total = self._make_kpi_card(summary_grid, 0, 0, "Total cobrado hoy", "0.00 CUP")
        self.lbl_count = self._make_kpi_card(summary_grid, 0, 1, "Transacciones hoy", "0")
        self.lbl_gb = self._make_kpi_card(summary_grid, 0, 2, "GB totales hoy", "0.0")
        layout.addLayout(summary_grid)

        # --- Loading ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(4)
        layout.addWidget(self.progress)

        # --- Tabla USBs activos ---
        section_active = QLabel("USBs insertados activos")
        section_active.setObjectName("section_title")
        layout.addWidget(section_active)

        self.active_table = QTableWidget(0, 6)
        self.active_table.setHorizontalHeaderLabels([
            "ID", "Dispositivo", "Modelo", "Capacidad", "Libre", "Acciones",
        ])
        self.active_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.active_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.active_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.active_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.active_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.active_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.active_table.setAlternatingRowColors(True)
        layout.addWidget(self.active_table)

        # --- Tabla cobros del día ---
        section_today = QLabel("Cobros del día")
        section_today.setObjectName("section_title")
        layout.addWidget(section_today)

        self.today_table = QTableWidget(0, 5)
        self.today_table.setHorizontalHeaderLabels([
            "Fecha", "Dispositivo", "Monto", "Operador", "Comentario",
        ])
        self.today_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.today_table.setAlternatingRowColors(True)
        layout.addWidget(self.today_table)

    def _make_kpi_card(self, grid: QGridLayout, row: int, col: int, title: str, default: str) -> QLabel:
        card = QFrame()
        card.setObjectName("card")
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 12)
        t = QLabel(title)
        t.setObjectName("kpi_label")
        v.addWidget(t)
        value = QLabel(default)
        value.setObjectName("kpi_value")
        v.addWidget(value)
        grid.addWidget(card, row, col)
        return value

    # -------------------------------------------------------------- Refresh
    def refresh(self):
        self.progress.setVisible(True)
        try:
            self._load_active()
            self._load_today_billings()
            self._load_summary()
        finally:
            self.progress.setVisible(False)

    def _load_active(self):
        try:
            drives = self._client.get("/api/inserted-drives/active") or []
        except Exception as e:
            self._show_error(f"Error cargando USBs activos: {e}")
            return

        self.active_table.setRowCount(len(drives))
        for i, d in enumerate(drives):
            self.active_table.setItem(i, 0, QTableWidgetItem(str(d.get("id", ""))))
            self.active_table.setItem(
                i, 1, QTableWidgetItem(d.get("name") or d.get("drive_letter") or "")
            )
            self.active_table.setItem(i, 2, QTableWidgetItem(d.get("model") or "—"))
            self.active_table.setItem(i, 3, QTableWidgetItem(_fmt_bytes(d.get("space_bytes"))))
            self.active_table.setItem(i, 4, QTableWidgetItem(_fmt_bytes(d.get("available_space_bytes"))))

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(4)

            pay_btn = QPushButton("Cobrar")
            pay_btn.setObjectName("primary")
            pay_btn.clicked.connect(lambda _, dd=d: self._open_payment_dialog(dd))
            actions_layout.addWidget(pay_btn)

            comment_btn = QPushButton("Comentario")
            comment_btn.clicked.connect(lambda _, dd=d: self._quick_comment(dd))
            actions_layout.addWidget(comment_btn)

            self.active_table.setCellWidget(i, 5, actions)

    def _load_today_billings(self):
        from_str, to_str = _today_iso_range()
        try:
            data = self._client.get(
                "/api/billings",
                {"page": 1, "page_size": 200, "from_date": from_str, "to_date": to_str},
            ) or {}
            items = data.get("items", []) if isinstance(data, dict) else data
        except Exception as e:
            self._show_error(f"Error cargando cobros del día: {e}")
            return

        self.today_table.setRowCount(len(items))
        for i, b in enumerate(items):
            self.today_table.setItem(i, 0, QTableWidgetItem(str(b.get("created_at", ""))[:19]))
            self.today_table.setItem(i, 1, QTableWidgetItem(f"#{b.get('device_id', '—')}"))
            self.today_table.setItem(
                i, 2, QTableWidgetItem(f"{float(b.get('charged') or 0):.2f} CUP")
            )
            self.today_table.setItem(i, 3, QTableWidgetItem(b.get("created_by") or "—"))
            self.today_table.setItem(i, 4, QTableWidgetItem(b.get("observations") or ""))

    def _load_summary(self):
        """Total cobrado, transacciones y GB hoy vía KPIs del backend."""
        try:
            kpis = self._client.get("/api/statistics/kpis/today") or {}
            self.lbl_total.setText(f"{float(kpis.get('revenue', 0) or 0):.2f} CUP")
            self.lbl_count.setText(str(kpis.get("transactions", 0) or 0))
            self.lbl_gb.setText(f"{float(kpis.get('gb_copied', 0) or 0):.2f}")
        except Exception as e:
            self._show_error(f"Error cargando resumen: {e}")

    # -------------------------------------------------------------- Acciones
    def _open_payment_dialog(self, drive: dict):
        dlg = PaymentDialog(drive, self._client, self)
        dlg.exec()
        self.refresh()

    def _quick_comment(self, drive: dict):
        drive_id = drive.get("id")
        if not drive_id:
            return
        text, ok = QInputDialog.getText(self, "Comentario", f"USB #{drive_id}:")
        if ok and text:
            try:
                self._client.patch(f"/api/inserted-drives/{drive_id}", {"comment": text})
                self.refresh()
            except APIError as e:
                QMessageBox.warning(self, "Error", f"HTTP {e.status}: {e.detail}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"{e}")

    def _export_pdf(self):
        """Exporta un reporte PDF simple del día usando reportlab si está disponible."""
        try:
            from reportlab.lib import colors  # type: ignore
            from reportlab.lib.pagesizes import A4  # type: ignore
            from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
            from reportlab.platypus import (
                SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
            )  # type: ignore
        except ImportError:
            QMessageBox.warning(
                self, "PDF",
                "reportlab no está instalado.\nInstale con: pip install reportlab",
            )
            return

        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte PDF", f"reporte_cobros_{datetime.now().strftime('%Y%m%d')}.pdf",
            "PDF (*.pdf)",
        )
        if not path:
            return

        try:
            doc = SimpleDocTemplate(path, pagesize=A4)
            styles = getSampleStyleSheet()
            elems = [
                Paragraph("Reporte de cobros del día", styles["Title"]),
                Paragraph(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]),
                Spacer(1, 12),
            ]

            data_rows = [["Fecha", "Dispositivo", "Monto", "Operador", "Comentario"]]
            for r in range(self.today_table.rowCount()):
                row = []
                for c in range(self.today_table.columnCount()):
                    item = self.today_table.item(r, c)
                    row.append(item.text() if item else "")
                data_rows.append(row)

            tbl = Table(data_rows)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0078D4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]))
            elems.append(tbl)
            elems.append(Spacer(1, 16))
            elems.append(Paragraph(
                f"Total cobrado: <b>{self.lbl_total.text()}</b>", styles["Normal"]
            ))
            elems.append(Paragraph(
                f"Transacciones: <b>{self.lbl_count.text()}</b>", styles["Normal"]
            ))
            elems.append(Paragraph(
                f"GB totales: <b>{self.lbl_gb.text()}</b>", styles["Normal"]
            ))

            doc.build(elems)
            QMessageBox.information(self, "PDF", f"Reporte guardado en:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "PDF", f"Error generando PDF: {e}")

    def _show_error(self, msg: str):
        QMessageBox.warning(self, "Error", msg)
