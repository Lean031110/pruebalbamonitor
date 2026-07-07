"""Tab USB — USBs activos + historial + cobro."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QInputDialog, QMessageBox, QColorDialog,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor

from desktop_qt.api.client import get_client


class USBTab(QWidget):
    def __init__(self, signals):
        super().__init__()
        self._client = get_client()
        self.signals = signals
        self._setup_ui()

        # Conectar señales
        self.signals.drive_inserted.connect(self._on_drive_inserted)
        self.signals.eject_pending.connect(self._on_eject_pending)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("USBs Activos")
        title.setObjectName("page_title")
        layout.addWidget(title)

        # Tabla de USBs activos
        self.active_table = QTableWidget(0, 7)
        self.active_table.setHorizontalHeaderLabels([
            "ID", "Unidad", "Volumen", "Modelo", "Capacidad", "Libre", "Acciones"
        ])
        self.active_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.active_table.setAlternatingRowColors(True)
        layout.addWidget(self.active_table)

        # Historial
        hist_title = QLabel("Historial Reciente")
        hist_title.setObjectName("section_title")
        layout.addWidget(hist_title)

        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels([
            "Fecha", "Unidad", "Volumen", "GB Copiados", "Pago", "Comentario"
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.setAlternatingRowColors(True)
        layout.addWidget(self.history_table)

    def refresh(self):
        self._load_active()
        self._load_history()

    def _load_active(self):
        try:
            drives = self._client.get("/api/inserted-drives/active")
            self.active_table.setRowCount(len(drives))
            for i, d in enumerate(drives):
                self.active_table.setItem(i, 0, QTableWidgetItem(str(d.get("id", ""))))
                self.active_table.setItem(i, 1, QTableWidgetItem(d.get("name", "")))
                self.active_table.setItem(i, 2, QTableWidgetItem(d.get("volume_label", "")))
                self.active_table.setItem(i, 3, QTableWidgetItem(d.get("model", "")))
                self.active_table.setItem(i, 4, QTableWidgetItem(self._fmt_bytes(d.get("space_bytes"))))
                self.active_table.setItem(i, 5, QTableWidgetItem(self._fmt_bytes(d.get("available_space_bytes"))))

                # Botones de acción
                actions = QWidget()
                actions_layout = QHBoxLayout(actions)
                actions_layout.setContentsMargins(4, 4, 4, 4)

                pay_btn = QPushButton("Cobrar")
                pay_btn.clicked.connect(lambda _, did=d["id"]: self._show_payment_dialog(did))
                actions_layout.addWidget(pay_btn)

                comment_btn = QPushButton("Comentario")
                comment_btn.clicked.connect(lambda _, did=d["id"]: self._show_comment_dialog(did))
                actions_layout.addWidget(comment_btn)

                color_btn = QPushButton("Color")
                color_btn.clicked.connect(lambda _, did=d["id"]: self._show_color_dialog(did))
                actions_layout.addWidget(color_btn)

                self.active_table.setCellWidget(i, 6, actions)
        except Exception:
            pass

    def _load_history(self):
        try:
            data = self._client.get("/api/inserted-drives", {"page": 1, "page_size": 20})
            drives = data.get("items", [])
            self.history_table.setRowCount(len(drives))
            for i, d in enumerate(drives):
                self.history_table.setItem(i, 0, QTableWidgetItem(d.get("insertion_date_time", "")[:19]))
                self.history_table.setItem(i, 1, QTableWidgetItem(d.get("name", "")))
                self.history_table.setItem(i, 2, QTableWidgetItem(d.get("volume_label", "")))
                # GB copiados - calcular desde space_bytes
                self.history_table.setItem(i, 3, QTableWidgetItem("—"))
                self.history_table.setItem(i, 4, QTableWidgetItem(f"{d.get('payment', 0) or 0} CUP" if d.get("payment") else "—"))
                self.history_table.setItem(i, 5, QTableWidgetItem(d.get("comment", "")))
        except Exception:
            pass

    def _fmt_bytes(self, b) -> str:
        if not b:
            return "—"
        for u in ["B", "KB", "MB", "GB", "TB"]:
            if abs(b) < 1024:
                return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} PB"

    def _show_payment_dialog(self, drive_id: int):
        text, ok = QInputDialog.getInt(self, "Cobro", f"Cobro para USB #{drive_id}:", value=50, min=0, max=99999)
        if ok:
            try:
                # Incluir user_id para trazabilidad (PaymentAlteration)
                user_id = getattr(self._client, "user_id", None)
                payload = {"payment": text}
                if user_id is not None:
                    payload["user_id"] = user_id
                self._client.patch(f"/api/inserted-drives/{drive_id}/payment", payload)
                QMessageBox.information(self, "OK", f"Cobro de {text} CUP registrado.")
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudo registrar: {e}")

    def _show_comment_dialog(self, drive_id: int):
        text, ok = QInputDialog.getText(self, "Comentario", f"Comentario para USB #{drive_id}:")
        if ok and text:
            try:
                self._client.patch(f"/api/inserted-drives/{drive_id}", {"comment": text})
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudo guardar: {e}")

    def _show_color_dialog(self, drive_id: int):
        color = QColorDialog.getColor(QColor("#FF0000"), self, "Color de fila")
        if color.isValid():
            try:
                # row_color es int, convertir
                self._client.patch(f"/api/inserted-drives/{drive_id}", {"row_color": color.rgb()})
                self.refresh()
            except Exception:
                pass

    def _on_drive_inserted(self, data: dict):
        """Señal WebSocket: USB insertada."""
        self.refresh()

    def _on_eject_pending(self, data: dict):
        """Señal WebSocket: USB extraída sin cobrar → popup."""
        from desktop_qt.ui.checkout_popup import CheckoutPopup
        # Pasar el user_id del usuario logueado para trazabilidad del cobro.
        popup = CheckoutPopup(
            data, self._client, self,
            user_id=getattr(self._client, "user_id", None),
        )
        popup.exec()
        self.refresh()
