"""Local port probing and ownership lookup. No Qt here.

``is_free`` mirrors how kubectl binds (SO_REUSEADDR, every requested address),
so a port reported free is one kubectl can actually listen on. ``owner`` reads
Linux ``/proc`` and is slow enough that callers run it off the UI thread.
"""

from __future__ import annotations

import errno
import os
import signal
import socket
from pathlib import Path

LISTEN = "0A"


def _bind_targets(address: str):
    for part in (item.strip() for item in address.split(",")):
        if part == "localhost":
            yield socket.AF_INET, "127.0.0.1"
            if socket.has_ipv6:
                yield socket.AF_INET6, "::1"
        elif ":" in part:
            yield socket.AF_INET6, part
        else:
            yield socket.AF_INET, part


def status(port: int, address: str = "127.0.0.1") -> str:
    """``free``, ``busy`` (already bound), ``denied`` (privileged port) or
    ``unavailable`` (the address does not belong to this machine)."""
    for family, host in _bind_targets(address):
        probe = socket.socket(family, socket.SOCK_STREAM)
        try:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, port))
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                return "busy"
            # An IPv6 loopback that is disabled is not a conflict for "localhost".
            if family == socket.AF_INET6 and host == "::1":
                continue
            if error.errno in (errno.EACCES, errno.EPERM):
                return "denied"
            return "unavailable"
        finally:
            probe.close()
    return "free"


def is_free(port: int, address: str = "127.0.0.1") -> bool:
    return status(port, address) == "free"


def _listening_inodes(port: int) -> set:
    inodes = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            rows = Path(table).read_text().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) < 10 or fields[3] != LISTEN:
                continue
            if int(fields[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(fields[9])
    return inodes


def owner(port: int):
    """Describe the process listening on ``port``: ``{pid, name, command, ours}``.

    ``pid`` is ``None`` when the socket belongs to another user or the kernel.
    Returns ``None`` when nothing listens on the port.
    """
    inodes = _listening_inodes(port)
    if not inodes:
        return None
    targets = {f"socket:[{inode}]" for inode in inodes}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for descriptor in (entry / "fd").iterdir():
                if os.readlink(descriptor) in targets:
                    return _describe(int(entry.name))
        except OSError:
            continue
    return {"pid": None, "name": "", "command": "", "ours": False}


def _describe(pid: int):
    try:
        name = Path(f"/proc/{pid}/comm").read_text().strip()
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        command = " ".join(part.decode(errors="replace") for part in argv if part)
    except OSError:
        name, command = "", ""
    stale_forward = "kubectl" in name and "port-forward" in command
    return {"pid": pid, "name": name, "command": command[:400], "ours": stale_forward}


def release(port: int) -> dict:
    """Stop a leftover ``kubectl port-forward`` holding ``port``.

    Refuses anything else: a local database on the same port is never killed.
    """
    holder = owner(port)
    if not holder:
        return {"ok": True}
    if not holder["ours"] or not holder["pid"]:
        return {"ok": False, "code": "not_kubectl", "owner": holder}
    try:
        os.kill(holder["pid"], signal.SIGTERM)
    except ProcessLookupError:
        return {"ok": True}
    except PermissionError:
        return {"ok": False, "code": "permission", "owner": holder}
    return {"ok": True, "owner": holder}


def suggest(preferred: int, taken: set, address: str = "127.0.0.1") -> int:
    """The first port from ``preferred`` upward that is neither configured nor bound."""
    port = max(1024, min(65535, preferred))
    for candidate in list(range(port, 65536)) + list(range(1024, port)):
        if candidate not in taken and is_free(candidate, address):
            return candidate
    return 0
