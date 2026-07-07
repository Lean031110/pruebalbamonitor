"""Tab License — Estado de licencia + activación.

Funcionalidades:
- Card grande mostrando estado: TRIAL / LICENSED / EXPIRED / INVALID
- Si TRIAL: días restantes (barra de progreso)
- Si EXPIRED: mensaje "Adquiera licencia" + botón "Activar licencia"
- Campo para pegar license key + botón "Activar"
- Mostrar Machine ID (con botón "Copiar al portapapeles")
- Mostrar tier actual (trial/pro/enterprise)
- Mostrar fecha de expiración (si aplica)
- Botón "Solicitar licencia" → guía (HWID + contacto proveedor)

Endpoints:
- GET  /api/license/status        → estado completo con trial
- GET  /api/license               → estado legacy (LicenseStatus schema)
- GET  /api/license/machine-id    → HWID
- POST /api/license/activate      → activar con license_key
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop_qt.api.client import APIError, get_client


# ---------------------------------------------------------------------------
# Estados visuales
# ---------------------------------------------------------------------------

STATE_STYLES = {
    "trial":    {"color": "#FBBF24", "bg": "#78350F", "label": "TRIAL"},
    "licensed": {"color": "#22C55E", "bg": "#14532D", "label": "LICENCIADO"},
    "expired":  {"color": "#EF4444", "bg": "#7F1D1D", "label": "EXPIRADO"},
    "invalid":  {"color": "#EF4444", "bg": "#7F1D1D", "label": "INVÁLIDO"},
}


class LicenseTab(QWidget):
    """Estado de licencia y activación."""

    TRIAL_DAYS = 10  # trial de 10 días según backend

    def __init__(self, signals):
        super().__init__()
        self._client = get_client()
        self.signals = signals
        self._machine_id: str = ""
        self._setup_ui()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Licencia")
        title.setObjectName("page_title")
        header_row.addWidget(title)
        header_row.addStretch()
        refresh_btn = QPushButton("Refrescar")
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        # Loading
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(4)
        layout.addWidget(self.progress)

        # --- Card grande de estado ---
        self.state_card = QFrame()
        self.state_card.setObjectName("card")
        self.state_card.setMinimumHeight(140)
        state_layout = QVBoxLayout(self.state_card)
        state_layout.setContentsMargins(28, 20, 28, 20)
        state_layout.setSpacing(8)

        self.state_label = QLabel("—")
        self.state_label.setObjectName("kpi_value")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet("font-size: 36px; font-weight: bold;")
        state_layout.addWidget(self.state_label)

        self.reason_label = QLabel("")
        self.reason_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reason_label.setObjectName("kpi_label")
        state_layout.addWidget(self.reason_label)

        # Barra de progreso (visible solo en trial)
        self.trial_progress = QProgressBar()
        self.trial_progress.setRange(0, self.TRIAL_DAYS)
        self.trial_progress.setVisible(False)
        self.trial_progress.setTextVisible(True)
        self.trial_progress.setFormat("Días restantes: %v / %m")
        state_layout.addWidget(self.trial_progress)

        self.expires_label = QLabel("")
        self.expires_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.expires_label.setObjectName("kpi_label")
        state_layout.addWidget(self.expires_label)

        layout.addWidget(self.state_card)

        # --- Grid de info: tier, machine_id, fecha expiración ---
        info_grid = QGridLayout()
        info_grid.setSpacing(10)

        self.tier_value = self._make_info_card(info_grid, 0, 0, "Tier actual", "—")
        self.exp_value = self._make_info_card(info_grid, 0, 1, "Expira", "—")
        self.days_value = self._make_info_card(info_grid, 0, 2, "Días restantes", "—")

        layout.addLayout(info_grid)

        # --- Machine ID con botón copiar ---
        mid_frame = QFrame()
        mid_frame.setObjectName("card")
        mid_layout = QVBoxLayout(mid_frame)
        mid_layout.setContentsMargins(16, 12, 16, 12)

        mid_title = QLabel("Machine ID (HWID)")
        mid_title.setObjectName("section_title")
        mid_layout.addWidget(mid_title)

        mid_row = QHBoxLayout()
        self.machine_id_edit = QLineEdit()
        self.machine_id_edit.setReadOnly(True)
        self.machine_id_edit.setPlaceholderText("(cargando…)")
        mid_row.addWidget(self.machine_id_edit, 1)

        copy_btn = QPushButton("Copiar al portapapeles")
        copy_btn.clicked.connect(self._copy_machine_id)
        mid_row.addWidget(copy_btn)
        mid_layout.addLayout(mid_row)

        layout.addWidget(mid_frame)

        # --- Activación ---
        act_frame = QFrame()
        act_frame.setObjectName("card")
        act_layout = QVBoxLayout(act_frame)
        act_layout.setContentsMargins(16, 12, 16, 12)

        act_title = QLabel("Activar licencia")
        act_title.setObjectName("section_title")
        act_layout.addWidget(act_title)

        act_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("Pegue aquí la license key recibida…")
        self.key_edit.setMinimumHeight(36)
        act_row.addWidget(self.key_edit, 1)

        activate_btn = QPushButton("Activar")
        activate_btn.setObjectName("primary")
        activate_btn.setMinimumHeight(36)
        activate_btn.clicked.connect(self._activate)
        act_row.addWidget(activate_btn)

        act_layout.addLayout(act_row)

        # Botones adicionales
        btn_row = QHBoxLayout()
        request_btn = QPushButton("Solicitar licencia (guía)")
        request_btn.clicked.connect(self._show_request_guide)
        btn_row.addWidget(request_btn)
        btn_row.addStretch()
        act_layout.addLayout(btn_row)

        layout.addWidget(act_frame)

        layout.addStretch()

    def _make_info_card(self, grid: QGridLayout, row: int, col: int,
                        title: str, default: str) -> QLabel:
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
            self._load_machine_id()
            self._load_status()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar estado: {e}")
        finally:
            self.progress.setVisible(False)

    def _load_machine_id(self):
        try:
            data = self._client.get("/api/license/machine-id") or {}
            self._machine_id = data.get("machine_id", "")
            self.machine_id_edit.setText(self._machine_id)
        except APIError as e:
            self.machine_id_edit.setText(f"Error HTTP {e.status}: {e.detail}")
        except Exception as e:
            self.machine_id_edit.setText(f"Error: {e}")

    def _load_status(self):
        try:
            status = self._client.get("/api/license/status") or {}
        except APIError as e:
            # Fallback al endpoint legacy
            try:
                legacy = self._client.get("/api/license") or {}
                status = {
                    "state": "licensed" if legacy.get("valid") else "invalid",
                    "tier": legacy.get("tier", "trial"),
                    "reason": legacy.get("reason", "—"),
                    "expires": legacy.get("expires"),
                    "days_remaining": None,
                    "machine_id": legacy.get("machine_id", self._machine_id),
                }
            except Exception as e2:
                QMessageBox.warning(self, "Error", f"No se pudo cargar estado: {e2}")
                return
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar estado: {e}")
            return

        state = (status.get("state") or "trial").lower()
        tier = status.get("tier") or "trial"
        reason = status.get("reason") or ""
        expires = status.get("expires")
        days_remaining = status.get("days_remaining")
        features_limited = status.get("features_limited", False)

        # --- Actualizar card grande ---
        style = STATE_STYLES.get(state, STATE_STYLES["trial"])
        self.state_label.setText(style["label"])
        self.state_label.setStyleSheet(
            f"font-size: 36px; font-weight: bold; color: {style['color']};"
        )
        self.state_card.setStyleSheet(
            f"QFrame#card {{ background-color: {style['bg']}; "
            f"border: 1px solid {style['color']}; border-radius: 8px; }}"
        )

        if reason:
            self.reason_label.setText(reason)
        else:
            self.reason_label.setText("")

        # --- Trial: mostrar barra de progreso ---
        if state == "trial" and days_remaining is not None:
            self.trial_progress.setVisible(True)
            try:
                days = int(days_remaining)
            except (TypeError, ValueError):
                days = 0
            self.trial_progress.setValue(max(0, min(self.TRIAL_DAYS, days)))
            self.days_value.setText(str(days))
        else:
            self.trial_progress.setVisible(False)
            self.days_value.setText("—")

        # --- Tier y expiración ---
        self.tier_value.setText(str(tier).upper())
        if expires:
            self.expires_label.setText(f"Expira el: {expires}")
            self.exp_value.setText(str(expires)[:10])
        else:
            self.expires_label.setText("Sin fecha de expiración")
            self.exp_value.setText("—")

        # Si expired/invalid, mostrar CTA adicional
        if state in ("expired", "invalid"):
            self.reason_label.setText(
                f"⚠ {reason or 'Licencia inválida o expirada.'} "
                f"Adquiera una licencia para continuar operando."
            )

    # -------------------------------------------------------------- Acciones
    def _copy_machine_id(self):
        if not self._machine_id:
            QMessageBox.warning(self, "Copiar", "No hay Machine ID para copiar.")
            return
        cb = QGuiApplication.clipboard()
        cb.setText(self._machine_id)
        QMessageBox.information(
            self, "Copiado",
            f"Machine ID copiado al portapapeles:\n\n{self._machine_id[:32]}…\n\n"
            f"Pégalo en el formulario de solicitud de licencia.",
        )

    def _activate(self):
        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Activar", "Pegue una license key primero.")
            return

        try:
            resp = self._client.post("/api/license/activate", {"license_key": key}) or {}
        except APIError as e:
            QMessageBox.warning(self, "Activar", f"HTTP {e.status}: {e.detail}")
            return
        except Exception as e:
            QMessageBox.warning(self, "Activar", f"Error: {e}")
            return

        if resp.get("success"):
            lic = resp.get("license") or {}
            QMessageBox.information(
                self, "Licencia activada ✓",
                f"{resp.get('message', 'OK')}\n\n"
                f"Tier: {lic.get('tier', '—')}\n"
                f"Expira: {lic.get('expires', '—')}",
            )
            self.key_edit.clear()
            self.refresh()
        else:
            QMessageBox.warning(
                self, "Activación fallida",
                resp.get("message", "No se pudo activar la licencia."),
            )

    def _show_request_guide(self):
        """Muestra una guía con los pasos para obtener una licencia."""
        mid = self._machine_id or "(cargue la pestaña primero)"
        guide = (
            "=== CÓMO SOLICITAR UNA LICENCIA ===\n\n"
            "1. Copie su Machine ID (HWID) mostrado arriba en esta pestaña.\n"
            "   También puede usar el botón 'Copiar al portapapeles'.\n\n"
            "2. Envíe el Machine ID a su proveedor autorizado de LBAMonitor,\n"
            "   junto con el tier deseado (trial / pro / enterprise).\n\n"
            "3. El proveedor generará una license key firmada para su máquina\n"
            "   y se la enviará (típicamente por email o mensaje).\n\n"
            "4. Pegue la license key en el campo 'Activar licencia' y haga clic\n"
            "   en 'Activar'.\n\n"
            "5. Si la activación es exitosa, el estado cambiará a 'LICENCIADO'\n"
            "   y se mostrará el tier y la fecha de expiración.\n\n"
            "----------------------------------------\n"
            f"SU MACHINE ID:\n{mid}\n\n"
            "----------------------------------------\n"
            "NOTA: El Machine ID es único para esta máquina. Si formatea o\n"
            "cambia hardware importante (motherboard, CPU), necesitará una\n"
            "nueva licencia.\n"
        )

        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Solicitar licencia — Guía")
        dlg.setMinimumSize(620, 520)
        v = QVBoxLayout(dlg)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(guide)
        v.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        dlg.exec()
