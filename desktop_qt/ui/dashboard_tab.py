"""Tab Dashboard — KPIs del día y del mes en vivo.

Lee los endpoints reales del backend v4.3:
  - GET /api/statistics/kpis/today → KPIs (transactions, revenue, ...)
  - GET /api/statistics/kpis/month → KPIs

Schema KPIs (ver backend/lbamonitor/api/schemas/statistics.py):
    transactions, revenue, discounts, usb_count, sessions,
    gb_copied, files_copied, avg_per_session, avg_per_gb
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
)
from PySide6.QtCore import Qt

from desktop_qt.api.client import get_client


class _KPICard(QFrame):
    """Tarjeta KPI individual."""

    def __init__(self, title: str, default: str = "—"):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("kpi_label")
        layout.addWidget(title_label)

        self.value_label = QLabel(default)
        self.value_label.setObjectName("kpi_value")
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class DashboardTab(QWidget):
    """Dashboard con KPIs de hoy + mes."""

    def __init__(self, signals):
        super().__init__()
        self._client = get_client()
        self.signals = signals
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Título
        title = QLabel("Resumen del Día")
        title.setObjectName("page_title")
        layout.addWidget(title)

        # --- KPIs de HOY ---
        today_section = QLabel("HOY")
        today_section.setObjectName("section_title")
        layout.addWidget(today_section)

        today_grid = QGridLayout()
        today_grid.setSpacing(12)

        # Mapeo: (key_interno, label_a_mostrar, valor_default, formatter)
        # Los keys coinciden con los campos del schema KPIs del backend.
        today_kpis = [
            ("revenue", "Ingresos", "0.00 CUP"),
            ("transactions", "Transacciones", "0"),
            ("usb_count", "USBs", "0"),
            ("gb_copied", "GB Copiados", "0.0"),
            ("files_copied", "Archivos", "0"),
            ("avg_per_session", "Promedio/Sesión", "0.00"),
        ]

        self.today_labels: dict[str, _KPICard] = {}
        for i, (key, label, default) in enumerate(today_kpis):
            card = _KPICard(label, default)
            self.today_labels[key] = card
            today_grid.addWidget(card, i // 3, i % 3)
        layout.addLayout(today_grid)

        # --- KPIs del MES ---
        month_section = QLabel("ESTE MES")
        month_section.setObjectName("section_title")
        layout.addWidget(month_section)

        month_grid = QGridLayout()
        month_grid.setSpacing(12)

        month_kpis = [
            ("m_revenue", "Ingresos", "0.00 CUP"),
            ("m_transactions", "Transacciones", "0"),
            ("m_usb_count", "USBs", "0"),
            ("m_gb_copied", "GB Copiados", "0.0"),
            ("m_files_copied", "Archivos", "0"),
            ("m_avg_per_session", "Promedio/Sesión", "0.00"),
        ]

        self.month_labels: dict[str, _KPICard] = {}
        for i, (key, label, default) in enumerate(month_kpis):
            card = _KPICard(label, default)
            self.month_labels[key] = card
            month_grid.addWidget(card, i // 3, i % 3)
        layout.addLayout(month_grid)

        # --- Estado de carga / error ---
        self.status_label = QLabel("")
        self.status_label.setObjectName("kpi_label")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()

    def refresh(self):
        """Actualiza KPIs desde la API."""
        try:
            today = self._client.get("/api/statistics/kpis/today")
        except Exception as e:
            self.status_label.setText(f"Error cargando KPIs de hoy: {e}")
            self.status_label.setStyleSheet("color: #EF4444;")
            return

        try:
            month = self._client.get("/api/statistics/kpis/month")
        except Exception as e:
            month = {}  # Si falla el mes, mostramos solo hoy
            self.status_label.setText(f"Error cargando KPIs del mes: {e}")
            self.status_label.setStyleSheet("color: #EF4444;")
        else:
            self.status_label.setText("Actualizado")
            self.status_label.setStyleSheet("color: #22C55E;")

        # --- Poblar KPIs de hoy ---
        # today es el schema KPIs directamente (no envuelto en {"kpis": {...}})
        self.today_labels["revenue"].set_value(
            f"{float(today.get('revenue', 0) or 0):.2f} CUP"
        )
        self.today_labels["transactions"].set_value(
            str(today.get("transactions", 0) or 0)
        )
        self.today_labels["usb_count"].set_value(
            str(today.get("usb_count", 0) or 0)
        )
        self.today_labels["gb_copied"].set_value(
            f"{float(today.get('gb_copied', 0) or 0):.1f}"
        )
        self.today_labels["files_copied"].set_value(
            str(today.get("files_copied", 0) or 0)
        )
        self.today_labels["avg_per_session"].set_value(
            f"{float(today.get('avg_per_session', 0) or 0):.2f}"
        )

        # --- Poblar KPIs del mes ---
        self.month_labels["m_revenue"].set_value(
            f"{float(month.get('revenue', 0) or 0):.2f} CUP"
        )
        self.month_labels["m_transactions"].set_value(
            str(month.get("transactions", 0) or 0)
        )
        self.month_labels["m_usb_count"].set_value(
            str(month.get("usb_count", 0) or 0)
        )
        self.month_labels["m_gb_copied"].set_value(
            f"{float(month.get('gb_copied', 0) or 0):.1f}"
        )
        self.month_labels["m_files_copied"].set_value(
            str(month.get("files_copied", 0) or 0)
        )
        self.month_labels["m_avg_per_session"].set_value(
            f"{float(month.get('avg_per_session', 0) or 0):.2f}"
        )
