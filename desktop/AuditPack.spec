# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows build.

Build with:  pyinstaller desktop/AuditPack.spec --noconfirm
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

PROJECT_ROOT = Path(SPECPATH).parent
DESKTOP_DIR = PROJECT_ROOT / "desktop"

EXE_NAME = "AuditPack"

# --- Bundled resources -------------------------------------------------------
datas = [
    (str(PROJECT_ROOT / "index.html"), "."),
]
binaries = []

hiddenimports = [
    "app",
    "controls_data",
    "key_store",
    "paths",
    "waitress",
]

# anthropic (and its httpx/pydantic stack) ship data files PyInstaller will not
# discover from imports alone, e.g. certifi's CA bundle for HTTPS.
for package in ("anthropic", "httpx", "httpcore", "certifi", "waitress"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# pywebview ships the native webview glue (and, on Windows, the WebView2
# interop assemblies) as package data. Optional: without it the launcher falls
# back to the default browser.
for package in ("webview", "pythonnet", "clr_loader"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception:
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Keep the download reasonable: none of these are used by the app.
excludes = [
    "matplotlib", "scipy", "numpy", "pandas", "IPython", "notebook", "jupyter",
    "pytest", "PyQt5", "PyQt6", "PySide2", "PySide6", "sqlalchemy", "torch",
    "tensorflow", "sklearn",
]

icon_windows = DESKTOP_DIR / "icon.ico"


a = Analysis(
    [str(DESKTOP_DIR / "launcher.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,             # no black console window for end users
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_windows) if icon_windows.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=EXE_NAME,
)
