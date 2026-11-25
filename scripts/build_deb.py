"""Build the installable Debian/Ubuntu package with desktop entry and themed icons."""

from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys
from hashlib import md5, sha256
from pathlib import Path

from linux_build_support import DEBIAN_REVISION, validate_bundle

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bandar import APP_ID, APP_NAME, REPOSITORY, VERSION  # noqa: E402

DEPENDS = (
    "libc6 (>= 2.39), libgl1, libegl1, libnss3, libasound2t64 | libasound2, libdbus-1-3, "
    "libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, "
    "libxcomposite1, libxdamage1, libxtst6, desktop-file-utils, hicolor-icon-theme"
)


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def write_icons(staging):
    """Vector and raster icons under the application ID, as desktops look them up."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # rendering needs no display
    QGuiApplication.instance() or QGuiApplication(["build"])
    source = ROOT / "bandar/web/icon.svg"
    renderer = QSvgRenderer(str(source))
    theme = staging / "usr/share/icons/hicolor"
    copy(source, theme / f"scalable/apps/{APP_ID}.svg")
    for size in (16, 22, 24, 32, 48, 64, 128, 256, 512):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        target = theme / f"{size}x{size}/apps/{APP_ID}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(target)):
            raise RuntimeError(f"Could not write {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="reuse build/onedir/Bandar")
    parser.add_argument("--local", action="store_true", help="package for this machine only")
    args = parser.parse_args()
    if not args.skip_build:
        command = [sys.executable, str(ROOT / "scripts/build_linux.py")]
        subprocess.run(command + (["--local"] if args.local else []), check=True)
    bundle = ROOT / "build/onedir/Bandar"
    reported = subprocess.check_output(
        [str(bundle / "Bandar"), "--version"], text=True, env={"QT_QPA_PLATFORM": "offscreen"}
    ).strip()
    if reported != f"{APP_NAME} {VERSION}":
        parser.error(f"The bundle reports {reported!r}, expected {APP_NAME} {VERSION}")
    glibc = validate_bundle(bundle, local=args.local)
    version = f"{VERSION}-{DEBIAN_REVISION}"
    staging = ROOT / "build/deb" / f"bandar_{version}_amd64"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(bundle, staging / "opt/bandar", symlinks=True)
    (staging / "usr/bin").mkdir(parents=True)
    (staging / "usr/bin/bandar").symlink_to("/opt/bandar/Bandar")
    desktop = staging / f"usr/share/applications/{APP_ID}.desktop"
    copy(ROOT / f"packaging/{APP_ID}.desktop", desktop)
    subprocess.run(["desktop-file-validate", str(desktop)], check=True)
    write_icons(staging)
    copy(ROOT / "README.md", staging / "usr/share/doc/bandar/README.md")
    copy(ROOT / "CHANGELOG.md", staging / "usr/share/doc/bandar/CHANGELOG.md")
    files = sorted(p for p in staging.rglob("*") if p.is_file() and not p.is_symlink())
    size = math.ceil(sum(p.stat().st_size for p in files) / 1024)
    control = staging / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        f"Package: bandar\nVersion: {version}\nArchitecture: amd64\n"
        "Section: devel\nPriority: optional\n"
        "Maintainer: Sadeq Kiomarsi <noreply@github.com>\n"
        f"Homepage: {REPOSITORY}\n"
        f"Installed-Size: {size}\n"
        f"Depends: {DEPENDS}\n"
        "Recommends: kubectl | kubernetes-client, libnotify-bin\n"
        "Description: Bandar - desktop manager for kubectl port-forwards\n"
        " Keep every kubectl port-forward in one window: named services in groups,\n"
        " live status, automatic reconnection and clear, actionable errors.\n"
        " Includes its own Python and Qt runtime.\n",
        encoding="utf-8",
    )
    sums = []
    for path in files:
        digest = md5(usedforsecurity=False)
        with path.open("rb") as stream:
            for chunk in iter(lambda s=stream: s.read(1 << 20), b""):
                digest.update(chunk)
        sums.append(f"{digest.hexdigest()}  {path.relative_to(staging)}")
    (control / "md5sums").write_text("\n".join(sums) + "\n", encoding="utf-8")
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    package = destination / f"bandar_{version}_amd64.deb"
    subprocess.run(
        ["dpkg-deb", "--root-owner-group", "-Zxz", "-z6", "--build", str(staging), str(package)],
        check=True,
    )
    checksum = sha256(package.read_bytes()).hexdigest()
    package.with_name(package.name + ".sha256").write_text(f"{checksum}  {package.name}\n")
    print(f"Package: {package} (needs GLIBC {glibc})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
