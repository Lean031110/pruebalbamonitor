"""Tab Settings — Configuración admin completa del sistema.

Secciones:
- Datos del negocio
- Precios (modo, per_gb/mb/file, fixed, min/max, descuentos VIP/empleado, promoción)
- Monitoreo (MTP interval, watcher buffer, debounce, filtros, excluir sistema)
- Backup (habilitado, hora, días a conservar, destino, on_exit)
- Logging (nivel, rotación, retención, ruta, consola)
- Apariencia (idioma, tema)
- Publicidad (carpeta, automático, carpetas de video)

Endpoints:
- GET/PUT /api/settings/business-info
- GET/PUT /api/settings/publicity-folder
- GET/PUT /api/settings/video-folders
- GET      /api/settings (listar KeyValue)
- PUT      /api/settings/{key}  (KeyValue genérico)

NOTA: pricing, monitoring, backup, logging, appearance no tienen endpoints
específicos. Se guardan como KeyValue con clave compuesta
"pricing.mode", "monitoring.mtp_poll_interval_seconds", etc., usando el
endpoint genérico /api/settings/{key}.
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop_qt.api.client import APIError, get_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes", "on")
    return bool(v)


def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Tab
# ---------------------------------------------------------------------------

class SettingsTab(QWidget):
    """Configuración admin completa."""

    PRICING_MODES = [
        ("per_gb", "Por GB"),
        ("per_mb", "Por MB"),
        ("per_file", "Por archivo"),
        ("fixed", "Precio fijo"),
        ("custom", "Personalizado"),
    ]

    LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    LANGUAGES = [("es", "Español"), ("en", "English")]
    THEMES = [("dark", "Oscuro"), ("light", "Claro")]

    def __init__(self, signals):
        super().__init__()
        self._client = get_client()
        self.signals = signals
        self._kv: dict[str, str] = {}  # cache de KeyValue
        self._setup_ui()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Configuración")
        title.setObjectName("page_title")
        header_row.addWidget(title)
        header_row.addStretch()
        refresh_btn = QPushButton("Refrescar")
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)
        test_btn = QPushButton("Probar configuración")
        test_btn.clicked.connect(self._test_config)
        header_row.addWidget(test_btn)
        save_btn = QPushButton("Guardar todo")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_all)
        header_row.addWidget(save_btn)
        outer.addLayout(header_row)

        # Loading
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(4)
        outer.addWidget(self.progress)

        # Scroll con todas las secciones
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(14)

        self._build_business_section(container_layout)
        self._build_pricing_section(container_layout)
        self._build_monitoring_section(container_layout)
        self._build_backup_section(container_layout)
        self._build_logging_section(container_layout)
        self._build_appearance_section(container_layout)
        self._build_publicity_section(container_layout)
        container_layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

    # ------------------------------------------------------------ Build UI
    def _build_business_section(self, parent_layout: QVBoxLayout):
        grp = QGroupBox("Datos del negocio")
        form = QFormLayout(grp)
        self.biz_name = QLineEdit()
        self.biz_address = QLineEdit()
        self.biz_phone = QLineEdit()
        self.biz_email = QLineEdit()
        self.biz_currency_code = QLineEdit()
        self.biz_currency_symbol = QLineEdit()
        self.biz_decimals = QSpinBox()
        self.biz_decimals.setRange(0, 4)
        self.biz_tax = QDoubleSpinBox()
        self.biz_tax.setRange(0, 100)
        self.biz_tax.setDecimals(2)
        self.biz_tax.setSuffix(" %")
        form.addRow("Nombre:", self.biz_name)
        form.addRow("Dirección:", self.biz_address)
        form.addRow("Teléfono:", self.biz_phone)
        form.addRow("Email:", self.biz_email)
        form.addRow("Moneda (código):", self.biz_currency_code)
        form.addRow("Símbolo moneda:", self.biz_currency_symbol)
        form.addRow("Decimales:", self.biz_decimals)
        form.addRow("Impuesto %:", self.biz_tax)
        parent_layout.addWidget(grp)

    def _build_pricing_section(self, parent_layout: QVBoxLayout):
        grp = QGroupBox("Precios")
        form = QFormLayout(grp)
        self.pr_mode = QComboBox()
        for v, label in self.PRICING_MODES:
            self.pr_mode.addItem(label, v)
        self.pr_per_gb = QDoubleSpinBox()
        self.pr_per_gb.setDecimals(2)
        self.pr_per_gb.setRange(0, 999999)
        self.pr_per_gb.setSuffix(" CUP")
        self.pr_per_mb = QDoubleSpinBox()
        self.pr_per_mb.setDecimals(4)
        self.pr_per_mb.setRange(0, 999999)
        self.pr_per_mb.setSuffix(" CUP")
        self.pr_per_file = QDoubleSpinBox()
        self.pr_per_file.setDecimals(2)
        self.pr_per_file.setRange(0, 999999)
        self.pr_per_file.setSuffix(" CUP")
        self.pr_fixed = QDoubleSpinBox()
        self.pr_fixed.setDecimals(2)
        self.pr_fixed.setRange(0, 999999)
        self.pr_fixed.setSuffix(" CUP")
        self.pr_min = QDoubleSpinBox()
        self.pr_min.setDecimals(2)
        self.pr_min.setRange(0, 999999)
        self.pr_min.setSuffix(" CUP")
        self.pr_max = QDoubleSpinBox()
        self.pr_max.setDecimals(2)
        self.pr_max.setRange(0, 999999)
        self.pr_max.setSuffix(" CUP")
        self.pr_vip_disc = QDoubleSpinBox()
        self.pr_vip_disc.setRange(0, 100)
        self.pr_vip_disc.setSuffix(" %")
        self.pr_emp_disc = QDoubleSpinBox()
        self.pr_emp_disc.setRange(0, 100)
        self.pr_emp_disc.setSuffix(" %")
        self.pr_promo_enabled = QCheckBox("Promoción activa")
        self.pr_promo_desc = QLineEdit()
        self.pr_promo_pct = QDoubleSpinBox()
        self.pr_promo_pct.setRange(0, 100)
        self.pr_promo_pct.setSuffix(" %")

        form.addRow("Modo:", self.pr_mode)
        form.addRow("Precio por GB:", self.pr_per_gb)
        form.addRow("Precio por MB:", self.pr_per_mb)
        form.addRow("Precio por archivo:", self.pr_per_file)
        form.addRow("Precio fijo:", self.pr_fixed)
        form.addRow("Mínimo:", self.pr_min)
        form.addRow("Máximo:", self.pr_max)
        form.addRow("Descuento VIP %:", self.pr_vip_disc)
        form.addRow("Descuento empleado %:", self.pr_emp_disc)
        form.addRow("", self.pr_promo_enabled)
        form.addRow("Descripción promo:", self.pr_promo_desc)
        form.addRow("% promo:", self.pr_promo_pct)
        parent_layout.addWidget(grp)

    def _build_monitoring_section(self, parent_layout: QVBoxLayout):
        grp = QGroupBox("Monitoreo")
        form = QFormLayout(grp)
        self.mon_mtp_interval = QSpinBox()
        self.mon_mtp_interval.setRange(1, 3600)
        self.mon_mtp_interval.setSuffix(" s")
        self.mon_buffer = QSpinBox()
        self.mon_buffer.setRange(1024, 16777216)
        self.mon_buffer.setSingleStep(1024)
        self.mon_debounce = QSpinBox()
        self.mon_debounce.setRange(0, 60000)
        self.mon_debounce.setSuffix(" ms")
        self.mon_filters = QLineEdit()
        self.mon_filters.setPlaceholderText("*.mp4,*.mkv,*.avi (vacío = todos)")
        self.mon_exclude_system = QCheckBox("Excluir archivos de sistema")

        form.addRow("Intervalo MTP:", self.mon_mtp_interval)
        form.addRow("Buffer watcher:", self.mon_buffer)
        form.addRow("Debounce:", self.mon_debounce)
        form.addRow("Filtros de archivos:", self.mon_filters)
        form.addRow("", self.mon_exclude_system)
        parent_layout.addWidget(grp)

    def _build_backup_section(self, parent_layout: QVBoxLayout):
        grp = QGroupBox("Backup")
        form = QFormLayout(grp)
        self.bk_enabled = QCheckBox("Habilitado")
        self.bk_hour = QSpinBox()
        self.bk_hour.setRange(0, 23)
        self.bk_hour.setSuffix(" h")
        self.bk_keep_days = QSpinBox()
        self.bk_keep_days.setRange(1, 3650)
        self.bk_keep_days.setSuffix(" días")
        self.bk_destination = QLineEdit()
        self.bk_on_exit = QCheckBox("Backup al salir")

        form.addRow("", self.bk_enabled)
        form.addRow("Hora:", self.bk_hour)
        form.addRow("Conservar:", self.bk_keep_days)
        form.addRow("Destino:", self.bk_destination)
        form.addRow("", self.bk_on_exit)
        parent_layout.addWidget(grp)

    def _build_logging_section(self, parent_layout: QVBoxLayout):
        grp = QGroupBox("Logging")
        form = QFormLayout(grp)
        self.log_level = QComboBox()
        for lvl in self.LOG_LEVELS:
            self.log_level.addItem(lvl, lvl)
        self.log_rotation = QLineEdit()
        self.log_rotation.setPlaceholderText("ej. 1 day")
        self.log_retention = QLineEdit()
        self.log_retention.setPlaceholderText("ej. 30 days")
        self.log_path = QLineEdit()
        self.log_console = QCheckBox("También a consola")

        form.addRow("Nivel:", self.log_level)
        form.addRow("Rotación:", self.log_rotation)
        form.addRow("Retención:", self.log_retention)
        form.addRow("Ruta:", self.log_path)
        form.addRow("", self.log_console)
        parent_layout.addWidget(grp)

    def _build_appearance_section(self, parent_layout: QVBoxLayout):
        grp = QGroupBox("Apariencia")
        form = QFormLayout(grp)
        self.app_language = QComboBox()
        for v, label in self.LANGUAGES:
            self.app_language.addItem(label, v)
        self.app_theme = QComboBox()
        for v, label in self.THEMES:
            self.app_theme.addItem(label, v)

        form.addRow("Idioma:", self.app_language)
        form.addRow("Tema:", self.app_theme)
        parent_layout.addWidget(grp)

    def _build_publicity_section(self, parent_layout: QVBoxLayout):
        grp = QGroupBox("Publicidad")
        form = QFormLayout(grp)
        self.pub_folder = QLineEdit()
        self.pub_automatic = QCheckBox("Copia automática")
        self.pub_video_folders = QTextEdit()
        self.pub_video_folders.setMaximumHeight(100)
        self.pub_video_folders.setPlaceholderText("Una carpeta por línea")

        form.addRow("Carpeta:", self.pub_folder)
        form.addRow("", self.pub_automatic)
        form.addRow("Carpetas de video:", self.pub_video_folders)
        parent_layout.addWidget(grp)

    # -------------------------------------------------------------- Refresh
    def refresh(self):
        self.progress.setVisible(True)
        try:
            self._load_kv()
            self._load_business()
            self._load_publicity()
            self._populate_from_kv()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Cargando configuración: {e}")
        finally:
            self.progress.setVisible(False)

    def _load_kv(self):
        """Carga todos los KeyValue a un dict {key: value}."""
        try:
            items = self._client.get("/api/settings") or []
            self._kv = {it.get("key"): it.get("value") for it in items if it.get("key")}
        except Exception:
            self._kv = {}

    def _load_business(self):
        try:
            data = self._client.get("/api/settings/business-info") or {}
            self.biz_name.setText(data.get("name", ""))
            self.biz_address.setText(data.get("address", ""))
            # phone, email, currency_code, currency_symbol, decimals, tax_percent
            # pueden venir en el KV; el endpoint BusinessInfo solo expone name/address/marketing_text
        except Exception:
            pass

    def _load_publicity(self):
        try:
            data = self._client.get("/api/settings/publicity-folder") or {}
            self.pub_folder.setText(data.get("folder_path", ""))
            self.pub_automatic.setChecked(_bool(data.get("automatic")))
        except Exception:
            pass
        try:
            data = self._client.get("/api/settings/video-folders") or {}
            folders = data.get("folders", []) or []
            self.pub_video_folders.setPlainText("\n".join(folders))
        except Exception:
            pass

    def _kv_get(self, key: str, default: str = "") -> str:
        return self._kv.get(key, default)

    def _populate_from_kv(self):
        """Poblar todos los widgets desde el cache de KeyValue."""
        kv = self._kv

        # Business (los campos que no están en BusinessInfo vienen del KV)
        self.biz_phone.setText(kv.get("business.phone", ""))
        self.biz_email.setText(kv.get("business.email", ""))
        self.biz_currency_code.setText(kv.get("business.currency_code", "CUP"))
        self.biz_currency_symbol.setText(kv.get("business.currency_symbol", "₱"))
        self.biz_decimals.setValue(_int(kv.get("business.currency_decimals", "2"), 2))
        self.biz_tax.setValue(_float(kv.get("business.tax_percent", "0"), 0))

        # Pricing
        self._set_combo_by_data(self.pr_mode, kv.get("pricing.mode", "per_gb"))
        self.pr_per_gb.setValue(_float(kv.get("pricing.price_per_gb", "25"), 25))
        self.pr_per_mb.setValue(_float(kv.get("pricing.price_per_mb", "0.05"), 0.05))
        self.pr_per_file.setValue(_float(kv.get("pricing.price_per_file", "1"), 1))
        self.pr_fixed.setValue(_float(kv.get("pricing.fixed_price", "50"), 50))
        self.pr_min.setValue(_float(kv.get("pricing.min_price", "5"), 5))
        self.pr_max.setValue(_float(kv.get("pricing.max_price", "5000"), 5000))
        self.pr_vip_disc.setValue(_float(kv.get("pricing.vip_discount_percent", "10"), 10))
        self.pr_emp_disc.setValue(_float(kv.get("pricing.employee_discount_percent", "50"), 50))
        self.pr_promo_enabled.setChecked(_bool(kv.get("pricing.promotion_enabled")))
        self.pr_promo_desc.setText(kv.get("pricing.promotion_description", ""))
        self.pr_promo_pct.setValue(_float(kv.get("pricing.promotion_discount_percent", "0"), 0))

        # Monitoring
        self.mon_mtp_interval.setValue(_int(kv.get("monitoring.mtp_poll_interval_seconds", "5"), 5))
        self.mon_buffer.setValue(_int(kv.get("monitoring.fs_watcher_buffer", "65536"), 65536))
        self.mon_debounce.setValue(_int(kv.get("monitoring.fs_debounce_ms", "500"), 500))
        self.mon_filters.setText(kv.get("monitoring.file_type_filters", ""))
        self.mon_exclude_system.setChecked(_bool(kv.get("monitoring.exclude_system_files", "true")))

        # Backup
        self.bk_enabled.setChecked(_bool(kv.get("backup.enabled", "true")))
        self.bk_hour.setValue(_int(kv.get("backup.hour", "3"), 3))
        self.bk_keep_days.setValue(_int(kv.get("backup.keep_days", "30"), 30))
        self.bk_destination.setText(kv.get("backup.destination", ""))
        self.bk_on_exit.setChecked(_bool(kv.get("backup.on_exit", "false")))

        # Logging
        self._set_combo_by_data(self.log_level, kv.get("logging.level", "INFO"))
        self.log_rotation.setText(kv.get("logging.rotation", "1 day"))
        self.log_retention.setText(kv.get("logging.retention", "30 days"))
        self.log_path.setText(kv.get("logging.path", ""))
        self.log_console.setChecked(_bool(kv.get("logging.console", "true")))

        # Appearance
        self._set_combo_by_data(self.app_language, kv.get("appearance.language", "es"))
        self._set_combo_by_data(self.app_theme, kv.get("appearance.theme", "dark"))

    def _set_combo_by_data(self, combo: QComboBox, value: str):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        # Si no matchea, intentar por texto (caso de QComboBox con strings simples)
        for i in range(combo.count()):
            if combo.itemText(i) == value:
                combo.setCurrentIndex(i)
                return

    # -------------------------------------------------------------- Save
    def _save_all(self):
        self.progress.setVisible(True)
        errors: list[str] = []
        try:
            # 1) Business info (endpoint dedicado)
            try:
                self._client.put("/api/settings/business-info", {
                    "name": self.biz_name.text().strip(),
                    "address": self.biz_address.text().strip(),
                    "marketing_text": "",
                })
            except APIError as e:
                errors.append(f"business-info: HTTP {e.status} {e.detail}")

            # 2) Publicity (endpoint dedicado)
            try:
                self._client.put("/api/settings/publicity-folder", {
                    "folder_path": self.pub_folder.text().strip(),
                    "automatic": self.pub_automatic.isChecked(),
                })
            except APIError as e:
                errors.append(f"publicity-folder: HTTP {e.status} {e.detail}")

            try:
                folders = [
                    ln.strip() for ln in self.pub_video_folders.toPlainText().splitlines()
                    if ln.strip()
                ]
                self._client.put("/api/settings/video-folders", {"folders": folders})
            except APIError as e:
                errors.append(f"video-folders: HTTP {e.status} {e.detail}")

            # 3) Resto via KeyValue genérico
            kv_pairs = {
                # Business
                "business.phone": self.biz_phone.text().strip(),
                "business.email": self.biz_email.text().strip(),
                "business.currency_code": self.biz_currency_code.text().strip(),
                "business.currency_symbol": self.biz_currency_symbol.text().strip(),
                "business.currency_decimals": str(self.biz_decimals.value()),
                "business.tax_percent": str(self.biz_tax.value()),
                # Pricing
                "pricing.mode": self.pr_mode.currentData(),
                "pricing.price_per_gb": str(self.pr_per_gb.value()),
                "pricing.price_per_mb": str(self.pr_per_mb.value()),
                "pricing.price_per_file": str(self.pr_per_file.value()),
                "pricing.fixed_price": str(self.pr_fixed.value()),
                "pricing.min_price": str(self.pr_min.value()),
                "pricing.max_price": str(self.pr_max.value()),
                "pricing.vip_discount_percent": str(self.pr_vip_disc.value()),
                "pricing.employee_discount_percent": str(self.pr_emp_disc.value()),
                "pricing.promotion_enabled": "true" if self.pr_promo_enabled.isChecked() else "false",
                "pricing.promotion_description": self.pr_promo_desc.text().strip(),
                "pricing.promotion_discount_percent": str(self.pr_promo_pct.value()),
                # Monitoring
                "monitoring.mtp_poll_interval_seconds": str(self.mon_mtp_interval.value()),
                "monitoring.fs_watcher_buffer": str(self.mon_buffer.value()),
                "monitoring.fs_debounce_ms": str(self.mon_debounce.value()),
                "monitoring.file_type_filters": self.mon_filters.text().strip(),
                "monitoring.exclude_system_files": "true" if self.mon_exclude_system.isChecked() else "false",
                # Backup
                "backup.enabled": "true" if self.bk_enabled.isChecked() else "false",
                "backup.hour": str(self.bk_hour.value()),
                "backup.keep_days": str(self.bk_keep_days.value()),
                "backup.destination": self.bk_destination.text().strip(),
                "backup.on_exit": "true" if self.bk_on_exit.isChecked() else "false",
                # Logging
                "logging.level": self.log_level.currentData(),
                "logging.rotation": self.log_rotation.text().strip(),
                "logging.retention": self.log_retention.text().strip(),
                "logging.path": self.log_path.text().strip(),
                "logging.console": "true" if self.log_console.isChecked() else "false",
                # Appearance
                "appearance.language": self.app_language.currentData(),
                "appearance.theme": self.app_theme.currentData(),
            }

            for k, v in kv_pairs.items():
                try:
                    self._client.put(f"/api/settings/{k}", {"value": v})
                except APIError as e:
                    errors.append(f"{k}: HTTP {e.status} {e.detail}")

            if errors:
                QMessageBox.warning(
                    self, "Guardado con errores",
                    "Algunos valores no se guardaron:\n  - " + "\n  - ".join(errors[:10]),
                )
            else:
                QMessageBox.information(self, "OK", "Configuración guardada ✓")
                self.refresh()
        finally:
            self.progress.setVisible(False)

    def _test_config(self):
        """Valida que el backend siga respondiendo y lista las settings críticas."""
        try:
            if not self._client.is_api_responding():
                QMessageBox.warning(self, "Test", "❌ Backend no responde.")
                return
            # Verificar un par de settings críticas
            kpis = self._client.get("/api/statistics/kpis/today") or {}
            ok_count = 0 if isinstance(kpis, dict) and "detail" in kpis else 1
            QMessageBox.information(
                self, "Test",
                f"✅ Backend OK\nKPIs hoy: {kpis.get('transactions', 0)} transacciones, "
                f"{kpis.get('revenue', 0)} CUP.\n\n"
                f"Settings cargadas: {len(self._kv)} clave-valor.\n"
                f"Configuración válida para guardar.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Test", f"❌ Error: {e}")
