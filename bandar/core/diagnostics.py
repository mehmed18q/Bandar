"""Classify kubectl output into stable, translatable problems. No Qt here.

Each rule pairs a pattern with a code and a retry decision. The first matching
rule wins, so specific causes are listed before generic network failures.
Retryable problems are transient (a rollout, a dropped tunnel, an unreachable
API server); the rest need the user to change something first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    code: str
    retryable: bool
    detail: str = ""

    def as_dict(self, **params):
        return {"code": self.code, "retryable": self.retryable, "detail": self.detail, **params}


@dataclass(frozen=True)
class Rule:
    code: str
    retryable: bool
    pattern: re.Pattern


def _rule(code, retryable, *patterns):
    return Rule(code, retryable, re.compile("|".join(patterns), re.IGNORECASE))


RULES = (
    _rule(
        "port_in_use",
        False,
        r"address already in use",
        r"unable to listen on any of the requested ports",
        r"unable to create listener",
    ),
    _rule("context_missing", False, r'context "[^"]*" does not exist', r"no context exists"),
    _rule("kubeconfig_invalid", False, r"error loading config file", r"invalid configuration"),
    _rule("namespace_missing", False, r'namespaces? "[^"]*" not found'),
    _rule(
        "auth",
        False,
        r"\bforbidden\b",
        r"\bunauthorized\b",
        r"you must be logged in",
        r"provide credentials",
        r"certificate (has )?expired",
        r"x509:",
        r"exec plugin",
        r"token (is )?expired",
    ),
    _rule(
        "remote_port_missing",
        False,
        r"does not have a (named )?port",
        r"does not have a service port",
        r"unable to find (a )?port",
        r"(container )?port .* not found",
    ),
    _rule(
        "pod_not_ready",
        True,
        r"pod is not running",
        r"unable to forward port because pod is not running",
        r"status=pending",
        r"no ready pods",
        r"timed out waiting for the condition",
        r"pod .* (is )?(terminating|being deleted)",
        r'pods? "[^"]*" not found',
    ),
    _rule(
        "target_missing",
        False,
        r'\w+(\.\w+)* "[^"]*" not found',
        r"the server doesn't have a resource type",
    ),
    _rule(
        "invalid_command",
        False,
        r"unknown flag",
        r"unknown shorthand",
        r"invalid port",
        r"error: TYPE/NAME",
    ),
    _rule(
        "connection_lost",
        True,
        r"lost connection to pod",
        r"error creating (error|forwarding) stream",
        r"connection reset by peer",
        r"broken pipe",
        r"use of closed network connection",
        r"error upgrading connection",
        r"\bunexpected eof\b",
        r"http2: client connection lost",
        r"timeout occurred",
    ),
    _rule(
        "api_unreachable",
        True,
        r"unable to connect to the server",
        r"dial tcp",
        r"i/o timeout",
        r"no such host",
        r"tls handshake timeout",
        r"network is unreachable",
        r"no route to host",
        r"connection refused",
        r"context deadline exceeded",
        r"timeout exceeded",
        r"handshake timeout",
        r"the server is currently unable",
        r"service unavailable",
    ),
)

# While a tunnel is healthy, kubectl reports failed individual connections and
# keeps running. These become warnings, unless they mean the tunnel itself died.
_PER_CONNECTION = re.compile(r"an error occurred forwarding", re.IGNORECASE)
_REMOTE_REFUSED = re.compile(r"connect: connection refused|failed to connect to localhost", re.I)
_KLOG_PREFIX = re.compile(r"^[EWIF]\d{4} \d\d:\d\d:\d\d\.\d+\s+\d+\s+[\w.-]+:\d+\]\s*")


def clean_line(line: str) -> str:
    """Strip klog headers and the ``error:`` prefix so messages read naturally."""
    line = _KLOG_PREFIX.sub("", line.strip())
    return re.sub(r"^error:\s*", "", line, flags=re.IGNORECASE)


def classify(text: str) -> Problem:
    detail = summarize(text)
    for rule in RULES:
        if rule.pattern.search(text):
            return Problem(rule.code, rule.retryable, detail)
    return Problem("unknown", True, detail)


def summarize(text: str) -> str:
    """Pick the most informative line: the last one that looks like an error."""
    lines = [clean_line(line) for line in text.splitlines() if line.strip()]
    lines = [line for line in lines if line]
    for line in reversed(lines):
        if re.search(r"error|unable|fail|denied|forbidden|not found|refused|lost", line, re.I):
            return line[:600]
    return lines[-1][:600] if lines else ""


_UNREACHABLE_NOW = re.compile(
    r"no route to host|network is unreachable|no such host|connection refused|"
    r"server misbehaving|name resolution",
    re.IGNORECASE,
)


def definitely_unreachable(text: str) -> bool:
    """Errors that prove the cluster cannot be reached (as opposed to a slow answer)."""
    return bool(_UNREACHABLE_NOW.search(text))


def runtime_event(line: str):
    """Classify a stderr line printed while the tunnel is up.

    Returns ``("fatal", Problem)`` when the tunnel is broken and must be rebuilt,
    ``("warning", Problem)`` for a single failed client connection, else ``None``.
    """
    if _PER_CONNECTION.search(line):
        if _REMOTE_REFUSED.search(line):
            return "warning", Problem("remote_refused", True, clean_line(line)[:600])
        problem = classify(line)
        if problem.code == "connection_lost":
            return "fatal", problem
        return "warning", Problem("connection_failed", True, problem.detail)
    problem = classify(line)
    if problem.code in {"connection_lost", "api_unreachable", "pod_not_ready"}:
        return "fatal", problem
    return None
