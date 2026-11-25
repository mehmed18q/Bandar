"""Desktop integration: the taskbar shows "Bandar" with its icon, not "python".

Desktops match a window to an application by its ID (Wayland app_id, set from
``QGuiApplication.desktopFileName``) or by WM_CLASS on X11. Both need an installed
desktop entry named after ``APP_ID``. Packages install one system-wide; a run from
a source checkout installs a per-user entry pointing at ``bandar.sh``.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from bandar import APP_ID, APP_NAME
from bandar.resources import ICON

ENTRY = """[Desktop Entry]
Type=Application
Version=1.0
Name={name}
GenericName=Port-forward manager
Comment=Manage kubectl port-forwards with live status and automatic reconnection
Exec={command}
TryExec={try_exec}
Icon={app_id}
Terminal=false
Categories=Development;
StartupNotify=true
StartupWMClass={name}
Keywords=kubectl;kubernetes;k8s;port-forward;tunnel;
"""


def desktop_entry(command: Path) -> str:
    return ENTRY.format(
        name=APP_NAME, app_id=APP_ID, command=shlex.quote(str(command)), try_exec=command
    )


def _write_if_changed(path: Path, data: bytes) -> bool:
    try:
        if path.is_file() and path.read_bytes() == data:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)
        return True
    except OSError:
        return False


def register_source_run(
    root: Path, data_home: Path | None = None, system: Path = Path("/usr/share/applications")
) -> bool:
    """Install or refresh the per-user desktop entry and icon. Returns True if anything changed.

    Skipped for frozen builds and when a system package already provides the entry.
    """
    launcher = root / "bandar.sh"
    if getattr(sys, "frozen", False) or not launcher.is_file():
        return False
    if (system / f"{APP_ID}.desktop").exists():
        return False
    data = data_home or Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    entry = _write_if_changed(
        data / "applications" / f"{APP_ID}.desktop", desktop_entry(launcher).encode()
    )
    icon = _write_if_changed(
        data / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg", ICON.read_bytes()
    )
    return entry or icon
