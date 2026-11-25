"""Freeze Bandar into an unpacked Linux bundle (build/onedir/Bandar) with PyInstaller."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

from linux_build_support import BUILD_TARGET, require_build_host

ROOT = Path(__file__).resolve().parent.parent
BUNDLED = ["PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6", "PyInstaller"]


def collect_licenses():
    output = ROOT / "build" / "licenses"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    notices = ["Bandar bundles these third-party components:", ""]
    for name in BUNDLED:
        package = distribution(name)
        notices.append(f"{package.metadata['Name']} {package.version}")
        for file in package.files or []:
            if any(part.lower().startswith(("license", "copying")) for part in file.parts):
                source = Path(package.locate_file(file))
                if source.is_file():
                    target = output / name / str(file)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    notices += ["", "Noto Sans Arabic: bandar/web/fonts/LICENSE.txt"]
    (output / "THIRD-PARTY.txt").write_text("\n".join(notices) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local", action="store_true", help="build on any Linux host (no 24.04 check)"
    )
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() != "x86_64":
        parser.error("This build targets Linux x86_64.")
    if not args.local:
        require_build_host()
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    target = BUILD_TARGET if not args.local else {**BUILD_TARGET, "local": True}
    (build / "build-platform.json").write_text(json.dumps(target) + "\n")
    collect_licenses()
    env = {**os.environ, "PYINSTALLER_CONFIG_DIR": str(build / "pyinstaller-cache")}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--log-level=WARN",
            "--distpath",
            str(build / "onedir"),
            "--workpath",
            str(build / "pyinstaller"),
            str(ROOT / "packaging" / "bandar.spec"),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    print(f"Built: {build / 'onedir/Bandar/Bandar'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
