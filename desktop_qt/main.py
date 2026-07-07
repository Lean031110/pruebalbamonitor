"""
LBAMonitor Desktop v4.3 — App PySide6 nativa.

Interfaz PRINCIPAL del sistema. 100% Python, sin WebView.

Uso:
  python -m desktop_qt            # modo normal
  python -m desktop_qt --kiosk    # modo kiosco (pantalla completa)
"""
from __future__ import annotations

import os
import sys
import subprocess
import time
from pathlib import Path

# Añadir backend al path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if BACKEND_DIR.is_dir():
    sys.path.insert(0, str(BACKEND_DIR.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt


def ensure_service_running(max_wait: int = 30) -> bool:
    """Verifica que el servicio backend esté corriendo. Lo arranca si no."""
    from desktop_qt.api.client import get_client
    client = get_client()

    if client.is_api_responding():
        return True

    print("Servicio no detectado. Arrancando automáticamente...")

    try:
        if BACKEND_DIR.is_dir():
            cmd = [sys.executable, "-m", "lbamonitor.monitor"]
            cwd = str(BACKEND_DIR)
        else:
            cmd = ["lbamonitor-svc.exe"]
            cwd = None

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=cwd,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        print(f"Servicio arrancado (PID={proc.pid})")
    except Exception as e:
        print(f"Error arrancando servicio: {e}")
        return False

    for i in range(max_wait):
        time.sleep(1)
        if client.is_api_responding():
            print(f"API respondiendo después de {i+1}s ✓")
            return True

    return False


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="LBAMonitor Desktop v4.3")
    parser.add_argument("--kiosk", action="store_true", help="Modo kiosco (pantalla completa)")
    parser.add_argument("--url", default="http://127.0.0.1:8123", help="URL del backend")
    args = parser.parse_args()

    # Asegurar que el servicio está corriendo
    ensure_service_running()

    # Crear aplicación Qt
    app = QApplication(sys.argv)
    app.setApplicationName("LBAMonitor")
    app.setApplicationVersion("4.3.0")

    # Cargar estilo QSS
    qss_path = Path(__file__).resolve().parent / "assets" / "style.qss"
    if qss_path.is_file():
        app.setStyleSheet(qss_path.read_text())

    # Icono de la app
    icon_path = Path(__file__).resolve().parent / "assets" / "icon.ico"
    if not icon_path.is_file():
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Login
    from desktop_qt.api.client import get_client
    client = get_client()
    client.base_url = args.url

    from desktop_qt.ui.login_dialog import LoginDialog
    if not LoginDialog.login():
        print("Login cancelado. Saliendo.")
        return 0

    # Ventana principal
    from desktop_qt.ui.main_window import MainWindow
    window = MainWindow(kiosk=args.kiosk)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
