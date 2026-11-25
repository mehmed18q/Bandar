# Build with scripts/build_linux.py, which prepares build/licenses and the build record.
from pathlib import Path

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    datas=[
        (str(root / "bandar" / "web"), "bandar/web"),
        (str(root / "build" / "licenses"), "licenses"),
        (str(root / "build" / "build-platform.json"), "."),
    ],
    hiddenimports=["PySide6.QtWebChannel", "PySide6.QtNetwork"],
    excludes=["tkinter", "unittest", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Bandar",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Bandar", strip=False, upx=False)
