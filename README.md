# Bandar

A desktop manager for `kubectl port-forward`: keep every tunnel you need in one window, grouped
and named, with live status, automatic reconnection and errors that say what to do.

> **بندر** — مدیریت پورت‌فورواردهای کوبرنتیز با رابط گرافیکی: گروه‌بندی، نام‌گذاری، اجرای تکی و
> گروهی، اتصال دوبارهٔ خودکار، خطاهای قابل‌فهم، پوستهٔ روشن/تیره و رابط فارسی و انگلیسی.

## Features

- **Services** with a name, context, namespace, resource (service, pod, deployment, statefulset,
  replicaset), local and remote port. Paste any `kubectl port-forward` command to fill the form.
  Contexts come from your kubeconfig; namespaces, resources and their ports are suggested from the
  cluster without blocking the window.
- **Safe local ports**: a port is owned by exactly one service, even when it is stopped. A port that is
  busy on this machine is shown with the process holding it, before you save.
- **Groups** with a color, an **environment badge** (production, staging, development, testing,
  legacy) and a note. Start, stop or restart a whole group; empty groups accept dropped services.
- **Ordering**: drag and drop services between and within groups, reorder groups, sort A→Z, or sort
  the table by any column.
- **Connectivity watchdog**: a dropped network, VPN or cluster is noticed within seconds (kubectl
  itself stays silent), tunnels are rebuilt, you get one notification, and they reconnect as soon as
  the cluster answers, also after sleep or a network change.
- **Pins and icons**: pin services or groups into the "Pinned" view; each service shows its
  technology's logo (PostgreSQL, Redis, Kafka, Docker, …), detected or chosen.
- **Supervision**: every forward is a small state machine (stopped → starting → healthy, retrying,
  error). Dropped tunnels reconnect with exponential backoff; problems that need you (wrong context,
  expired credentials, busy port) stop and explain what to do.
- **Import / export** a plain-text list, the same format both ways.
- **One JSON file** holds services, groups and settings. Writes are atomic and asynchronous; edits
  made by hand are picked up automatically, and an invalid hand edit is never overwritten.
- **Contexts**: switch kubectl's current context from the sidebar and open your kubeconfig.
- **Notifications** when a forward drops, fails to start or reconnects, with Retry and Show buttons.
- **Closing** asks whether to keep forwards running in the background or quit; quitting (or even a
  crash) stops every kubectl process.
- Light, dark and system themes, six palettes, comfortable or compact density, English, Persian and
  Arabic (right-to-left), tray icon, resume of running forwards on launch.

## Install

Ubuntu 24.04+ (amd64): add the APT repository from the
[project site](https://mehmed18q.github.io/Bandar/), or download the `.deb` from the
[latest release](https://github.com/mehmed18q/Bandar/releases/latest) and run
`sudo apt install ./bandar_*.deb`.

## Run from source

Requirements: Python 3.11+, `kubectl` on `PATH` (or set its path in Settings).

```bash
./bandar.sh                      # creates .venv on first run
./bandar.sh --hidden             # start in the tray
./bandar.sh --config ~/work.json # use another configuration file
```

The configuration lives in `~/.config/bandar/config.json` (or `$BANDAR_CONFIG`); logs are in
`~/.config/bandar/logs/`.

## Import format

```text
# one service per line; "[group @environment]" starts a group, "[]" ends it
[orders @production]
orders-postgresql = kubectl --context main -n orders-api port-forward svc/orders-psql-master 5432:5432
orders-redis = kubectl --context main -n orders-api port-forward svc/orders-redis-haproxy 6379:6379

[]
# without a name, the resource name is used
kubectl --context prod -n chat port-forward svc/chat-redis-main 6381:6379
```

## Keyboard

`Ctrl+N` new service · `Ctrl+G` new group · `Ctrl+I` import/export · `Ctrl+,` settings ·
`/` search · `Ctrl+A` select visible · `Delete` delete selected · `Esc` close or clear.
In the list: `↑`/`↓` move, `Enter` details, `Space` select, `E` edit, `S` start/stop, `R` restart,
`C` copy the local address.

## Architecture

```
bandar/
  core/        pure domain, no Qt: config (validation, ordering), commands (parse/build/import/export),
               diagnostics (kubectl output → problem codes), ports (bind status, owner lookup)
  runtime/     forward.py (one kubectl process as a state machine), retry.py (backoff strategy),
               manager.py (facade over all forwards), tasks.py (thread pool → Qt thread)
  infra/       store.py (JSON repository: coalesced async writes, file watching),
               kube.py (async, cached kubectl queries)
  app.py       application service: the only entry point for user intentions
  ui/          window, tray, notifier (system notifications) and bridge.py (JSON request/reply
               adapter over QWebChannel)
  integration.py  desktop entry and icon, so the taskbar shows Bandar
  web/         the interface: vanilla JS modules (store → view-model → renderers), CSS tokens
```

Rules: the core never imports Qt; the interface never mutates state directly but asks the
Application through the bridge; anything slow (processes, file I/O, `/proc` scans, cluster queries)
is asynchronous, so the window never freezes.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -t .   # unit and integration tests (fake kubectl)
node --test tests/js/*.test.cjs                        # interface tests
.venv/bin/python scripts/screens.py /tmp/shots main ar group-edit   # screenshots, offscreen
.venv/bin/python scripts/i18n_keys.py ar               # untranslated interface strings
.venv/bin/ruff check bandar tests scripts && .venv/bin/ruff format --check bandar tests scripts
```

Packaging (see [packaging/RELEASE.md](packaging/RELEASE.md)):

```bash
python3 scripts/build_ubuntu24.py                       # release .deb, built and tested in Ubuntu 24.04
.venv/bin/pip install -r requirements-build.txt && .venv/bin/python scripts/build_deb.py --local
```

`tests/fake_kubectl.py` stands in for kubectl, so tests never touch a cluster.

Technology logos come from [Simple Icons](https://simpleicons.org) (CC0-1.0); they are trademarks
of their owners and only identify the technology. Regenerate them with `scripts/make_icons.py`.

## License and credits

© 2026 · Development by [Sadeq Kiomarsi](https://github.com/mehmed18q) ·
[github.com/mehmed18q/Bandar](https://github.com/mehmed18q/Bandar)
