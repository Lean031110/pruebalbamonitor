"""Tab Catalog — Gestión de catálogo de audiovisuales.

Funcionalidades:
- Tabla de entradas (título, categoría, año, género, tamaño GB, veces
  copiado, activo)
- Filtro por categoría + búsqueda por texto
- Botones: Nuevo / Editar / Desactivar (soft delete)
- Formulario de creación/edición con todos los campos
- Botón "Ver top copiados"

Endpoints usados:
- GET    /api/catalog?page=&page_size=&category=&active_only=&query=
- GET    /api/catalog/{id}
- POST   /api/catalog
- PATCH  /api/catalog/{id}
- DELETE /api/catalog/{id}   (soft delete → active=false)
- GET    /api/catalog/top-copied?limit=
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
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


CATEGORIES = [
    ("", "Todas"),
    ("movie", "Película"),
    ("series", "Series"),
    ("music", "Música"),
    ("document", "Documento"),
    ("game", "Juego"),
    ("app", "App"),
    ("other", "Otro"),
]


# ---------------------------------------------------------------------------
# Diálogo crear/editar entrada
# ---------------------------------------------------------------------------

class CatalogEditDialog(QDialog):
    """Formulario para crear/editar una entrada de catálogo."""

    def __init__(self, parent=None, entry: Optional[dict] = None):
        super().__init__(parent)
        self._entry = entry
        self.setWindowTitle("Editar entrada" if entry else "Nueva entrada")
        self.setMinimumSize(520, 540)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.title_edit = QLineEdit()
        form.addRow("Título *:", self.title_edit)

        self.category_combo = QComboBox()
        for v, label in CATEGORIES:
            if v:  # skip "Todas"
                self.category_combo.addItem(label, v)
        form.addRow("Categoría *:", self.category_combo)

        self.year_spin = QSpinBox()
        self.year_spin.setRange(1900, 2100)
        self.year_spin.setValue(2024)
        form.addRow("Año:", self.year_spin)

        self.genre_edit = QLineEdit()
        form.addRow("Género:", self.genre_edit)

        self.director_edit = QLineEdit()
        form.addRow("Director:", self.director_edit)

        self.artist_edit = QLineEdit()
        form.addRow("Artista:", self.artist_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        form.addRow("Descripción:", self.description_edit)

        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(0, 99999)
        self.size_spin.setDecimals(2)
        self.size_spin.setSuffix(" GB")
        form.addRow("Tamaño:", self.size_spin)

        self.rating_spin = QDoubleSpinBox()
        self.rating_spin.setRange(0, 10)
        self.rating_spin.setDecimals(1)
        self.rating_spin.setSuffix(" / 10")
        form.addRow("Rating:", self.rating_spin)

        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 99999)
        self.duration_spin.setSuffix(" min")
        form.addRow("Duración:", self.duration_spin)

        self.cover_edit = QLineEdit()
        self.cover_edit.setPlaceholderText("Ruta a portada (opcional)")
        form.addRow("Cover:", self.cover_edit)

        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Ruta al archivo (opcional)")
        form.addRow("Archivo:", self.file_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("tags, separados, por, coma")
        form.addRow("Tags:", self.tags_edit)

        self.active_check = QCheckBox("Activo")
        self.active_check.setChecked(True)
        form.addRow("", self.active_check)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Pre-llenar
        if self._entry:
            e = self._entry
            self.title_edit.setText(e.get("title") or "")
            cur_cat = e.get("category")
            for i in range(self.category_combo.count()):
                if self.category_combo.itemData(i) == cur_cat:
                    self.category_combo.setCurrentIndex(i)
                    break
            if e.get("year"):
                self.year_spin.setValue(int(e["year"]))
            self.genre_edit.setText(e.get("genre") or "")
            self.director_edit.setText(e.get("director") or "")
            self.artist_edit.setText(e.get("artist") or "")
            self.description_edit.setPlainText(e.get("description") or "")
            if e.get("size_gb") is not None:
                self.size_spin.setValue(float(e["size_gb"]))
            if e.get("rating") is not None:
                self.rating_spin.setValue(float(e["rating"]))
            if e.get("duration_minutes") is not None:
                self.duration_spin.setValue(int(e["duration_minutes"]))
            self.cover_edit.setText(e.get("cover_path") or "")
            self.file_edit.setText(e.get("file_path") or "")
            self.tags_edit.setText(e.get("tags") or "")
            self.active_check.setChecked(bool(e.get("active", True)))

    def _validate_and_accept(self):
        if not self.title_edit.text().strip():
            QMessageBox.warning(self, "Validación", "El título es obligatorio.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "title": self.title_edit.text().strip(),
            "category": self.category_combo.currentData(),
            "year": self.year_spin.value(),
            "genre": self.genre_edit.text().strip() or None,
            "director": self.director_edit.text().strip() or None,
            "artist": self.artist_edit.text().strip() or None,
            "description": self.description_edit.toPlainText().strip() or None,
            "size_gb": self.size_spin.value(),
            "rating": self.rating_spin.value(),
            "duration_minutes": self.duration_spin.value(),
            "cover_path": self.cover_edit.text().strip() or None,
            "file_path": self.file_edit.text().strip() or None,
            "tags": self.tags_edit.text().strip() or None,
            "active": self.active_check.isChecked(),
        }


# ---------------------------------------------------------------------------
# Tab principal
# ---------------------------------------------------------------------------

class CatalogTab(QWidget):
    """Gestión del catálogo de audiovisuales."""

    def __init__(self, signals):
        super().__init__()
        self._client = get_client()
        self.signals = signals
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Catálogo")
        title.setObjectName("page_title")
        header_row.addWidget(title)
        header_row.addStretch()
        refresh_btn = QPushButton("Refrescar")
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        # Filtros + acciones
        filters_row = QHBoxLayout()

        filters_row.addWidget(QLabel("Categoría:"))
        self.category_combo = QComboBox()
        for v, label in CATEGORIES:
            self.category_combo.addItem(label, v)
        self.category_combo.currentIndexChanged.connect(self._on_filter_changed)
        filters_row.addWidget(self.category_combo)

        filters_row.addWidget(QLabel("Buscar:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Texto a buscar…")
        self.search_edit.textChanged.connect(self._on_filter_changed)
        filters_row.addWidget(self.search_edit, 1)

        self.show_inactive = QCheckBox("Inactivos")
        self.show_inactive.toggled.connect(self._on_filter_changed)
        filters_row.addWidget(self.show_inactive)

        filters_row.addStretch()

        new_btn = QPushButton("Nuevo")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self._new_entry)
        filters_row.addWidget(new_btn)

        edit_btn = QPushButton("Editar")
        edit_btn.clicked.connect(self._edit_entry)
        filters_row.addWidget(edit_btn)

        deactivate_btn = QPushButton("Desactivar")
        deactivate_btn.clicked.connect(self._deactivate_entry)
        filters_row.addWidget(deactivate_btn)

        top_btn = QPushButton("Ver top copiados")
        top_btn.clicked.connect(self._view_top)
        filters_row.addWidget(top_btn)

        layout.addLayout(filters_row)

        # Loading
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(4)
        layout.addWidget(self.progress)

        # Tabla
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Título", "Categoría", "Año", "Género",
            "Tamaño (GB)", "Veces copiado", "Activo",
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
        self.table.doubleClicked.connect(self._edit_entry)
        layout.addWidget(self.table)

    # -------------------------------------------------------------- Refresh
    def refresh(self):
        self.progress.setVisible(True)
        try:
            self._load_entries()
        finally:
            self.progress.setVisible(False)

    def _load_entries(self):
        params: dict = {"page": 1, "page_size": 500}
        cat = self.category_combo.currentData()
        if cat:
            params["category"] = cat
        q = self.search_edit.text().strip()
        if q:
            params["query"] = q
        # active_only=False si "Inactivos" está activo
        params["active_only"] = not self.show_inactive.isChecked()

        try:
            data = self._client.get("/api/catalog", params) or {}
            items = data.get("items", []) if isinstance(data, dict) else []
        except APIError as e:
            QMessageBox.warning(self, "Error", f"HTTP {e.status}: {e.detail}")
            return
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar catálogo: {e}")
            return

        self.table.setRowCount(len(items))
        for i, e in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(str(e.get("id", ""))))
            self.table.setItem(i, 1, QTableWidgetItem(e.get("title", "")))
            self.table.setItem(i, 2, QTableWidgetItem(e.get("category", "—")))
            self.table.setItem(i, 3, QTableWidgetItem(str(e.get("year") or "—")))
            self.table.setItem(i, 4, QTableWidgetItem(e.get("genre") or "—"))
            size = e.get("size_gb")
            self.table.setItem(i, 5, QTableWidgetItem(f"{float(size):.2f}" if size else "—"))
            self.table.setItem(i, 6, QTableWidgetItem(str(e.get("times_copied", 0))))
            active = "Sí" if e.get("active", True) else "No"
            item = QTableWidgetItem(active)
            if not e.get("active", True):
                item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(i, 7, item)

    # -------------------------------------------------------------- Acciones
    def _on_filter_changed(self, *_):
        self._load_entries()

    def _selected_entry_id(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Seleccionar", "Seleccione una entrada de la tabla.")
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        try:
            return int(item.text())
        except ValueError:
            return None

    def _new_entry(self):
        dlg = CatalogEditDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._client.post("/api/catalog", dlg.get_data())
            QMessageBox.information(self, "OK", "Entrada creada ✓")
            self.refresh()
        except APIError as e:
            QMessageBox.warning(self, "Error", f"HTTP {e.status}: {e.detail}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo crear: {e}")

    def _edit_entry(self):
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        try:
            full = self._client.get(f"/api/catalog/{entry_id}") or {}
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar entrada: {e}")
            return

        dlg = CatalogEditDialog(self, entry=full)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._client.patch(f"/api/catalog/{entry_id}", dlg.get_data())
            QMessageBox.information(self, "OK", "Entrada actualizada ✓")
            self.refresh()
        except APIError as e:
            QMessageBox.warning(self, "Error", f"HTTP {e.status}: {e.detail}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{e}")

    def _deactivate_entry(self):
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        confirm = QMessageBox.question(
            self, "Confirmar",
            f"¿Desactivar la entrada #{entry_id}? (soft-delete, no se elimina)",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self._client.delete(f"/api/catalog/{entry_id}")
            QMessageBox.information(self, "OK", "Entrada desactivada ✓")
            self.refresh()
        except APIError as e:
            QMessageBox.warning(self, "Error", f"HTTP {e.status}: {e.detail}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{e}")

    def _view_top(self):
        """Muestra el top de entradas más copiadas."""
        limit, ok = QInputDialog.getInt(
            self, "Top copiados", "Número de entradas:", value=10, min=1, max=100,
        )
        if not ok:
            return
        try:
            items = self._client.get(
                "/api/catalog/top-copied", {"limit": limit}
            ) or []
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar top: {e}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Top {limit} más copiados")
        dlg.setMinimumSize(640, 460)
        v = QVBoxLayout(dlg)
        table = QTableWidget(len(items), 4)
        table.setHorizontalHeaderLabels(["Título", "Categoría", "Veces copiado", "Tamaño (GB)"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.setAlternatingRowColors(True)
        for i, e in enumerate(items):
            table.setItem(i, 0, QTableWidgetItem(e.get("title", "")))
            table.setItem(i, 1, QTableWidgetItem(e.get("category", "—")))
            table.setItem(i, 2, QTableWidgetItem(str(e.get("times_copied", 0))))
            size = e.get("size_gb")
            table.setItem(i, 3, QTableWidgetItem(f"{float(size):.2f}" if size else "—"))
        v.addWidget(table)
        close = QPushButton("Cerrar")
        close.clicked.connect(dlg.accept)
        v.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()
