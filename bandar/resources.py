"""Locations of bundled files, valid for source runs and frozen builds alike."""

import sys
from pathlib import Path

PACKAGE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "bandar"
WEB = PACKAGE / "web"
ICON = WEB / "icon.svg"
