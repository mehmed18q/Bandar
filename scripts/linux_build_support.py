"""The oldest supported Ubuntu ABI for distributable builds, and checks against it."""

import json
import platform
import re
import subprocess
from pathlib import Path

DEBIAN_REVISION = "1"
BUILD_TARGET = {"distribution": "ubuntu", "release": "24.04", "architecture": "amd64"}
MAX_GLIBC = (2, 39)


def require_build_host():
    info = platform.freedesktop_os_release()
    if (
        info.get("ID") != BUILD_TARGET["distribution"]
        or info.get("VERSION_ID") != BUILD_TARGET["release"]
        or platform.machine() != "x86_64"
    ):
        raise RuntimeError(
            "Release builds require Ubuntu 24.04 amd64. Use: python scripts/build_ubuntu24.py "
            "(or --local for a package for this machine only)"
        )


def audit_glibc(bundle):
    """The newest GLIBC symbol version any bundled ELF file needs."""
    maximum = (0, 0)
    for path in Path(bundle).rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                continue
        symbols = subprocess.check_output(["readelf", "--version-info", str(path)], text=True)
        versions = [
            tuple(map(int, item.split("."))) for item in re.findall(r"GLIBC_(\d+\.\d+)", symbols)
        ]
        maximum = max(maximum, max(versions, default=(0, 0)))
    return maximum


def validate_bundle(bundle, local=False):
    record = Path(bundle) / "_internal/build-platform.json"
    if not local and (not record.is_file() or json.loads(record.read_text()) != BUILD_TARGET):
        raise RuntimeError(
            "Missing Ubuntu 24.04 build record; build with scripts/build_ubuntu24.py"
        )
    required = audit_glibc(bundle)
    if not local and required > MAX_GLIBC:
        raise RuntimeError(f"The bundle needs GLIBC {required}; rebuild on Ubuntu 24.04")
    return ".".join(map(str, required))
