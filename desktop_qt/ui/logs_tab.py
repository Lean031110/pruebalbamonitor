"""Tab Logs — Visor de logs en tiempo real.

Funcionalidades:
- Tabla con columnas: timestamp, level, módulo, mensaje
- Filtro por nivel (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- Filtro por texto de búsqueda
- Auto-scroll (toggle on/off)
- Botón "Limpiar vista"
- Botón "Exportar a archivo"
- Botón "Refrescar"

Estrategia de obtención de logs:
1) Intenta GET /api/admin/logs (si el backend lo implementa en el futuro).
2) Si no existe (404), lee directamente el archivo de log local:
   - La ruta se obtiene del KV 'logging.path' (GET /api/settings/logging.path).
   - Si no, fallback a la ruta por defecto del OS:
     * Windows: C:/ProgramData/LBAMonitor/logs/lbamonitor.log
     * Linux/Mac: /var/log/lbamonitor/lbamonitor.log o ~/.lbamonitor/logs/
3) Si la señal WS 'log_entry' está activa, los nuevos logs se añaden en vivo.

Formato de línea de loguru (ej.):
  2024-12-30 14:32:45.123 | INFO     | lbamonitor.api.routes.billings:create_billing:78 - Cobro creado
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
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


LEVEL_COLORS = {
    "DEBUG":    "#9CA3AF",
    "INFO":     "#60A5FA",
    "WARNING":  "#FBBF24",
    "ERROR":    "#EF4444",
    "CRITICAL": "#DC2626",
    "TRACE":    "#A78BFA",
}

# Regex para parsear línea de loguru:
# 2024-12-30 14:32:45.123 | INFO     | module:func:78 - message
LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    r"\s*\|\s*(?P<level>[A-Z]+)"
    r"\s*\|\s*(?P<module>[^|]+?)"
    r"\s*-\s*(?P<msg>.*)$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_log_path() -> Path:
    if sys.platform.startswith("win"):
        return Path("C:/ProgramData/LBAMonitor/logs/lbamonitor.log")
    if os.geteuid() == 0 if hasattr(os, "geteuid") else False:
        return Path("/var/log/lbamonitor/lbamonitor.log")
    return Path.home() / ".lbamonitor" / "logs" / "lbamonitor.log"


def _parse_line(line: str) -> Optional[dict]:
    """Parsea una línea de loguru y devuelve dict {ts, level, module, msg}."""
    m = LOG_LINE_RE.match(line.strip())
    if not m:
        return None
    return {
        "ts": m.group("ts"),
        "level": m.group("level").strip(),
        "module": m.group("module").strip()[:80],  # truncar para UI
        "msg": m.group("msg").strip(),
    }


# ---------------------------------------------------------------------------
# Tab
# ---------------------------------------------------------------------------

class LogsTab(QWidget):
    """Visor de logs en tiempo real."""

    LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def __init__(self, signals):
        super().__init__()
        self._client = get_client()
        self.signals = signals
        self._log_path: Optional[Path] = None
        self._last_size: int = 0
        self._setup_ui()

        # Señal WS: log_entry viene del backend (si lo emite)
        try:
            self.signals.log_entry.connect(self._on_log_entry)
        except Exception:
            pass

        # Timer para polling de archivo (cada 2s)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_log_file)
        self._poll_timer.start(2000)

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Logs")
        title.setObjectName("page_title")
        header_row.addWidget(title)

        self.path_label = QLabel("Log: (sin cargar)")
        self.path_label.setObjectName("kpi_label")
        header_row.addWidget(self.path_label, 1)

        refresh_btn = QPushButton("Refrescar")
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        # Filtros
        filters_row = QHBoxLayout()

        filters_row.addWidget(QLabel("Nivel:"))
        self.level_combo = QComboBox()
        for lvl in self.LEVELS:
            self.level_combo.addItem(lvl, lvl)
        self.level_combo.currentIndexChanged.connect(self._apply_filters)
        filters_row.addWidget(self.level_combo)

        filters_row.addWidget(QLabel("Buscar:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Texto a filtrar (regex o substring)…")
        self.search_edit.textChanged.connect(self._apply_filters)
        filters_row.addWidget(self.search_edit, 1)

        self.autoscroll_check = QCheckBox("Auto-scroll")
        self.autoscroll_check.setChecked(True)
        filters_row.addWidget(self.autoscroll_check)

        clear_btn = QPushButton("Limpiar vista")
        clear_btn.clicked.connect(self._clear_view)
        filters_row.addWidget(clear_btn)

        export_btn = QPushButton("Exportar…")
        export_btn.clicked.connect(self._export)
        filters_row.addWidget(export_btn)

        layout.addLayout(filters_row)

        # Loading
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(4)
        layout.addWidget(self.progress)

        # Tabla
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Level", "Módulo", "Mensaje"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        # Status
        self.status_label = QLabel("")
        self.status_label.setObjectName("kpi_label")
        layout.addWidget(self.status_label)

    # -------------------------------------------------------------- Refresh
    def refresh(self):
        self.progress.setVisible(True)
        try:
            self._resolve_log_path()
            self._last_size = 0  # forzar releer
            self._all_entries: list[dict] = []
            self._load_full_log()
            self._apply_filters()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudieron cargar logs: {e}")
        finally:
            self.progress.setVisible(False)

    def _resolve_log_path(self):
        """Determina la ruta del archivo de log.

        1. Intenta GET /api/admin/logs (si existe).
        2. Si no, lee logging.path del KV.
        3. Si no, usa el default del OS.
        """
        # 1. Probar endpoint (puede no existir todavía)
        try:
            data = self._client.get("/api/admin/logs", {"limit": 200}) or {}
            if isinstance(data, list):
                # El endpoint sí existe y devuelve lista de entries
                self._log_path = None  # modo API
                self.path_label.setText("Log: API /api/admin/logs")
                self._all_entries = [
                    {
                        "ts": e.get("timestamp", ""),
                        "level": e.get("level", "INFO"),
                        "module": e.get("module") or e.get("logger") or "—",
                        "msg": e.get("message", ""),
                    }
                    for e in data
                ]
                return
            if isinstance(data, dict) and "items" in data:
                self._log_path = None
                self.path_label.setText("Log: API /api/admin/logs")
                self._all_entries = [
                    {
                        "ts": e.get("timestamp", ""),
                        "level": e.get("level", "INFO"),
                        "module": e.get("module") or "—",
                        "msg": e.get("message", ""),
                    }
                    for e in data["items"]
                ]
                return
            if isinstance(data, dict) and "path" in data:
                self._log_path = Path(data["path"])
                self.path_label.setText(f"Log: {self._log_path}")
                return
        except APIError as e:
            if e.status != 404:
                # Otro error → mejor intentar leer el archivo
                pass
        except Exception:
            pass

        # 2. Intentar leer logging.path del KV
        try:
            kv = self._client.get("/api/settings/logging.path") or {}
            path_str = kv.get("value") if isinstance(kv, dict) else None
            if path_str:
                self._log_path = Path(path_str) / "lbamonitor.log"
                self.path_label.setText(f"Log: {self._log_path}")
                return
        except Exception:
            pass

        # 3. Default del OS
        self._log_path = _default_log_path()
        self.path_label.setText(f"Log: {self._log_path} (default)")

    def _load_full_log(self):
        """Lee el archivo de log completo (tail de N líneas)."""
        if self._log_path is None:
            # Ya está cargado vía API
            if not hasattr(self, "_all_entries"):
                self._all_entries = []
            return

        if not hasattr(self, "_all_entries"):
            self._all_entries = []

        try:
            p = self._log_path
            if not p.is_file():
                self.status_label.setText(f"Archivo no encontrado: {p}")
                return

            size = p.stat().st_size
            self._last_size = size

            # Leer últimas ~5000 líneas para no saturar la UI
            # (leer por bloques desde el final sería más eficiente, pero
            # para simplicidad leemos todo y hacemos tail)
            try:
                with p.open("r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[-5000:]
            except Exception:
                return

            entries = []
            for line in lines:
                e = _parse_line(line)
                if e:
                    entries.append(e)
                else:
                    # Línea sin timestamp (multi-línea) → adjuntar al anterior
                    if entries:
                        entries[-1]["msg"] += "\n" + line.rstrip()
            self._all_entries = entries
            self.status_label.setText(f"{len(entries)} entradas cargadas.")
        except Exception as e:
            self.status_label.setText(f"Error leyendo log: {e}")

    def _poll_log_file(self):
        """Polling cada 2s: si el archivo creció, lee solo el delta."""
        if self._log_path is None or not self._log_path.is_file():
            return
        try:
            size = self._log_path.stat().st_size
        except Exception:
            return

        if size < self._last_size:
            # Log rotó → releer todo
            self._last_size = 0
            self._load_full_log()
            self._apply_filters()
            return

        if size == self._last_size:
            return

        # Hay contenido nuevo: leerlo
        try:
            with self._log_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self._last_size)
                new_lines = f.readlines()
            self._last_size = size
        except Exception:
            return

        # Añadir entradas nuevas
        appended = 0
        for line in new_lines:
            e = _parse_line(line)
            if e:
                self._all_entries.append(e)
                appended += 1
            elif self._all_entries:
                self._all_entries[-1]["msg"] += "\n" + line.rstrip()

        if appended > 0:
            self._apply_filters()

    # -------------------------------------------------------------- Filtros
    def _apply_filters(self, *_):
        if not hasattr(self, "_all_entries"):
            self._all_entries = []

        level = self.level_combo.currentData()
        query = self.search_edit.text().strip()
        query_re = None
        if query:
            try:
                query_re = re.compile(query, re.IGNORECASE)
            except re.error:
                # Si no es regex válida, tratamos como substring literal
                query_re = None
                query_lower = query.lower()

        def matches(e: dict) -> bool:
            if level != "ALL" and e.get("level") != level:
                return False
            if not query:
                return True
            text = f"{e.get('msg','')} {e.get('module','')}"
            if query_re is not None:
                return bool(query_re.search(text))
            return query_lower in text.lower()

        filtered = [e for e in self._all_entries if matches(e)]
        self.table.setRowCount(len(filtered))
        for i, e in enumerate(filtered):
            ts_item = QTableWidgetItem(e.get("ts", ""))
            ts_item.setForeground(QColor("#A1A1AA"))
            self.table.setItem(i, 0, ts_item)

            lvl = e.get("level", "INFO")
            lvl_item = QTableWidgetItem(lvl)
            color = LEVEL_COLORS.get(lvl, "#E4E4E7")
            lvl_item.setForeground(QColor(color))
            self.table.setItem(i, 1, lvl_item)

            self.table.setItem(i, 2, QTableWidgetItem(e.get("module", "—")))
            self.table.setItem(i, 3, QTableWidgetItem(e.get("msg", "")))

        self.status_label.setText(
            f"{len(filtered)} / {len(self._all_entries)} entradas mostradas."
        )

        if self.autoscroll_check.isChecked() and self.table.rowCount() > 0:
            self.table.scrollToBottom()

    # -------------------------------------------------------------- Acciones
    def _clear_view(self):
        self.table.setRowCount(0)
        self.status_label.setText("Vista limpiada.")

    def _export(self):
        if not hasattr(self, "_all_entries") or not self._all_entries:
            QMessageBox.information(self, "Exportar", "No hay logs para exportar.")
            return

        default_name = f"lbamonitor_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar logs", default_name, "Log (*.log);;Text (*.txt);;All (*.*)",
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                for e in self._all_entries:
                    f.write(
                        f"{e.get('ts','')} | {e.get('level',''):8s} | "
                        f"{e.get('module','')} - {e.get('msg','')}\n"
                    )
            QMessageBox.information(self, "Exportar", f"Logs exportados a:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Exportar", f"Error: {e}")

    def _on_log_entry(self, data: dict):
        """Slot para la señal WS 'log_entry' (si el backend la emite)."""
        if not hasattr(self, "_all_entries"):
            self._all_entries = []
        entry = {
            "ts": data.get("timestamp") or data.get("ts") or datetime.now().isoformat(),
            "level": data.get("level", "INFO"),
            "module": data.get("module") or data.get("logger") or "ws",
            "msg": data.get("message") or data.get("msg", ""),
        }
        self._all_entries.append(entry)
        # Solo aplicar filtros si el nivel pasa el filtro actual
        if self._passes_filter(entry):
            self._append_row(entry)

    def _passes_filter(self, e: dict) -> bool:
        level = self.level_combo.currentData()
        if level != "ALL" and e.get("level") != level:
            return False
        query = self.search_edit.text().strip()
        if not query:
            return True
        text = f"{e.get('msg','')} {e.get('module','')}"
        try:
            return bool(re.search(query, text, re.IGNORECASE))
        except re.error:
            return query.lower() in text.lower()

    def _append_row(self, e: dict):
        """Añade una fila al final de la tabla."""
        row = self.table.rowCount()
        self.table.insertRow(row)

        ts_item = QTableWidgetItem(e.get("ts", ""))
        ts_item.setForeground(QColor("#A1A1AA"))
        self.table.setItem(row, 0, ts_item)

        lvl = e.get("level", "INFO")
        lvl_item = QTableWidgetItem(lvl)
        lvl_item.setForeground(QColor(LEVEL_COLORS.get(lvl, "#E4E4E7")))
        self.table.setItem(row, 1, lvl_item)

        self.table.setItem(row, 2, QTableWidgetItem(e.get("module", "—")))
        self.table.setItem(row, 3, QTableWidgetItem(e.get("msg", "")))

        if self.autoscroll_check.isChecked():
            self.table.scrollToBottom()
