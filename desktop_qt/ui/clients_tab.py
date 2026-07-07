"""Tab Clients — Gestión de clientes, VIP y membresías.

Funcionalidades:
- Tabla de clientes (nombre/alias, dispositivo, visitas, total gastado,
  GB totales, puntos, nivel membresía)
- Filtro de búsqueda por nombre
- Botones: Nuevo cliente / Editar cliente / Marcar como VIP / Ver detalle
- Sección de niveles de membresía (bronce/plata/oro/platino/diamante)

Endpoints usados:
- GET    /api/clients?page=&page_size=&query=
- GET    /api/clients/{id}
- PATCH  /api/clients/{id}     (name, phone, observations, photo_path)
- GET    /api/vip
- POST   /api/vip              {device_id, vip_type, discount_percent, reason}
- DELETE /api/vip/{device_id}
- GET    /api/memberships/levels
- PATCH  /api/memberships/levels/{tier}
- POST   /api/memberships/recompute
- GET    /api/inserted-drives?device_id=  (para historial del cliente)
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop_qt.api.client import APIError, get_client


# ---------------------------------------------------------------------------
# Diálogo crear/editar cliente
# ---------------------------------------------------------------------------

class ClientEditDialog(QDialog):
    """Diálogo para crear o editar un cliente."""

    def __init__(self, parent=None, client: Optional[dict] = None):
        super().__init__(parent)
        self._client_data = client
        self.setWindowTitle("Editar cliente" if client else "Nuevo cliente")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.observations_edit = QTextEdit()
        self.observations_edit.setMaximumHeight(80)
        self.photo_edit = QLineEdit()
        self.photo_edit.setPlaceholderText("Ruta a foto (opcional)")

        if self._client_data:
            self.name_edit.setText(self._client_data.get("name") or "")
            self.phone_edit.setText(self._client_data.get("phone") or "")
            self.observations_edit.setPlainText(self._client_data.get("observations") or "")
            self.photo_edit.setText(self._client_data.get("photo_path") or "")

        form.addRow("Nombre / alias:", self.name_edit)
        form.addRow("Teléfono:", self.phone_edit)
        form.addRow("Observaciones:", self.observations_edit)
        form.addRow("Foto:", self.photo_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip() or None,
            "phone": self.phone_edit.text().strip() or None,
            "observations": self.observations_edit.toPlainText().strip() or None,
            "photo_path": self.photo_edit.text().strip() or None,
        }


# ---------------------------------------------------------------------------
# Diálogo para marcar/desmarcar VIP
# ---------------------------------------------------------------------------

class VIPDialog(QDialog):
    """Diálogo para marcar un dispositivo como VIP."""

    VIP_TYPES = [
        ("none", "Sin VIP"),
        ("vip", "VIP"),
        ("blocked", "Bloqueado"),
        ("never_pays", "Nunca paga"),
        ("free", "Gratis"),
        ("discount", "Descuento"),
        ("employee", "Empleado"),
        ("business", "Negocio"),
    ]

    def __init__(self, parent=None, device_id: Optional[int] = None,
                 current: Optional[dict] = None):
        super().__init__(parent)
        self._device_id = device_id
        self.setWindowTitle("Marcar como VIP")
        self.setMinimumWidth(380)
        self._setup_ui(current)

    def _setup_ui(self, current: Optional[dict]):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.type_combo = QComboBox()
        for v, label in self.VIP_TYPES:
            self.type_combo.addItem(label, v)
        if current:
            cur_type = current.get("vip_type", "none")
            for i in range(self.type_combo.count()):
                if self.type_combo.itemData(i) == cur_type:
                    self.type_combo.setCurrentIndex(i)
                    break
        form.addRow("Tipo VIP:", self.type_combo)

        self.discount_spin = QDoubleSpinBox()
        self.discount_spin.setRange(0, 100)
        self.discount_spin.setDecimals(2)
        self.discount_spin.setSuffix(" %")
        if current and current.get("discount_percent") is not None:
            self.discount_spin.setValue(float(current["discount_percent"]))
        form.addRow("Descuento:", self.discount_spin)

        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("Motivo (opcional)")
        if current and current.get("reason"):
            self.reason_edit.setText(current["reason"])
        form.addRow("Motivo:", self.reason_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        return {
            "device_id": self._device_id,
            "vip_type": self.type_combo.currentData(),
            "discount_percent": self.discount_spin.value(),
            "reason": self.reason_edit.text().strip() or None,
        }


# ---------------------------------------------------------------------------
# Diálogo de detalle (historial completo)
# ---------------------------------------------------------------------------

class ClientDetailDialog(QDialog):
    """Muestra el detalle completo de un cliente: KPIs + historial."""

    def __init__(self, client: dict, api_client, parent=None):
        super().__init__(parent)
        self._client = client
        self._api = api_client
        self.setWindowTitle(f"Detalle — {client.get('name') or f'Cliente #{client.get('id')}'}")
        self.setMinimumSize(720, 540)
        self._setup_ui()
        self._load_history()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # KPIs principales
        kpi_frame = QFrame()
        kpi_frame.setObjectName("card")
        kpi_layout = QGridLayout(kpi_frame)
        kpi_layout.setContentsMargins(14, 12, 14, 12)
        c = self._client

        def add_kpi(r, col, label, value):
            l = QLabel(label)
            l.setObjectName("kpi_label")
            v = QLabel(str(value))
            v.setObjectName("kpi_value")
            kpi_layout.addWidget(l, r, col)
            kpi_layout.addWidget(v, r + 1, col)

        add_kpi(0, 0, "Visitas", c.get("visit_count", 0))
        add_kpi(0, 1, "Total gastado", f"{float(c.get('total_spent') or 0):.2f} CUP")
        add_kpi(0, 2, "GB copiados", f"{float(c.get('total_gb_copied') or 0):.2f}")
        add_kpi(0, 3, "Puntos", c.get("points", 0))
        add_kpi(0, 4, "Tier", c.get("tier", "bronce"))

        layout.addWidget(kpi_frame)

        # Fechas
        info = QLabel(
            f"Primera visita: {c.get('first_visit', '—')[:10]}  ·  "
            f"Última visita: {c.get('last_visit', '—')[:10]}  ·  "
            f"Tel: {c.get('phone') or '—'}"
        )
        info.setObjectName("kpi_label")
        layout.addWidget(info)

        # Historial
        layout.addWidget(QLabel("Historial de sesiones:"))
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels([
            "Fecha", "Dispositivo", "Monto", "Comentario", "Usuario",
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.setAlternatingRowColors(True)
        layout.addWidget(self.history_table)

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _load_history(self):
        device_id = self._client.get("device_id")
        if not device_id:
            return
        # El endpoint /api/inserted-drives no soporta device_id directo;
        # cargamos una página amplia y filtramos client-side por el campo
        # `device_id` que sí viene en cada InsertedDrive.
        try:
            data = self._api.get(
                "/api/inserted-drives",
                {"page": 1, "page_size": 200},
            ) or {}
            all_items = data.get("items", []) if isinstance(data, dict) else []
            items = [
                d for d in all_items
                if d.get("device_id") == device_id
            ]
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar historial: {e}")
            return

        self.history_table.setRowCount(len(items))
        for i, d in enumerate(items):
            self.history_table.setItem(
                i, 0, QTableWidgetItem(str(d.get("insertion_date_time", ""))[:19])
            )
            self.history_table.setItem(i, 1, QTableWidgetItem(d.get("name") or "—"))
            self.history_table.setItem(
                i, 2,
                QTableWidgetItem(f"{d.get('payment', 0) or 0} CUP" if d.get("payment") else "—"),
            )
            self.history_table.setItem(i, 3, QTableWidgetItem(d.get("comment") or ""))
            self.history_table.setItem(i, 4, QTableWidgetItem(str(d.get("user_id") or "—")))


# ---------------------------------------------------------------------------
# Tab principal
# ---------------------------------------------------------------------------

class ClientsTab(QWidget):
    """Gestión de clientes, VIP y membresías."""

    def __init__(self, signals):
        super().__init__()
        self._client = get_client()
        self.signals = signals
        self._vips: dict[int, dict] = {}  # device_id → vip info
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Clientes")
        title.setObjectName("page_title")
        header_row.addWidget(title)
        header_row.addStretch()
        refresh_btn = QPushButton("Refrescar")
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)
        recompute_btn = QPushButton("Recomputar tiers")
        recompute_btn.clicked.connect(self._recompute_tiers)
        header_row.addWidget(recompute_btn)
        layout.addLayout(header_row)

        # Search + actions row
        actions_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar por nombre…")
        self.search_edit.textChanged.connect(self._on_search_changed)
        actions_row.addWidget(self.search_edit, 1)

        new_btn = QPushButton("Nuevo cliente")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self._new_client)
        actions_row.addWidget(new_btn)

        edit_btn = QPushButton("Editar")
        edit_btn.clicked.connect(self._edit_client)
        actions_row.addWidget(edit_btn)

        vip_btn = QPushButton("Marcar como VIP")
        vip_btn.clicked.connect(self._mark_vip)
        actions_row.addWidget(vip_btn)

        detail_btn = QPushButton("Ver detalle")
        detail_btn.clicked.connect(self._view_detail)
        actions_row.addWidget(detail_btn)

        layout.addLayout(actions_row)

        # Loading
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(4)
        layout.addWidget(self.progress)

        # Tabla de clientes
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Nombre", "Dispositivo", "Visitas", "Total gastado",
            "GB totales", "Puntos", "Tier",
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._view_detail)
        layout.addWidget(self.table)

        # Sección de niveles de membresía
        levels_title = QLabel("Niveles de membresía")
        levels_title.setObjectName("section_title")
        layout.addWidget(levels_title)

        self.levels_table = QTableWidget(0, 6)
        self.levels_table.setHorizontalHeaderLabels([
            "Tier", "Min. visitas", "Min. GB", "Min. gastado",
            "Descuento %", "Color",
        ])
        self.levels_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.levels_table.setAlternatingRowColors(True)
        layout.addWidget(self.levels_table)

    # -------------------------------------------------------------- Refresh
    def refresh(self):
        self.progress.setVisible(True)
        self._all_clients = None  # invalidar caché
        try:
            self._load_vips()
            self._load_clients()
            self._load_levels()
        finally:
            self.progress.setVisible(False)

    def _load_vips(self):
        try:
            vips = self._client.get("/api/vip") or []
            self._vips = {v.get("device_id"): v for v in vips if v.get("device_id")}
        except Exception:
            self._vips = {}

    def _load_clients(self):
        # El backend /api/clients NO soporta `query`. Cargamos todos (cacheados)
        # y filtramos client-side.
        if not hasattr(self, "_all_clients") or self._all_clients is None:
            params = {"page": 1, "page_size": 500}
            try:
                data = self._client.get("/api/clients", params) or {}
                self._all_clients = (
                    data.get("items", []) if isinstance(data, dict) else []
                )
            except APIError as e:
                QMessageBox.warning(self, "Error", f"HTTP {e.status}: {e.detail}")
                return
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudo cargar clientes: {e}")
                return

        items = list(self._all_clients)

        # Filtro client-side por nombre o teléfono
        q = self.search_edit.text().strip().lower()
        if q:
            items = [
                c for c in items
                if (c.get("name") or "").lower().find(q) >= 0
                or (c.get("phone") or "").lower().find(q) >= 0
            ]

        self.table.setRowCount(len(items))
        for i, c in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(str(c.get("id", ""))))
            name = c.get("name") or "(sin nombre)"
            vip_info = self._vips.get(c.get("device_id"))
            if vip_info:
                name += f"  [{vip_info.get('vip_type', 'vip').upper()}]"
            self.table.setItem(i, 1, QTableWidgetItem(name))
            self.table.setItem(i, 2, QTableWidgetItem(str(c.get("device_id", "—"))))
            self.table.setItem(i, 3, QTableWidgetItem(str(c.get("visit_count", 0))))
            self.table.setItem(
                i, 4,
                QTableWidgetItem(f"{float(c.get('total_spent') or 0):.2f} CUP"),
            )
            self.table.setItem(
                i, 5,
                QTableWidgetItem(f"{float(c.get('total_gb_copied') or 0):.2f}"),
            )
            self.table.setItem(i, 6, QTableWidgetItem(str(c.get("points", 0))))
            self.table.setItem(i, 7, QTableWidgetItem(c.get("tier", "bronce")))

    def _load_levels(self):
        try:
            levels = self._client.get("/api/memberships/levels") or []
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudieron cargar niveles: {e}")
            return

        self.levels_table.setRowCount(len(levels))
        for i, l in enumerate(levels):
            self.levels_table.setItem(i, 0, QTableWidgetItem(l.get("tier", "")))
            self.levels_table.setItem(i, 1, QTableWidgetItem(str(l.get("min_visits", 0))))
            self.levels_table.setItem(i, 2, QTableWidgetItem(str(l.get("min_gb", 0))))
            self.levels_table.setItem(i, 3, QTableWidgetItem(f"{float(l.get('min_spent') or 0):.2f}"))
            self.levels_table.setItem(
                i, 4,
                QTableWidgetItem(f"{float(l.get('discount_percent') or 0):.2f}"),
            )
            self.levels_table.setItem(i, 5, QTableWidgetItem(l.get("color") or "—"))

    # -------------------------------------------------------------- Acciones
    def _on_search_changed(self, _text: str):
        self._load_clients()

    def _selected_client(self) -> Optional[dict]:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Seleccionar", "Seleccione un cliente de la tabla.")
            return None
        client_id_item = self.table.item(row, 0)
        device_id_item = self.table.item(row, 2)
        if not client_id_item:
            return None
        try:
            client_id = int(client_id_item.text())
            device_id = int(device_id_item.text()) if device_id_item else None
        except ValueError:
            return None
        return {"id": client_id, "device_id": device_id, "_row": row}

    def _new_client(self):
        QMessageBox.information(
            self, "Nuevo cliente",
            "Los clientes se crean automáticamente cuando un dispositivo USB\n"
            "es insertado por primera vez.\n\n"
            "Para editar uno existente, seleccione y use 'Editar'.",
        )

    def _edit_client(self):
        sel = self._selected_client()
        if not sel:
            return
        try:
            full = self._client.get(f"/api/clients/{sel['id']}") or {}
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar cliente: {e}")
            return

        dlg = ClientEditDialog(self, client=full)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._client.patch(f"/api/clients/{sel['id']}", dlg.get_data())
            QMessageBox.information(self, "OK", "Cliente actualizado ✓")
            self.refresh()
        except APIError as e:
            QMessageBox.warning(self, "Error", f"HTTP {e.status}: {e.detail}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{e}")

    def _mark_vip(self):
        sel = self._selected_client()
        if not sel or not sel.get("device_id"):
            QMessageBox.warning(self, "Error", "El cliente no tiene dispositivo asociado.")
            return
        current = self._vips.get(sel["device_id"])
        dlg = VIPDialog(self, device_id=sel["device_id"], current=current)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            if data["vip_type"] == "none":
                self._client.delete(f"/api/vip/{sel['device_id']}")
                QMessageBox.information(self, "VIP", "VIP eliminado.")
            else:
                self._client.post("/api/vip", data)
                QMessageBox.information(self, "VIP", "VIP actualizado ✓")
            self.refresh()
        except APIError as e:
            QMessageBox.warning(self, "Error", f"HTTP {e.status}: {e.detail}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{e}")

    def _view_detail(self):
        sel = self._selected_client()
        if not sel:
            return
        try:
            full = self._client.get(f"/api/clients/{sel['id']}") or {}
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar cliente: {e}")
            return
        dlg = ClientDetailDialog(full, self._client, self)
        dlg.exec()

    def _recompute_tiers(self):
        try:
            resp = self._client.post("/api/memberships/recompute") or {}
            QMessageBox.information(self, "Tiers", resp.get("message", "Recomputado ✓"))
            self.refresh()
        except APIError as e:
            QMessageBox.warning(self, "Error", f"HTTP {e.status}: {e.detail}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{e}")
