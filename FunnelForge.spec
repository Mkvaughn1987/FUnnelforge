# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    collect_dynamic_libs,
)

# -------------------------------------------------
# Force-include the funnel_forge package (your app)
# -------------------------------------------------
ff_hidden = collect_submodules("funnel_forge")
ff_datas = collect_data_files("funnel_forge")

# -------------------------------------------------
# FORCE INCLUDE PYWIN32 / OUTLOOK COM DEPENDENCIES
# Fixes: ModuleNotFoundError: win32timezone (scheduled/future emails)
# -------------------------------------------------
pywin_hidden = []
pywin_hidden += ["win32timezone", "pythoncom", "pywintypes"]
pywin_hidden += collect_submodules("win32com")
pywin_hidden += collect_submodules("win32")

# Include py files for dynamic imports
pywin_datas = []
pywin_datas += collect_data_files("win32", include_py_files=True)
pywin_datas += collect_data_files("win32com", include_py_files=True)

# Include required pywin32 DLLs (pythoncom311.dll, pywintypes311.dll, etc.)
pywin_bins = collect_dynamic_libs("pywin32_system32")

# -------------------------------------------------
# Merge all collections
# -------------------------------------------------
hiddenimports = ff_hidden + pywin_hidden
datas = ff_datas + pywin_datas
binaries = pywin_bins

# Bundle assets folder
if os.path.isdir("assets"):
    datas += [("assets", "assets")]

a = Analysis(
    ["run_funnelforge.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FunnelForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FunnelForge",
)

# Post-build: Move assets from _internal to root (next to EXE)
import shutil
assets_src = os.path.join(DISTPATH, "FunnelForge", "_internal", "assets")
assets_dst = os.path.join(DISTPATH, "FunnelForge", "assets")
if os.path.isdir(assets_src):
    if os.path.isdir(assets_dst):
        shutil.rmtree(assets_dst)
    shutil.copytree(assets_src, assets_dst)
