"""Build and check the release package inside Ubuntu 24.04 (Docker), not on the host."""

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "bandar-builder:ubuntu24"
SOURCES = ("bandar", "scripts", "packaging", "tests", "examples")
FILES = (
    "main.py",
    "bandar.sh",
    "README.md",
    "CHANGELOG.md",
    "requirements.txt",
    "requirements-build.txt",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-image-build", action="store_true")
    args = parser.parse_args()
    if not args.skip_image_build:
        subprocess.run(
            ["docker", "build", "-f", "packaging/ubuntu24.Dockerfile", "-t", IMAGE, "."],
            cwd=ROOT,
            check=True,
        )
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ubuntu24-", dir=ROOT / "build") as folder:
        stage = Path(folder)
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "my-services.txt")
        for name in SOURCES:
            shutil.copytree(ROOT / name, stage / name, ignore=ignore)
        for name in FILES:
            shutil.copy2(ROOT / name, stage / name)
        docker = [
            "docker", "run", "--rm", "--init",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--shm-size=1g",
            "--mount", f"type=bind,source={stage},target=/work",
            "-e", "HOME=/tmp",
            "-e", "QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu --no-sandbox",
            IMAGE,
        ]  # fmt: skip
        subprocess.run([*docker, "python", "scripts/build_deb.py"], check=True)
        subprocess.run(
            [
                *docker,
                "xvfb-run",
                "-a",
                "python",
                "tests/bundle_smoke.py",
                "build/onedir/Bandar/Bandar",
            ],
            check=True,
        )
        destination = ROOT / "dist"
        destination.mkdir(exist_ok=True)
        for path in (stage / "dist").iterdir():
            shutil.copy2(path, destination / path.name)
            print(f"Ready: {destination / path.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
