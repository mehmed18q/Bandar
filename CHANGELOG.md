# Changelog

## 1.3.0 — 2026-11-25

- Icons redesigned: logos sit centered on a tile in their brand color (dark glyphs on light brands),
  and icons without a brand color take the group's color.
- Far more choices: 187 technology logos (databases, messaging, infrastructure, cloud, observability,
  languages, developer tools, apps and payments), 158 general icons from Lucide, environment icons
  (production, staging, testing, development, local, legacy) and emoji, including any pasted emoji.
  A tabbed picker with search (try "gold" or "chat") for services and groups.
- When a local port is blocked by another program's outgoing connection, that program is named.
- Fixed: closing and immediately reopening an editor could reset it, so a service's own local port
  was reported as taken.

## 1.2.0 — 2026-11-25

- Connectivity watchdog: every cluster in use is checked every few seconds and right after a network
  change or wake from sleep. A dropped network, VPN or cluster is detected even though kubectl
  stays silent; tunnels are rebuilt with backoff, you are notified, and they reconnect as soon as
  the cluster answers. Tunnels older than a network change are rebuilt too, since their connections
  may be dead. A banner names the unreachable clusters; bursts of failures become one notification.
- Pin services and groups; a "Pinned" view in the sidebar (P toggles a pin in the list).
- Technology icons for services and groups (PostgreSQL, Redis, Redis Cluster, Kafka, Docker,
  Kubernetes and 30 more), detected from the name and port or chosen by hand.
- Clicking outside a dialog or the details panel closes it; clicking a group row opens or collapses it.
- Arabic interface; the language picker (with flags) and the "Theme & colors" panel now work as in Khana.
- Switch kubectl's current context from the sidebar or status bar, and open the kubeconfig file or folder.
- System notifications when a forward drops, fails to start or reconnects, with Retry and Show
  actions (always, only in the background, or off).
- Closing the window asks whether to keep forwards running in the background or quit; the choice
  can be remembered. Quitting stops every forward, and kubectl processes now also stop if Bandar
  itself crashes or is killed.
- Group editor redesigned: live preview, environment picker, readable member list.
- Group and toolbar buttons only offer what applies (a fully running group shows only Stop/Restart).
- Problem messages under a service have room to breathe and can be hidden.
- Environment filter in the sidebar; keyboard navigation in the list (arrows, Enter, Space, E, S, R, C).
- The taskbar shows "Bandar" and its icon: a desktop entry is registered for source runs and
  installed by the package.
- Ubuntu package (.deb), signed APT repository and a GitHub Pages site, built on Ubuntu 24.04.
- Interface tests (node --test) next to the Python suite.

## 1.0.0 — 2026-11-25

First release.

- Services: add, edit, duplicate, delete; paste a `kubectl port-forward` command to fill the form;
  context, namespace, resource and port suggestions loaded from the cluster in the background.
- Local ports: a port belongs to one service even while stopped; ports busy on this machine are
  reported with the owning process before saving; leftover `kubectl port-forward` processes can be
  stopped from the error message.
- Groups: name, color, environment badge (production, staging, development, testing, legacy), note
  and members; start, stop and restart a whole group.
- Ordering: drag and drop services and groups, move up/down, sort A→Z, or sort the list by any column.
- Supervision: an explicit state machine per forward, automatic reconnection with exponential
  backoff, start timeout, optional active health check, clear per-problem explanations and actions.
- Import and export of plain-text lists (`name = kubectl …`, `[group @environment]`).
- JSON configuration with atomic, asynchronous writes; hand edits reload automatically and an
  invalid file is never overwritten. Previously running forwards resume on launch.
- Light, dark and system themes with six palettes; English and Persian (RTL) interfaces; tray icon,
  desktop notifications and single-instance launch.
