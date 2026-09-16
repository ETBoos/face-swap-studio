# Build on Windows x64 using scripts/build-windows.ps1.
from pathlib import Path
import sys

from PyInstaller.utils.hooks import copy_metadata

if sys.platform != "win32":
    raise SystemExit("The Windows package must be built on Windows.")

root = Path(SPECPATH).parent
datas = copy_metadata("face-swap-studio")
datas += [
    (str(root / "src" / "face_swap_studio" / "engines" / filename), "face_swap_studio/engines")
    for filename in ("facefusion_worker.py", "facefusion_protocol.py")
]
binaries = []
hiddenimports = []
# The application uses a separately installed camera component; no GPL camera
# Python package or third-party face engine is collected into this bundle.

a = Analysis(
    [str(root / "packaging" / "run_app.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "ruff", "PyInstaller", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FaceSwapStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    version=str(root / "build" / "packaging" / "version_info.txt"),
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="FaceSwapStudio",
)
