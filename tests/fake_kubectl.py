#!/usr/bin/env python3
"""A stand-in for kubectl so tests never touch a real cluster.

``port-forward`` really listens on the requested local port. The target name
selects a scenario:

    ok-*          print "Forwarding from …" and serve until terminated
    flaky-*       become healthy, then report a lost connection and exit
    once-flaky-*  like flaky the first time (per marker file), healthy afterwards
    auth-*        fail at once with an authorization error
    missing-*     fail at once with a NotFound error
    slow-*        never print anything (start timeout)
    warn-*        healthy, and report a refused connection inside the pod
"""

import json
import os
import signal
import socket
import sys
import time

CONTEXTS = {
    "kind": "Config",
    "current-context": "main",
    "contexts": [
        {
            "name": "main",
            "context": {"cluster": "main", "user": "main", "namespace": "orders-api"},
        },
        {"name": "prod", "context": {"cluster": "prod", "user": "prod"}},
        {"name": "stage", "context": {"cluster": "stage", "user": "stage"}},
    ],
}


def flag(args, name):
    for index, arg in enumerate(args):
        if arg == name and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
    return ""


def port_forward(args):
    positional = []
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in {"--context", "--namespace", "-n", "--address", "--kubeconfig"}:
            skip = True
            continue
        if arg.startswith("-") or arg == "port-forward":
            continue
        positional.append(arg)
    resource, ports = positional[0], positional[1]
    target = resource.split("/", 1)[1]
    local, remote = ports.split(":")
    address = flag(args, "--address") or "127.0.0.1"
    if target.startswith("auth-"):
        print("error: You must be logged in to the server (Unauthorized)", file=sys.stderr)
        return 1
    if target.startswith("missing-"):
        print(f'Error from server (NotFound): services "{target}" not found', file=sys.stderr)
        return 1
    if target.startswith("slow-"):
        time.sleep(3600)
        return 0
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((address, int(local)))
    except OSError:
        print(f"Unable to listen on port {local}: address already in use", file=sys.stderr)
        print("error: unable to listen on any of the requested ports", file=sys.stderr)
        return 1
    listener.listen()
    print(f"Forwarding from {address}:{local} -> {remote}", flush=True)
    flaky = target.startswith("flaky-")
    if target.startswith("once-flaky-"):
        marker = os.environ.get("FAKE_KUBECTL_MARKER", "/tmp/fake-kubectl-marker") + "-" + target
        flaky = not os.path.exists(marker)
        open(marker, "w").close()
    if flaky:
        time.sleep(0.6)
        print(
            "E1125 10:00:00.000000   1234 portforward.go:413] lost connection to pod",
            file=sys.stderr,
        )
        print("error: lost connection to pod", file=sys.stderr, flush=True)
        return 1
    if target.startswith("warn-"):
        time.sleep(0.4)
        print(
            f"E1125 10:00:00.000000 1 portforward.go:424] an error occurred forwarding {local} -> {remote}:"
            " error forwarding port: dial tcp4 127.0.0.1:{remote}: connect: connection refused",
            file=sys.stderr,
            flush=True,
        )
    listener.settimeout(0.5)
    while True:
        try:
            connection, _ = listener.accept()
            print(f"Handling connection for {local}", flush=True)
            connection.close()
        except TimeoutError:
            continue


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    args = sys.argv[1:]
    if "port-forward" in args:
        return port_forward(args)
    if "use-context" in args:
        name = args[args.index("use-context") + 1]
        if name not in {c["name"] for c in CONTEXTS["contexts"]}:
            print(f'error: no context exists with the name: "{name}"', file=sys.stderr)
            return 1
        print(f'Switched to context "{name}".')
        return 0
    if args[:2] == ["config", "view"] or "view" in args:
        print(json.dumps(CONTEXTS))
        return 0
    if "version" in args:
        print(json.dumps({"clientVersion": {"gitVersion": "v1.30.14"}}))
        return 0
    if "namespaces" in args:
        print("default chat orders-api orders-stage")
        return 0
    if "services" in args:
        print("orders-psql-master\t5432/postgres ")
        print("orders-redis-haproxy\t6379/redis 9101/metrics ")
        return 0
    print(f"fake kubectl: unsupported {args}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
