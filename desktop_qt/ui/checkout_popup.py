"""Popup de cobro forzado nativo Qt (reemplaza Tkinter).

Recibe `user_id` del usuario logueado para que el PATCH /payment registre
quién cobró (trazabilidad PaymentAlteration).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QMessageBox,
)
from PySide6.QtCore import Qt

from desktop_qt.api.client import get_client, APIError


class CheckoutPopup(QDialog):
    """Popup modal de cobro forzado — Qt nativo."""

    def __init__(self, data: dict, client, parent=None, user_id: int | None = None):
        """
        Args:
            data: dict con device_name, files_count, total_gb,
                  suggested_price, inserted_id (del evento WS).
            client: ApiClient para hacer los requests HTTP.
            parent: widget padre.
            user_id: ID del usuario logueado (para trazabilidad del cobro).
                     Si es None, intenta leerse del singleton ApiClient.
        """
        super().__init__(parent)
        self._data = data
        self._client = client

        # Resolver user_id: parámetro explícito > ApiClient.user_id > None
        if user_id is None:
            user_id = getattr(client, "user_id", None)
        # Si sigue sin resolverse, intentar desde el singleton (por si `client`
        # no es el singleton sino otra instancia).
        if user_id is None:
            user_id = get_client().user_id
        self._user_id = user_id

        self.setWindowTitle("COBRO PENDIENTE — LBAMonitor")
        self.setFixedSize(500, 420)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Dialog)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(12)

        # Header
        header = QLabel("⚠ USB EXTRAÍDA SIN FACTURAR")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #EF4444;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Info
        info_frame = QFrame()
        info_layout = QVBoxLayout(info_frame)

        device = self._data.get("device_name") or self._data.get("name") or "USB"
        files = self._data.get("files_count", 0)
        gb = self._data.get("total_gb", 0.0) or self._data.get("gb_copied", 0.0)
        suggested = self._data.get("suggested_price", 0.0) or self._data.get("payment", 0.0)
        self._inserted_id = self._data.get("inserted_id") or self._data.get("id") or 0

        for line in [f"Dispositivo: {device}",
                     f"Archivos copiados: {files}",
                     f"GB copiados: {gb:.2f} GB",
                     f"Precio sugerido: {suggested:.2f} CUP"]:
            lbl = QLabel(line)
            lbl.setStyleSheet("font-size: 14px;")
            info_layout.addWidget(lbl)

        layout.addWidget(info_frame)

        # Input precio
        price_label = QLabel("PRECIO COBRADO:")
        price_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(price_label)

        self.price_input = QLineEdit(str(int(suggested)) if suggested > 0 else "0")
        self.price_input.setStyleSheet(
            "font-size: 20px; font-weight: bold; text-align: center; padding: 8px;"
        )
        self.price_input.setAlignment(Qt.AlignCenter)
        self.price_input.returnPressed.connect(self._pay)
        layout.addWidget(self.price_input)

        # Botones rápidos
        quick_layout = QHBoxLayout()
        for val in [25, 50, 100, 200, 500]:
            btn = QPushButton(f"{val}")
            btn.clicked.connect(lambda _, v=val: self.price_input.setText(str(v)))
            quick_layout.addWidget(btn)
        layout.addLayout(quick_layout)

        # Botón cobrar
        pay_btn = QPushButton("✓ COBRAR Y EXPULSAR")
        pay_btn.setObjectName("success")
        pay_btn.clicked.connect(self._pay)
        layout.addWidget(pay_btn)

    def _pay(self):
        try:
            price = int(float(self.price_input.text().replace(",", ".").strip()))
        except ValueError:
            QMessageBox.warning(self, "Error", "El precio debe ser un número entero.")
            return

        if self._user_id is None:
            QMessageBox.warning(
                self, "Error",
                "No se pudo determinar el usuario logueado.\n"
                "Reinicie sesión e inténtelo de nuevo.",
            )
            return

        if not self._inserted_id:
            QMessageBox.warning(self, "Error", "No se pudo determinar el ID de la inserción.")
            return

        # 1) PATCH /api/inserted-drives/{id}/payment con user_id real
        try:
            self._client.patch(
                f"/api/inserted-drives/{self._inserted_id}/payment",
                {"payment": price, "user_id": self._user_id},
            )
        except APIError as e:
            QMessageBox.warning(
                self, "Error",
                f"No se pudo registrar el cobro (HTTP {e.status}):\n{e.detail}",
            )
            return
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo registrar: {e}")
            return

        # 2) Eject (best-effort: el backend v4.3 no expone /eject todavía,
        #    así que envolvemos en try/except y lo ignoramos silenciosamente).
        try:
            self._client.post(f"/api/inserted-drives/{self._inserted_id}/eject")
        except Exception:
            # Endpoint no implementado todavía — no es fatal.
            pass

        self.accept()
