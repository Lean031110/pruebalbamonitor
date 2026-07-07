"""
Ventana principal de LBAMonitor Desktop v4.3 (PySide6).

Estructura:
  - Sidebar (izquierda) con navegación
  - QStackedWidget (centro) con las diferentes tabs
  - Topbar con título + usuario + logout
  - SystemTrayIcon con menú contextual
  - WSClient (QObject) que recibe eventos WebSocket en un QThread
    dedicado y emite signals thread-safe al main thread.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QFrame, QSystemTrayIcon,
    QMenu, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import QPixmap, QAction, QIcon

from desktop_qt.api.client import get_client


class SignalsBridge(QObject):
    """Bridge para señales entre el WSClient (QThread) y la UI (main thread).

    Hereda de QObject para poder definir signals Qt. Los signals son
    thread-safe: si se emiten desde otro hilo, Qt encola la llamada en
    la event loop del hilo del receptor (main thread).
    """
    drive_inserted = Signal(dict)
    drive_removed = Signal(str)
    eject_pending = Signal(dict)
    file_copied = Signal(dict)
    stats_updated = Signal(dict)
    log_entry = Signal(dict)


class MainWindow(QMainWindow):
    """Ventana principal con sidebar + tabs + bandeja + WS."""

    def __init__(self, kiosk: bool = False):
        super().__init__()
        self.kiosk = kiosk
        self._client = get_client()
        self.signals = SignalsBridge()
        self._ws_client = None
        self._ws_reconnect_timer = None

        self.setWindowTitle(f"LBAMonitor v4.3 — {self._client.username or 'admin'}")
        self.setMinimumSize(1280, 800)

        if kiosk:
            self.showFullScreen()
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        self._setup_ui()
        self._setup_tray()
        self._setup_timers()
        self._start_ws_client()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Sidebar ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Logo + título
        logo_frame = QFrame()
        logo_frame.setFixedHeight(56)
        logo_layout = QHBoxLayout(logo_frame)
        logo_layout.setContentsMargins(16, 8, 16, 8)

        logo_label = QLabel()
        logo_path = self._get_asset("logo.png")
        if logo_path:
            pix = QPixmap(logo_path)
            if not pix.isNull():
                logo_label.setPixmap(
                    pix.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        logo_layout.addWidget(logo_label)

        title = QLabel("LBAMonitor")
        title.setObjectName("app_title")
        logo_layout.addWidget(title)
        logo_layout.addStretch()

        sidebar_layout.addWidget(logo_frame)

        # Botones de navegación
        self.nav_buttons = []
        nav_items = [
            ("dashboard", "Dashboard"),
            ("usb", "USBs Activos"),
            ("billing", "Cobros"),
            ("clients", "Clientes"),
            ("catalog", "Catálogo"),
            ("settings", "Configuración"),
            ("logs", "Logs"),
            ("license", "Licencia"),
        ]

        for nav_id, label in nav_items:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, nid=nav_id: self._switch_tab(nid))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append((nav_id, btn))

        sidebar_layout.addStretch()

        # Usuario + logout
        user_frame = QFrame()
        user_frame.setFixedHeight(60)
        user_layout = QHBoxLayout(user_frame)
        user_layout.setContentsMargins(16, 8, 16, 8)

        # Mostrar el usuario logueado real (desde el ApiClient)
        user_label = QLabel(self._client.username or "admin")
        user_label.setObjectName("kpi_label")
        user_layout.addWidget(user_label)

        logout_btn = QPushButton("Salir")
        logout_btn.clicked.connect(self._logout)
        user_layout.addWidget(logout_btn)

        sidebar_layout.addWidget(user_frame)
        main_layout.addWidget(sidebar)

        # --- Content ---
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Topbar
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(56)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(24, 8, 24, 8)

        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("page_title")
        topbar_layout.addWidget(self.page_title)
        topbar_layout.addStretch()

        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #22C55E; font-size: 16px;")
        topbar_layout.addWidget(self.status_indicator)

        self.status_label = QLabel("Servicio activo")
        self.status_label.setObjectName("kpi_label")
        topbar_layout.addWidget(self.status_label)

        content_layout.addWidget(topbar)

        # Stack de tabs
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)

        # Crear tabs (lazy import para evitar circular deps)
        self._tabs = {}
        self._create_tabs()

        main_layout.addWidget(content, 1)

        # Status bar
        self.statusBar().showMessage("Listo")

        # Seleccionar dashboard por defecto
        self._switch_tab("dashboard")

    def _create_tabs(self):
        """Crea todas las tabs y las añade al stack."""
        from desktop_qt.ui.dashboard_tab import DashboardTab
        from desktop_qt.ui.usb_tab import USBTab
        from desktop_qt.ui.billing_tab import BillingTab
        from desktop_qt.ui.clients_tab import ClientsTab
        from desktop_qt.ui.catalog_tab import CatalogTab
        from desktop_qt.ui.settings_tab import SettingsTab
        from desktop_qt.ui.logs_tab import LogsTab
        from desktop_qt.ui.license_tab import LicenseTab

        tabs = [
            ("dashboard", DashboardTab),
            ("usb", USBTab),
            ("billing", BillingTab),
            ("clients", ClientsTab),
            ("catalog", CatalogTab),
            ("settings", SettingsTab),
            ("logs", LogsTab),
            ("license", LicenseTab),
        ]

        for tab_id, tab_class in tabs:
            try:
                tab = tab_class(self.signals)
                self._tabs[tab_id] = tab
                self.stack.addWidget(tab)
            except Exception as e:
                # Si una tab falla, crear placeholder
                placeholder = QLabel(f"Error cargando {tab_id}: {e}")
                placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._tabs[tab_id] = placeholder
                self.stack.addWidget(placeholder)

    def _switch_tab(self, tab_id: str):
        """Cambia a la tab seleccionada."""
        titles = {
            "dashboard": "Dashboard",
            "usb": "USBs Activos",
            "billing": "Cobros",
            "clients": "Clientes",
            "catalog": "Catálogo",
            "settings": "Configuración",
            "logs": "Logs",
            "license": "Licencia",
        }
        self.page_title.setText(titles.get(tab_id, "LBAMonitor"))

        for nid, btn in self.nav_buttons:
            btn.setChecked(nid == tab_id)

        if tab_id in self._tabs:
            self.stack.setCurrentWidget(self._tabs[tab_id])
            # Llamar refresh si existe
            tab = self._tabs[tab_id]
            if hasattr(tab, "refresh"):
                try:
                    tab.refresh()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self):
        """Configura el icono de bandeja."""
        icon_path = self._get_asset("icon.ico")
        if icon_path:
            self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
        else:
            self.tray_icon = QSystemTrayIcon(self)

        tray_menu = QMenu()

        show_action = QAction("Mostrar", self)
        show_action.triggered.connect(self.showNormal)
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        backup_action = QAction("Forzar backup", self)
        backup_action.triggered.connect(self._trigger_backup)
        tray_menu.addAction(backup_action)

        tray_menu.addSeparator()

        quit_action = QAction("Salir", self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _setup_timers(self):
        """Timer para refrescar datos periódicamente."""
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_current_tab)
        self.refresh_timer.start(5000)  # 5 segundos

        # Timer para verificar estado del servicio
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self._check_health)
        self.health_timer.start(30000)  # 30 segundos

    def _refresh_current_tab(self):
        """Refresca la tab actual."""
        current = self.stack.currentWidget()
        if hasattr(current, "refresh"):
            try:
                current.refresh()
            except Exception:
                pass

    def _check_health(self):
        """Verifica que el servicio esté activo."""
        if self._client.is_api_responding():
            self.status_indicator.setStyleSheet("color: #22C55E; font-size: 16px;")
            self.status_label.setText("Servicio activo")
        else:
            self.status_indicator.setStyleSheet("color: #EF4444; font-size: 16px;")
            self.status_label.setText("Servicio caído")

    def _trigger_backup(self):
        """Fuerza un backup."""
        try:
            self._client.post("/api/backups/trigger")
            self.tray_icon.showMessage(
                "LBAMonitor", "Backup creado ✓",
                QSystemTrayIcon.MessageIcon.Information, 3000,
            )
        except Exception:
            self.tray_icon.showMessage(
                "LBAMonitor", "Error creando backup",
                QSystemTrayIcon.MessageIcon.Critical, 3000,
            )

    # ------------------------------------------------------------------
    # WebSocket client (thread-safe via QObject signals)
    # ------------------------------------------------------------------

    def _start_ws_client(self):
        """Arranca el WSClient thread-safe.

        WSClient hereda de QObject y emite signals Qt desde el QThread
        donde corre el WebSocketApp. Los signals son encolados al main
        thread automáticamente por Qt, así que es seguro llamar a
        QSystemTrayIcon.showMessage u otros métodos Qt desde los slots.
        """
        from desktop_qt.api.ws_client import WSClient

        ws_url = (
            self._client.base_url
            .replace("http://", "ws://")
            .replace("https://", "wss://")
            + "/ws/events"
        )
        token = self._client.get_access_token()
        self._ws_client = WSClient(ws_url, token=token)

        # Conectar signals del WSClient a slots del main_window (main thread).
        # Qt garantiza que el slot corre en el hilo del receptor (main thread).
        self._ws_client.event_received.connect(self._on_ws_event)
        self._ws_client.connected.connect(self._on_ws_connected)
        self._ws_client.disconnected.connect(self._on_ws_disconnected)
        self._ws_client.error.connect(self._on_ws_error)

        self._ws_client.start()

    def _on_ws_event(self, event: dict):
        """Slot (main thread) que recibe cada evento WS y lo dispatchea."""
        evt_type = event.get("type", "")
        evt_data = event.get("data", {}) or {}

        if evt_type == "drive.inserted":
            self.signals.drive_inserted.emit(evt_data)
            # Notificación de bandeja
            device = evt_data.get("name") or evt_data.get("drive_letter") or "USB"
            self.tray_icon.showMessage(
                "LBAMonitor", f"USB insertada: {device}",
                QSystemTrayIcon.MessageIcon.Information, 3000,
            )
        elif evt_type == "drive.removed":
            self.signals.drive_removed.emit(evt_data.get("drive_letter", ""))
        elif evt_type == "drive.eject.pending":
            self.signals.eject_pending.emit(evt_data)
        elif evt_type == "file.copied":
            self.signals.file_copied.emit(evt_data)
        elif evt_type == "log.entry":
            self.signals.log_entry.emit(evt_data)
        # Otros eventos (billing.registered, reward.granted, etc.) se ignoran
        # aquí pero podrían añadirse fácilmente.

    def _on_ws_connected(self):
        self.status_indicator.setStyleSheet("color: #22C55E; font-size: 16px;")
        self.status_label.setText("Conectado")

    def _on_ws_disconnected(self):
        # Mantener el indicador de salud del backend (lo refresca el timer)
        pass

    def _on_ws_error(self, msg: str):
        # Errores de WS son no fatales: el WSClient reconecta solo.
        pass

    # ------------------------------------------------------------------
    # Logout / close
    # ------------------------------------------------------------------

    def _logout(self):
        """Cierra sesión y la ventana."""
        try:
            self._client.logout()
        except Exception:
            pass
        self.close()

    def _get_asset(self, name: str) -> str:
        """Busca un archivo de assets."""
        candidates = [
            Path(__file__).resolve().parent.parent / "assets" / name,
            Path(__file__).resolve().parent.parent.parent / "assets" / name,
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
        return ""

    def closeEvent(self, event):
        """Al cerrar, detener todo ordenadamente."""
        # Detener WSClient (stop() espera al QThread hasta 5s)
        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception:
                pass
            self._ws_client = None
        # Detener timers
        try:
            self.refresh_timer.stop()
            self.health_timer.stop()
        except Exception:
            pass
        # Ocultar tray
        if self.tray_icon:
            self.tray_icon.hide()
        event.accept()
