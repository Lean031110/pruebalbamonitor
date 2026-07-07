"""
Diálogo de login para la app desktop PySide6 (LBAMonitor v4.3).

Hace POST a /api/auth/login (manejado por ApiClient.login) y guarda
access_token + refresh_token en el singleton ApiClient.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QFrame, QSizePolicy, QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from desktop_qt.api.client import get_client, APIError


class LoginDialog(QDialog):
    """Diálogo de login con usuario y contraseña."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LBAMonitor — Login")
        self.setFixedSize(420, 460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._client = get_client()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignCenter)

        # Logo
        logo_label = QLabel()
        logo_path = self._get_logo_path()
        if logo_path:
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                logo_label.setPixmap(
                    pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        # Título
        title = QLabel("LBAMonitor")
        title.setObjectName("login_title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Monitoreo de copias USB")
        subtitle.setObjectName("login_subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        # Usuario
        user_label = QLabel("Usuario")
        user_label.setObjectName("kpi_label")
        layout.addWidget(user_label)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("nombre de usuario")
        self.user_input.setMinimumHeight(40)
        layout.addWidget(self.user_input)

        # Password
        pass_label = QLabel("Contraseña")
        pass_label.setObjectName("kpi_label")
        layout.addWidget(pass_label)

        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("••••••••")
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.pass_input.setMinimumHeight(40)
        self.pass_input.returnPressed.connect(self._try_login)
        layout.addWidget(self.pass_input)

        # Error
        self.error_label = QLabel("")
        self.error_label.setObjectName("error_label")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        layout.addSpacing(10)

        # Botón
        self.login_btn = QPushButton("Entrar")
        self.login_btn.setObjectName("primary")
        self.login_btn.setMinimumHeight(44)
        self.login_btn.clicked.connect(self._try_login)
        layout.addWidget(self.login_btn)

        self.user_input.setFocus()

    def _get_logo_path(self) -> str:
        from pathlib import Path
        candidates = [
            Path(__file__).resolve().parent.parent / "assets" / "logo.png",
            Path(__file__).resolve().parent.parent.parent / "assets" / "logo.png",
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
        return ""

    def _try_login(self):
        username = self.user_input.text().strip()
        password = self.pass_input.text()

        if not username or not password:
            self._show_error("Ingresa usuario y contraseña")
            return

        self.login_btn.setEnabled(False)
        self.login_btn.setText("Entrando...")
        self.error_label.setVisible(False)

        # Procesar eventos para que la UI se actualice
        QApplication.processEvents()

        try:
            self._client.login(username, password)
            # Si llegamos aquí, login exitoso (tokens ya guardados en el client)
            self.accept()
            return
        except APIError as e:
            if e.status == 401:
                self._show_error("Usuario o contraseña incorrectos")
            elif e.status == 0:
                # Error de conexión
                msg = str(e)
                if "refused" in msg or "connect" in msg.lower() or "timeout" in msg.lower():
                    self._show_error(
                        "No se pudo conectar al servicio.\n"
                        "¿Está lbamonitor-svc corriendo?"
                    )
                else:
                    self._show_error(f"Error de red: {e.detail[:120]}")
            elif e.status == 429:
                self._show_error(
                    "Demasiados intentos fallidos.\nEspera un minuto e inténtalo de nuevo."
                )
            else:
                self._show_error(f"Error del servidor ({e.status}): {e.detail[:120]}")
        except Exception as e:
            self._show_error(f"Error inesperado: {str(e)[:120]}")

        self.login_btn.setEnabled(True)
        self.login_btn.setText("Entrar")

    def _show_error(self, msg: str):
        self.error_label.setText(msg)
        self.error_label.setVisible(True)

    @staticmethod
    def login(parent=None) -> bool:
        """Muestra el diálogo de login. Devuelve True si el login fue exitoso."""
        dialog = LoginDialog(parent)
        return dialog.exec() == QDialog.DialogCode.Accepted
