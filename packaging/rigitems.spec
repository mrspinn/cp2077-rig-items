# PyInstaller spec: one-file app for Windows (windowed .exe) and Linux.
# Build from the repo root:  pyinstaller packaging/rigitems.spec
import sys
from pathlib import Path

root = Path(SPECPATH).parent
windows = sys.platform == "win32"

a = Analysis(
    [str(root / "packaging/app.py")],
    pathex=[str(root)],
    datas=[(str(root / "rigitems/data"), "rigitems/data")],
    hiddenimports=["rigitems.gui"],   # imported lazily by cli
    excludes=["numpy", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="RigItems",
    console=not windows,   # Linux keeps a console so the CLI still prints; Windows opens just the window
    upx=False,
    icon=str(root / "packaging/rigitems.ico"),
)
