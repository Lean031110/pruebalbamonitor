# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec para lbamonitor-desktop.exe (app admin con PyWebView).

Genera un bundle --onedir con:
  - PyWebView (WebView2)
  - pystray (bandeja)
  - Pillow (icono)
  - Dependencias lbamonitor para importar config
"""
from pathlib import Path

block_cipher = None

BACKEND_DIR = Path(SPECPATH).parent  # backend/
PROJECT_ROOT = BACKEND_DIR.parent
DESKTOP_DIR = PROJECT_ROOT / "desktop"

a = Analysis(
    [str(DESKTOP_DIR / "lbamonitor_desktop" / "main.py")],
    pathex=[str(BACKEND_DIR), str(DESKTOP_DIR)],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / "config.default.toml"), "."),
    ],
    hiddenimports=[
        "webview",
        "webview.platforms.edgechromium",
        "pystray",
        "pystray._win32",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        # lbamonitor imports
        "lbamonitor",
        "lbamonitor.core.config",
        "lbamonitor.utils.logging_setup",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
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
    name="lbamonitor-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Sin consola (app de bandeja)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="lbamonitor-desktop",
)
