# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
APP_NAME = "UntappdBeerHistory"
ICON = ROOT / "resources" / "appicon.ico"


def safe_collect_data_files(package: str):
    try:
        return collect_data_files(package)
    except Exception:
        return []


def safe_collect_submodules(package: str):
    try:
        return collect_submodules(package)
    except Exception:
        return []


def safe_copy_metadata(distribution: str):
    try:
        return copy_metadata(distribution)
    except Exception:
        return []


datas = [
    (str(ROOT / "README.md"), "."),
]

for package in ("certifi", "plotly", "toga", "toga_winforms", "webdriver_manager"):
    datas += safe_collect_data_files(package)

for distribution in (
    "beautifulsoup4",
    "certifi",
    "charset-normalizer",
    "clr-loader",
    "idna",
    "numpy",
    "pandas",
    "plotly",
    "pythonnet",
    "requests",
    "selenium",
    "toga",
    "toga-core",
    "toga-winforms",
    "travertino",
    "urllib3",
    "webdriver-manager",
):
    datas += safe_copy_metadata(distribution)

hiddenimports = []
for package in (
    "clr_loader",
    "plotly.validators",
    "pythonnet",
    "toga",
    "toga_winforms",
    "travertino",
    "selenium",
    "webdriver_manager",
):
    hiddenimports += safe_collect_submodules(package)


a = Analysis(
    [str(SRC / "untappd_beer_history" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
