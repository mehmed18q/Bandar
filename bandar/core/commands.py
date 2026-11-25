"""Translate between service records and kubectl command lines. No Qt here.

``parse_kubectl`` accepts what people paste from a terminal. ``plan_import``
reads Bandar's plain-text list format and reports a result for every line
before anything changes; ``export_text`` writes the same format back::

    # comments and blank lines are ignored
    [orders @production]                       <- services below join group "orders"
    orders-postgresql = kubectl --context main -n orders port-forward svc/psql 5432:5432
    kubectl -n orders port-forward svc/redis 6379:6379   <- named after the resource
    []                                       <- back to "no group"
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

from bandar.core import config as cfg

# Global kubectl flags that consume the next token when written without "=".
VALUE_FLAGS = {
    "--address",
    "--as",
    "--as-group",
    "--as-uid",
    "--cache-dir",
    "--certificate-authority",
    "--client-certificate",
    "--client-key",
    "--cluster",
    "--context",
    "--kubeconfig",
    "--namespace",
    "--pod-running-timeout",
    "--request-timeout",
    "--server",
    "--tls-server-name",
    "--token",
    "--user",
    "-n",
    "-s",
    "-v",
}


class CommandError(ValueError):
    """A command that cannot become a service. ``code`` is translated by the UI."""

    def __init__(self, code, **params):
        super().__init__(code)
        self.code = code
        self.params = params

    def as_dict(self):
        return {"code": self.code, **self.params}


def split_args(text: str) -> list:
    """Split shell-style text into arguments; raises ValueError on unbalanced quotes."""
    return shlex.split(text.replace("\\\n", " "), comments=False)


def _is_kubectl(token: str) -> bool:
    return token.rsplit("/", 1)[-1] in {"kubectl", "kubectl.exe", "k", "oc"}


def parse_kubectl(text) -> dict:
    """Return service fields (without ``id``/``name``) from a port-forward command."""
    try:
        tokens = split_args(text) if isinstance(text, str) else list(text)
    except ValueError:
        raise CommandError("unbalanced_quotes") from None
    if tokens and _is_kubectl(tokens[0]):
        tokens = tokens[1:]
    if "port-forward" not in tokens:
        raise CommandError("not_port_forward")
    values = {"context": "", "namespace": "", "address": "127.0.0.1"}
    extra, positional = [], []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        name, has_value, inline = token.partition("=")
        if token.startswith("-n") and len(token) > 2 and not token.startswith("--"):
            name, has_value, inline = "-n", "=", token[2:].removeprefix("=")
        if name.startswith("-"):
            if name in VALUE_FLAGS and not has_value:
                if index + 1 >= len(tokens):
                    raise CommandError("missing_flag_value", flag=name)
                inline = tokens[index + 1]
                index += 1
            if name == "--context":
                values["context"] = inline
            elif name in {"-n", "--namespace"}:
                values["namespace"] = inline
            elif name == "--address":
                values["address"] = inline
            elif name in VALUE_FLAGS:
                extra += [token] if has_value else [name, inline]
            else:
                extra.append(token)
        elif token != "port-forward":
            positional.append(token)
        index += 1
    if not positional:
        raise CommandError("missing_target")
    resource, ports = positional[0], positional[1:]
    kind_alias, slash, target = resource.partition("/")
    if not slash:
        kind_alias, target = "pod", resource
    kind = cfg.KIND_ALIASES.get(kind_alias.lower())
    if not kind:
        raise CommandError("unsupported_kind", kind=kind_alias)
    if not ports:
        raise CommandError("missing_ports")
    if len(ports) > 1:
        raise CommandError("multiple_ports", count=len(ports))
    spec = ports[0]
    if spec.startswith(":"):
        raise CommandError("random_local_port")
    local_text, colon, remote_text = spec.partition(":")
    local = cfg.parse_port(local_text)
    remote = cfg.parse_remote_port(remote_text if colon else local_text)
    if remote is None or local is None:
        raise CommandError("invalid_port_spec", spec=spec)
    return {
        "context": values["context"],
        "namespace": values["namespace"],
        "kind": kind,
        "target": target,
        "localPort": local,
        "remotePort": remote,
        "address": values["address"],
        "extraArgs": extra,
    }


def build_args(service: dict, settings: dict) -> list:
    """kubectl arguments for a service. Global flags first, then the subcommand."""
    args = []
    if settings.get("kubeconfig"):
        args += ["--kubeconfig", settings["kubeconfig"]]
    if service.get("context"):
        args += ["--context", service["context"]]
    if service.get("namespace"):
        args += ["--namespace", service["namespace"]]
    args += [
        "port-forward",
        f"{cfg.KIND_PREFIX[service['kind']]}/{service['target']}",
        f"{service['localPort']}:{service['remotePort']}",
        "--address",
        service.get("address") or "127.0.0.1",
    ]
    return args + list(service.get("extraArgs", []))


def display_command(service: dict, settings: dict) -> str:
    return shlex.join([settings.get("kubectl") or "kubectl", *build_args(service, settings)])


# ---------------------------------------------------------------- import / export

_GROUP_HEADER = re.compile(r"^\[(?P<name>[^\]@]*?)\s*(?:@(?P<env>[a-z]+))?\s*\]$")
_NAMED = re.compile(
    r"^(?P<name>.+?)\s*[=:]\s*(?P<command>(?:\S*/)?(?:kubectl|kubectl\.exe|k|oc)\s.+)$"
)


@dataclass
class ImportLine:
    line: int
    text: str
    action: str  # "add" | "update" | "group" | "skip" | "error"
    name: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class PlannedService:
    name: str
    fields: dict
    group: str | None  # group name, "" for none, None to leave an existing service's group


@dataclass
class ImportPlan:
    services: list = field(default_factory=list)  # PlannedService in file order
    groups: list = field(default_factory=list)  # group names in order of appearance
    environments: dict = field(default_factory=dict)  # group name -> environment
    lines: list = field(default_factory=list)

    def summary(self):
        counts = {}
        for entry in self.lines:
            counts[entry.action] = counts.get(entry.action, 0) + 1
        return counts

    def as_dict(self):
        return {"summary": self.summary(), "lines": [entry.__dict__ for entry in self.lines]}


def _split_named(line: str):
    """``(name, command)`` for a line; the name is empty for a bare kubectl command."""
    first = line.split(None, 1)[0]
    if _is_kubectl(first):
        return "", line
    match = _NAMED.match(line)
    if not match:
        raise CommandError("not_port_forward")
    return cfg.clean_text(match.group("name")), match.group("command")


def plan_import(text: str, config: dict, update_existing=True) -> ImportPlan:
    """Parse a list without touching ``config``. Every meaningful line gets a result."""
    plan = ImportPlan()
    existing = {item["name"].casefold(): item for item in config["services"]}
    planned = {}  # casefolded name -> fields (+ name)
    group = None
    header_line = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or set(line) <= set("=-_*~ "):
            continue
        header = _GROUP_HEADER.match(line)
        if header:
            group = cfg.clean_text(header.group("name"))
            environment = header.group("env") or ""
            if environment not in cfg.ENVIRONMENTS:
                plan.lines.append(
                    ImportLine(
                        number,
                        line,
                        "error",
                        group,
                        {"code": "unknown_environment", "env": environment},
                    )
                )
                group, header_line = None, None
                continue
            if group and group.casefold() not in {g.casefold() for g in plan.groups}:
                plan.groups.append(group)
            if group and environment:
                plan.environments[group.casefold()] = environment
            header_line = ImportLine(number, line, "group", group, {"count": 0, "env": environment})
            plan.lines.append(header_line)
            continue
        try:
            name, command = _split_named(line)
            fields = parse_kubectl(command)
        except CommandError as error:
            plan.lines.append(ImportLine(number, line, "error", detail=error.as_dict()))
            continue
        name = name or fields["target"][: cfg.NAME_LIMIT]
        key = name.casefold()
        clash = _port_clash(fields, name, planned, existing, update_existing)
        if clash:
            plan.lines.append(
                ImportLine(number, line, "error", name, {"code": "port_taken", "service": clash})
            )
            continue
        if key in existing and not update_existing:
            plan.lines.append(ImportLine(number, line, "skip", name, {"code": "exists"}))
            continue
        action = "update" if key in existing or key in planned else "add"
        planned[key] = {**fields, "name": name}
        plan.services = [item for item in plan.services if item.name.casefold() != key]
        plan.services.append(PlannedService(name, fields, group))
        if header_line is not None and group is not None:
            header_line.detail["count"] += 1
        plan.lines.append(ImportLine(number, line, action, name, _describe(fields, group)))
    return plan


def _port_clash(fields, name, planned, existing, update_existing):
    """Name of another service (planned or configured) that owns the same local port."""
    key = name.casefold()
    for other_key, other in planned.items():
        same_port = other_key != key and other["localPort"] == fields["localPort"]
        if same_port and cfg.addresses_overlap(other["address"], fields["address"]):
            return other["name"]
    for other_key, other in existing.items():
        replaced = other_key in planned or (other_key == key and update_existing)
        if other_key == key or replaced:
            continue
        if other["localPort"] == fields["localPort"] and cfg.addresses_overlap(
            other["address"], fields["address"]
        ):
            return other["name"]
    return None


def _describe(fields, group):
    return {
        "context": fields["context"],
        "namespace": fields["namespace"],
        "resource": f"{cfg.KIND_PREFIX[fields['kind']]}/{fields['target']}",
        "ports": f"{fields['localPort']}:{fields['remotePort']}",
        "group": group or "",
    }


def apply_import(plan: ImportPlan, config: dict) -> tuple:
    """Return ``(new_config, changed_ids)``; ``config`` itself is not mutated."""
    result = cfg.normalize(config)
    groups = {item["name"].casefold(): item for item in result["groups"]}
    for group_name in plan.groups:
        environment = plan.environments.get(group_name.casefold())
        if group_name.casefold() in groups:
            if environment:
                groups[group_name.casefold()]["environment"] = environment
            continue
        group, _ = cfg.validate_group({"name": group_name, "environment": environment}, result)
        group["color"] = cfg.GROUP_COLORS[len(result["groups"]) % len(cfg.GROUP_COLORS)]
        result["groups"].append(group)
        groups[group_name.casefold()] = group
    by_name = {item["name"].casefold(): item for item in result["services"]}
    changed = []
    for entry in plan.services:
        group_id = groups[entry.group.casefold()]["id"] if entry.group else ""
        current = by_name.get(entry.name.casefold())
        if current:
            current.update(entry.fields)
            if entry.group is not None:
                current["group"] = group_id
            changed.append(current["id"])
            continue
        service = {
            "id": cfg.new_id("s", {item["id"] for item in result["services"]}),
            "name": entry.name,
            "group": group_id,
            "autoStart": False,
            "note": "",
            **entry.fields,
        }
        result["services"].append(service)
        by_name[entry.name.casefold()] = service
        changed.append(service["id"])
    return cfg.normalize(result), changed


def export_text(config: dict, ids=None, header: str = "") -> str:
    """Write services in the import format, grouped, in configured order."""
    chosen = [s for s in config["services"] if ids is None or s["id"] in ids]
    known = {g["id"] for g in config["groups"]}
    settings = {**config["settings"], "kubectl": "kubectl"}
    lines = [f"# {header}"] if header else []

    def entry(service):
        return f"{service['name']} = {display_command(service, settings)}"

    loose = [s for s in chosen if s["group"] not in known]
    lines += [entry(s) for s in loose]
    for group in config["groups"]:
        members = [s for s in chosen if s["group"] == group["id"]]
        if not members:
            continue
        if len(lines) > (1 if header else 0):
            lines.append("")
        suffix = f" @{group['environment']}" if group.get("environment") else ""
        lines.append(f"[{group['name']}{suffix}]")
        lines += [entry(s) for s in members]
    return "\n".join(lines) + "\n"
