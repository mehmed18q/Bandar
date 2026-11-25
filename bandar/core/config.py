"""Validate, normalize and atomically persist the JSON configuration. No Qt here.

Hand-edited files are repaired field by field: one bad value never discards the
rest. Identifiers are stable so running forwards survive renames; a service may
also name its group by the group's name, which is rewritten to the group's id.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import math
import os
import re
import secrets
import tempfile
import time
from pathlib import Path

SCHEMA = 1
LANGUAGES = ("en", "fa", "ar")
THEMES = ("auto", "light", "dark")
PALETTES = ("ocean", "forest", "violet", "rose", "amber", "slate")
ENVIRONMENTS = ("", "production", "staging", "development", "testing", "legacy")
GROUP_COLORS = ("blue", "teal", "green", "amber", "orange", "red", "pink", "violet", "slate")
DENSITIES = ("comfortable", "compact")
STARTUP = ("restore", "manual")
NOTIFICATIONS = ("always", "background", "off")
CLOSE_ACTIONS = ("ask", "background", "quit")
VIEWS = ("all", "pinned", "running", "problems", "stopped", "healthy", "connecting", "errors")
UNGROUPED = "__ungrouped__"
SORT_KEYS = ("", "name", "context", "namespace", "status", "uptime", "local", "remote", "restarts")
KINDS = ("service", "pod", "deployment", "statefulset", "replicaset")
KIND_PREFIX = {
    "service": "svc",
    "pod": "pod",
    "deployment": "deploy",
    "statefulset": "sts",
    "replicaset": "rs",
}
KIND_ALIASES = {
    alias: kind
    for kind, aliases in {
        "service": ("svc", "service", "services"),
        "pod": ("po", "pod", "pods"),
        "deployment": ("deploy", "deployment", "deployments"),
        "statefulset": ("sts", "statefulset", "statefulsets"),
        "replicaset": ("rs", "replicaset", "replicasets"),
    }.items()
    for alias in aliases
}

DEFAULT_SETTINGS = {
    "language": "en",
    "theme": "auto",
    "palette": "ocean",
    "density": "comfortable",
    "kubectl": "kubectl",
    "kubeconfig": "",
    "autoRetry": True,
    "maxRetries": 0,
    "retryMaxDelay": 30,
    "startTimeout": 20,
    "healthCheckInterval": 0,
    "clusterCheckInterval": 10,
    "startup": "restore",
    "closeAction": "ask",
    "confirmDelete": True,
    "notifications": "always",
    "sortKey": "",
    "sortDir": "asc",
    "sidebarCollapsed": False,
    "ungroupedCollapsed": False,
    # The list view the window shows, restored on the next launch.
    "view": "all",
    "viewGroup": "",
    "viewEnv": "",
}
_CHOICES = {
    "language": LANGUAGES,
    "theme": THEMES,
    "palette": PALETTES,
    "density": DENSITIES,
    "startup": STARTUP,
    "notifications": NOTIFICATIONS,
    "closeAction": CLOSE_ACTIONS,
    "view": VIEWS,
    "viewEnv": ENVIRONMENTS,
    "sortKey": SORT_KEYS,
    "sortDir": ("asc", "desc"),
}
_NUMBERS = {
    "maxRetries": (0, 1000),
    "retryMaxDelay": (2, 600),
    "startTimeout": (5, 300),
    "healthCheckInterval": (0, 3600),
    "clusterCheckInterval": (0, 600),
}
_FLAGS = (
    "autoRetry",
    "confirmDelete",
    "sidebarCollapsed",
    "ungroupedCollapsed",
)

NAME_LIMIT = 64
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_K8S_NAME = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")
_NAMESPACE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_PORT_NAME = re.compile(r"^(?=.*[a-z])[a-z0-9]([a-z0-9-]{0,13}[a-z0-9])?$")
_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
# A logo name, "i:<glyph>", "env:<environment>" or "emoji:<an emoji or two characters>".
_ICON = re.compile(
    r"^(?:[a-z0-9-]{1,40}|i:[a-z0-9-]{1,48}|env:[a-z]{1,16}|emoji:[^\s\x00-\x1f\x7f]{1,16})$"
)


class ConfigError(Exception):
    """The file exists but cannot be used; ``detail`` is shown to the user."""

    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


def default_path() -> Path:
    override = os.environ.get("BANDAR_CONFIG")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "bandar" / "config.json"


def kubeconfig_path(settings: dict, environ=None) -> Path:
    """The kubeconfig kubectl reads: the setting, then $KUBECONFIG's first entry, then ~/.kube/config."""
    environ = os.environ if environ is None else environ
    if settings.get("kubeconfig"):
        return Path(settings["kubeconfig"]).expanduser()
    first = next((p for p in environ.get("KUBECONFIG", "").split(os.pathsep) if p), "")
    return Path(first).expanduser() if first else Path.home() / ".kube" / "config"


def empty() -> dict:
    return {
        "version": SCHEMA,
        "settings": dict(DEFAULT_SETTINGS),
        "groups": [],
        "services": [],
        "session": {"running": []},
    }


def new_id(prefix: str, taken) -> str:
    while True:
        candidate = f"{prefix}_{secrets.token_hex(4)}"
        if candidate not in taken:
            return candidate


def clean_text(value, limit=NAME_LIMIT) -> str:
    if not isinstance(value, str):
        return ""
    return _CONTROL.sub("", value).strip()[:limit]


def unique_name(name: str, taken) -> str:
    """Return ``name`` or the first free ``name-N``; comparison ignores case."""
    folded = {item.casefold() for item in taken}
    if name.casefold() not in folded:
        return name
    index = 2
    while f"{name}-{index}".casefold() in folded:
        index += 1
    return f"{name}-{index}"


def bounded(value, default, minimum, maximum):
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return int(max(minimum, min(maximum, number)))


def normalize_settings(values) -> dict:
    values = values if isinstance(values, dict) else {}
    result = dict(DEFAULT_SETTINGS)
    for key, options in _CHOICES.items():
        if values.get(key) in options:
            result[key] = values[key]
    for key in _FLAGS:
        if isinstance(values.get(key), bool):
            result[key] = values[key]
    if isinstance(values.get("notifications"), bool):  # files from 1.0.0 stored a flag
        result["notifications"] = "always" if values["notifications"] else "off"
    if values.get("closeToTray") is False and "closeAction" not in values:  # 1.0.0
        result["closeAction"] = "quit"
    for key, (low, high) in _NUMBERS.items():
        result[key] = bounded(values.get(key), DEFAULT_SETTINGS[key], low, high)
    for key in ("healthCheckInterval", "clusterCheckInterval"):
        if 0 < result[key] < 5:
            result[key] = 5
    view_group = values.get("viewGroup")
    if isinstance(view_group, str) and (view_group == UNGROUPED or _ID.match(view_group)):
        result["viewGroup"] = view_group  # checked against the groups in normalize()
    for key in ("kubectl", "kubeconfig"):
        text = clean_text(values.get(key), 1024)
        if text or key == "kubeconfig":
            result[key] = text
    return result


def parse_port(value):
    """Return an int port, or ``None``. Booleans and fractions are rejected."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int) and 1 <= value <= 65535:
        return value
    return None


def parse_remote_port(value):
    """Remote ports may be numbers or a named container/service port."""
    port = parse_port(value)
    if port is not None:
        return port
    if isinstance(value, str) and _PORT_NAME.match(value.strip()):
        return value.strip()
    return None


def valid_address(value: str) -> bool:
    parts = [part.strip() for part in value.split(",")]
    if not parts or len(parts) > 4:
        return False
    for part in parts:
        if part == "localhost":
            continue
        try:
            ipaddress.ip_address(part)
        except ValueError:
            return False
    return True


def valid_context(value: str) -> bool:
    return len(value) <= 253 and not re.search(r"\s", value) and not _CONTROL.search(value)


def icon_key(value) -> str:
    """An icon name from the interface's catalog, or "" (services then guess one)."""
    return value if isinstance(value, str) and _ICON.match(value) else ""


def _args(value) -> list:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item and "\x00" not in item][:24]


def _service(raw, groups_by_key, taken_ids, taken_names):
    """Lenient repair for persisted services. Returns ``None`` when unusable."""
    if not isinstance(raw, dict):
        return None
    name = clean_text(raw.get("name"))
    target = clean_text(raw.get("target"), 253)
    local = parse_port(raw.get("localPort"))
    remote = parse_remote_port(raw.get("remotePort"))
    if not name or not target or re.search(r"\s", target) or local is None or remote is None:
        return None
    sid = raw.get("id") if isinstance(raw.get("id"), str) and _ID.match(raw["id"]) else ""
    if not sid or sid in taken_ids:
        sid = new_id("s", taken_ids)
    taken_ids.add(sid)
    name = unique_name(name, taken_names)
    taken_names.append(name)
    group = raw.get("group") if isinstance(raw.get("group"), str) else ""
    group = groups_by_key.get(group) or groups_by_key.get(group.casefold(), "")
    context = clean_text(raw.get("context"), 253)
    namespace = clean_text(raw.get("namespace"), 63)
    address = clean_text(raw.get("address"), 200) or "127.0.0.1"
    return {
        "id": sid,
        "name": name,
        "group": group,
        "context": context if valid_context(context) else "",
        "namespace": namespace if _NAMESPACE.match(namespace) else "",
        "kind": KIND_ALIASES.get(str(raw.get("kind", "")).lower(), "service"),
        "target": target,
        "localPort": local,
        "remotePort": remote,
        "address": address if valid_address(address) else "127.0.0.1",
        "extraArgs": _args(raw.get("extraArgs")),
        "autoStart": raw.get("autoStart") is True,
        "pinned": raw.get("pinned") is True,
        "icon": icon_key(raw.get("icon")),
        "note": clean_text(raw.get("note"), 300),
    }


def normalize(raw) -> dict:
    """Return a fresh, complete configuration containing only supported fields."""
    raw = raw if isinstance(raw, dict) else {}
    config = empty()
    config["settings"] = normalize_settings(raw.get("settings"))
    group_ids, group_names, groups_by_key = set(), [], {}
    for item in raw.get("groups") if isinstance(raw.get("groups"), list) else []:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"))
        if not name:
            continue
        gid = item.get("id") if isinstance(item.get("id"), str) and _ID.match(item["id"]) else ""
        if not gid or gid in group_ids:
            gid = new_id("g", group_ids)
        group_ids.add(gid)
        name = unique_name(name, group_names)
        group_names.append(name)
        groups_by_key[gid] = gid
        groups_by_key.setdefault(name.casefold(), gid)
        config["groups"].append(
            {
                "id": gid,
                "name": name,
                "color": item.get("color") if item.get("color") in GROUP_COLORS else "blue",
                "collapsed": item.get("collapsed") is True,
                "environment": item.get("environment")
                if item.get("environment") in ENVIRONMENTS
                else "",
                "pinned": item.get("pinned") is True,
                "icon": icon_key(item.get("icon")),
                "note": clean_text(item.get("note"), 300),
            }
        )
    service_ids, service_names = set(), []
    for item in raw.get("services") if isinstance(raw.get("services"), list) else []:
        service = _service(item, groups_by_key, service_ids, service_names)
        if service:
            config["services"].append(service)
    session = raw.get("session") if isinstance(raw.get("session"), dict) else {}
    running = session.get("running") if isinstance(session.get("running"), list) else []
    config["session"]["running"] = [sid for sid in dict.fromkeys(running) if sid in service_ids]
    if config["settings"]["viewGroup"] not in group_ids | {UNGROUPED}:
        config["settings"]["viewGroup"] = ""  # the remembered group was deleted
    return config


def _error(code, **params):
    return {"code": code, **params}


def _addresses(value: str) -> set:
    result = set()
    for part in value.split(","):
        part = part.strip()
        if part == "localhost":
            result |= {"127.0.0.1", "::1"}
        else:
            result.add(str(ipaddress.ip_address(part)))
    return result


def addresses_overlap(first: str, second: str) -> bool:
    """Bind address lists collide when they share an address or either one is a wildcard."""
    try:
        left, right = _addresses(first), _addresses(second)
    except ValueError:
        return True
    wildcard = {"0.0.0.0", "::"}
    return bool(left & right or left & wildcard or right & wildcard)


def port_holder(services, port: int, address: str, exclude=None):
    """Return the configured service that already claims ``address:port``, if any.

    Ownership is about configuration, not process state: two services must never
    share a local port even while both are stopped.
    """
    for service in services:
        if service["id"] == exclude or service["localPort"] != port:
            continue
        if addresses_overlap(service["address"], address):
            return service
    return None


def validate_service(data, config, editing=None):
    """Strict validation for the add/edit form. Returns ``(service, errors)``.

    ``errors`` maps a field name to ``{"code": ..., **params}`` for translation.
    """
    data = data if isinstance(data, dict) else {}
    errors = {}
    others = [item for item in config["services"] if item["id"] != editing]
    name = clean_text(data.get("name"))
    if not name:
        errors["name"] = _error("required")
    elif any(item["name"].casefold() == name.casefold() for item in others):
        errors["name"] = _error("duplicate_service")
    group = data.get("group") if isinstance(data.get("group"), str) else ""
    if group and group not in {item["id"] for item in config["groups"]}:
        errors["group"] = _error("missing_group")
    context = clean_text(data.get("context"), 253)
    if not valid_context(context):
        errors["context"] = _error("invalid_context")
    namespace = clean_text(data.get("namespace"), 253)
    if namespace and not (len(namespace) <= 63 and _NAMESPACE.match(namespace)):
        errors["namespace"] = _error("invalid_namespace")
    kind = KIND_ALIASES.get(str(data.get("kind", "")).lower())
    if not kind:
        errors["kind"] = _error("invalid_kind")
    target = clean_text(data.get("target"), 300)
    if not target:
        errors["target"] = _error("required")
    elif len(target) > 253 or not _K8S_NAME.match(target):
        errors["target"] = _error("invalid_target")
    remote = parse_remote_port(data.get("remotePort"))
    if remote is None:
        errors["remotePort"] = _error("invalid_remote_port")
    address = clean_text(data.get("address"), 200) or "127.0.0.1"
    if not valid_address(address):
        errors["address"] = _error("invalid_address")
    local = parse_port(data.get("localPort"))
    if local is None:
        errors["localPort"] = _error("invalid_port")
    elif "address" not in errors:
        holder = port_holder(config["services"], local, address, exclude=editing)
        if holder:
            errors["localPort"] = _error("port_taken", service=holder["name"])
    extra = data.get("extraArgs")
    if isinstance(extra, str):
        from bandar.core.commands import split_args  # local import avoids a cycle

        try:
            extra = split_args(extra)
        except ValueError:
            errors["extraArgs"] = _error("invalid_args")
            extra = []
    extra = _args(extra)
    if extra and not extra[0].startswith("-"):
        errors["extraArgs"] = _error("args_must_be_flags")
    elif "port-forward" in extra:
        errors["extraArgs"] = _error("invalid_args")
    if errors:
        return None, errors
    current = next((item for item in config["services"] if item["id"] == editing), None)
    taken = {item["id"] for item in config["services"]}
    return {
        "id": current["id"] if current else new_id("s", taken),
        "name": name,
        "group": group,
        "context": context,
        "namespace": namespace,
        "kind": kind,
        "target": target,
        "localPort": local,
        "remotePort": remote,
        "address": address,
        "extraArgs": extra,
        "autoStart": data.get("autoStart") is True,
        "pinned": bool(current and current.get("pinned")),
        "icon": icon_key(data.get("icon")),
        "note": clean_text(data.get("note"), 300),
    }, {}


def validate_group(data, config, editing=None):
    data = data if isinstance(data, dict) else {}
    name = clean_text(data.get("name"))
    if not name:
        return None, {"name": _error("required")}
    if any(
        item["name"].casefold() == name.casefold() and item["id"] != editing
        for item in config["groups"]
    ):
        return None, {"name": _error("duplicate_group")}
    current = next((item for item in config["groups"] if item["id"] == editing), None)
    taken = {item["id"] for item in config["groups"]}
    return {
        "id": current["id"] if current else new_id("g", taken),
        "name": name,
        "color": data.get("color") if data.get("color") in GROUP_COLORS else "blue",
        "collapsed": current["collapsed"] if current else False,
        "environment": data.get("environment") if data.get("environment") in ENVIRONMENTS else "",
        "pinned": bool(current and current.get("pinned")),
        "icon": icon_key(data.get("icon")),
        "note": clean_text(data.get("note"), 300),
    }, {}


def move_before(items: list, item_id: str, before_id) -> list:
    """Return ``items`` with ``item_id`` moved in front of ``before_id`` (or to the end)."""
    moving = next((item for item in items if item["id"] == item_id), None)
    if moving is None or item_id == before_id:
        return list(items)
    rest = [item for item in items if item["id"] != item_id]
    index = next((i for i, item in enumerate(rest) if item["id"] == before_id), len(rest))
    return rest[:index] + [moving] + rest[index:]


def sorted_by_name(items: list, ids=None) -> list:
    """Sort the items whose id is in ``ids`` (all when ``None``) by name, keeping
    every other item in place. Lets one group be sorted without touching others."""
    chosen = [item for item in items if ids is None or item["id"] in ids]
    ordered = iter(sorted(chosen, key=lambda item: item["name"].casefold()))
    return [next(ordered) if ids is None or item["id"] in ids else item for item in items]


def dumps(config) -> str:
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"


def parse(text: str) -> dict:
    """Parse and normalize file contents, raising ConfigError for invalid JSON."""
    try:
        raw = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as error:
        raise ConfigError(f"line {error.lineno}, column {error.colno}: {error.msg}") from None
    if not isinstance(raw, dict):
        raise ConfigError("the top level must be a JSON object")
    return normalize(raw)


def load(path: Path):
    """Return ``(config, notice)``.

    A file that cannot be read or parsed is left untouched and reported with
    ``readOnly``: nothing is written until the user fixes it (Bandar reloads it
    automatically) or explicitly resets it.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return empty(), None
    except (OSError, UnicodeDecodeError) as error:
        return empty(), {"code": "config_unreadable", "detail": str(error), "readOnly": True}
    try:
        return parse(text), None
    except ConfigError as error:
        return empty(), {"code": "config_invalid", "detail": error.detail, "readOnly": True}


def backup(path: Path) -> Path:
    """Move ``path`` aside with a timestamped name and return the new location."""
    target = path.with_name(f"{path.name}.backup-{time.strftime('%Y%m%d-%H%M%S')}")
    os.replace(path, target)
    return target


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        else:
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
