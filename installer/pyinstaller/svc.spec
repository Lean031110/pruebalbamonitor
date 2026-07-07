# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec para lbamonitor-svc.exe (servicio de monitoreo + API).

Genera un bundle --onedir con todas las dependencias necesarias:
  - FastAPI + Uvicorn
  - SQLAlchemy 2.0 async + aiosqlite
  - watchdog + pywin32 (Windows)
  - pythonnet + MediaDevices.dll (MTP)
  - Pillow + openpyxl + reportlab
  - Alembic

Excluye:
  - matplotlib (usamos Recharts en frontend, ahorra 40 MB)
  - tkinter (no se usa)
  - tests
"""
from pathlib import Path
import sys

block_cipher = None

# Rutas
BACKEND_DIR = Path(SPECPATH).parent  # backend/
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

a = Analysis(
    [str(BACKEND_DIR / "lbamonitor" / "monitor" / "__main__.py")],
    pathex=[str(BACKEND_DIR)],
    binaries=[],
    datas=[
        # Incluir migraciones Alembic
        (str(BACKEND_DIR / "alembic"), "alembic"),
        (str(BACKEND_DIR / "alembic.ini"), "."),
        # Incluir config por defecto
        (str(PROJECT_ROOT / "config.default.toml"), "."),
        # Incluir frontend build (si existe)
        (str(FRONTEND_DIST), "frontend/dist") if FRONTEND_DIST.is_dir() else (),
    ],
    hiddenimports=[
        # FastAPI / Starlette
        "fastapi",
        "fastapi.middleware.cors",
        "starlette.responses",
        "starlette.staticfiles",
        # SQLAlchemy
        "sqlalchemy",
        "sqlalchemy.ext.asyncio",
        "sqlalchemy.dialects.sqlite",
        "aiosqlite",
        "greenlet",
        # Uvicorn
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # Pydantic
        "pydantic",
        "pydantic_settings",
        "pydantic_core",
        # Watchdog
        "watchdog",
        "watchdog.observers",
        "watchdog.events",
        # Logging
        "loguru",
        # Pillow
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFont",
        # openpyxl / reportlab
        "openpyxl",
        "reportlab",
        # Alembic
        "alembic",
        "alembic.command",
        "alembic.config",
        "alembic.script",
        "alembic.environment",
        # HTTP
        "httpx",
        "anyio",
        "sniffio",
        # APScheduler
        "apscheduler",
        # Utils
        "click",
        "rich",
        # pythonnet (solo en Windows)
        "clr",
    ] + (
        # Windows-only
        ["win32api", "win32con", "win32gui", "win32file", "pythoncom", "wmi", "pywintypes"]
        if sys.platform == "win32" else []
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "matplotlib",
        "matplotlib.tests",
        "numpy.tests",
        "pandas.tests",
        "IPython",
        "notebook",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="lbamonitor-svc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Servicio: consola visible para logs
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "installer" / "assets" / "icon.ico") if (PROJECT_ROOT / "installer" / "assets" / "icon.ico").is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="lbamonitor-svc",
)
