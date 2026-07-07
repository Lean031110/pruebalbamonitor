# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec para lbamonitor-cli.exe (herramienta de administración).
"""
from pathlib import Path

block_cipher = None
BACKEND_DIR = Path(SPECPATH).parent
PROJECT_ROOT = BACKEND_DIR.parent

a = Analysis(
    [str(BACKEND_DIR / "lbamonitor" / "cli" / "__main__.py")],
    pathex=[str(BACKEND_DIR)],
    binaries=[],
    datas=[
        (str(BACKEND_DIR / "alembic"), "alembic"),
        (str(BACKEND_DIR / "alembic.ini"), "."),
        (str(PROJECT_ROOT / "config.default.toml"), "."),
    ],
    hiddenimports=[
        "click",
        "rich",
        "lbamonitor",
        "lbamonitor.core",
        "lbamonitor.core.services.license_engine",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "pandas.tests",
        "IPython",
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
    name="lbamonitor-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="lbamonitor-cli",
)
