/* Pure derivations from Store.state: resolved contexts, counts, filtered and
 * sorted sections. Rendering modules read these and never recompute rules. */
(() => {
  'use strict';
  const UNGROUPED = '__ungrouped__';
  const ACTIVE = new Set(['starting', 'healthy', 'retrying']);

  const VIEWS = {
    all: () => true,
    pinned: () => true, // decided per service and group in sections()
    running: (rt) => ACTIVE.has(rt.state),
    problems: (rt) => rt.state === 'error' || rt.state === 'retrying',
    stopped: (rt) => rt.state === 'stopped' || rt.state === 'stopping',
    healthy: (rt) => rt.state === 'healthy',
    connecting: (rt) => rt.state === 'starting' || rt.state === 'retrying',
    errors: (rt) => rt.state === 'error',
  };

  /** The context a service uses: its own, the one it started with, or kubectl's current one. */
  function contextOf(state, service) {
    if (service.context) return { name: service.context, inherited: false };
    const runtime = Store.runtime(service.id);
    const name = (runtime.desired && runtime.context) || state.meta.kube?.current || '';
    return { name: name || 'default', inherited: true };
  }

  function namespaceOf(state, service, context) {
    if (service.namespace) return { name: service.namespace, inherited: false };
    const entry = (state.meta.kube?.contexts || []).find((c) => c.name === context.name);
    return { name: entry?.namespace || 'default', inherited: true };
  }

  function describe(state, service) {
    const context = contextOf(state, service);
    return {
      service,
      runtime: Store.runtime(service.id),
      context,
      namespace: namespaceOf(state, service, context),
    };
  }

  /** Pinned directly, or through its group. */
  const isPinned = (service) => service.pinned || !!Store.group(service.group)?.pinned;

  function counts(state) {
    const result = { all: 0, pinned: 0, running: 0, problems: 0, stopped: 0, healthy: 0, connecting: 0, errors: 0 };
    for (const service of state.config.services) {
      const runtime = Store.runtime(service.id);
      for (const [view, test] of Object.entries(VIEWS)) if (view !== 'pinned' && test(runtime)) result[view] += 1;
      if (isPinned(service)) result.pinned += 1;
    }
    return result;
  }

  function health(state, services) {
    const result = { total: services.length, healthy: 0, connecting: 0, errors: 0, running: 0 };
    for (const service of services) {
      const runtime = Store.runtime(service.id);
      if (runtime.state === 'healthy') result.healthy += 1;
      if (runtime.state === 'starting' || runtime.state === 'retrying') result.connecting += 1;
      if (runtime.state === 'error') result.errors += 1;
      if (ACTIVE.has(runtime.state)) result.running += 1;
    }
    return result;
  }

  function matches(item, group, terms) {
    if (!terms.length) return true;
    const { service, context, namespace } = item;
    const haystack = [
      service.name,
      service.target,
      service.kind,
      context.name,
      namespace.name,
      service.localPort,
      service.remotePort,
      service.note,
      group?.name,
    ]
      .join(' ')
      .toLowerCase();
    return terms.every((term) => haystack.includes(term));
  }

  const STATE_ORDER = { error: 0, retrying: 1, starting: 2, stopping: 3, healthy: 4, stopped: 5 };
  const SORTERS = {
    name: (item) => item.service.name.toLowerCase(),
    context: (item) => item.context.name.toLowerCase(),
    namespace: (item) => item.namespace.name.toLowerCase(),
    status: (item) => STATE_ORDER[item.runtime.state] ?? 9,
    uptime: (item) => (item.runtime.healthySince ? Date.now() - item.runtime.healthySince : -1),
    local: (item) => item.service.localPort,
    remote: (item) => (typeof item.service.remotePort === 'number' ? item.service.remotePort : 1e6),
    restarts: (item) => item.runtime.restarts || 0,
  };

  function sortItems(items, key, direction) {
    const read = SORTERS[key];
    if (!read) return items;
    const sign = direction === 'desc' ? -1 : 1;
    return [...items].sort((a, b) => {
      const x = read(a);
      const y = read(b);
      return (x < y ? -1 : x > y ? 1 : 0) * sign || a.service.name.localeCompare(b.service.name);
    });
  }

  /** Groups in configured order, then ungrouped; filtered by view, group and search. */
  function sections(state) {
    const { view, group: onlyGroup, search, env } = state.ui;
    const terms = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const filtering = view !== 'all' || terms.length > 0 || !!env;
    const { sortKey, sortDir } = state.config.settings;
    const known = new Set(state.config.groups.map((g) => g.id));
    const buckets = new Map(state.config.groups.map((g) => [g.id, []]));
    buckets.set(UNGROUPED, []);
    for (const service of state.config.services) {
      buckets.get(known.has(service.group) ? service.group : UNGROUPED).push(service);
    }
    const result = [];
    for (const [key, services] of buckets) {
      if (onlyGroup && onlyGroup !== key) continue;
      const group = key === UNGROUPED ? null : Store.group(key);
      if (env && (group?.environment || '') !== env) continue;
      const visible = services
        .map((service) => describe(state, service))
        .filter((item) => (view === 'pinned' ? isPinned(item.service) : VIEWS[view](item.runtime)) && matches(item, group, terms));
      // Empty groups stay visible as drop targets unless the list is being filtered.
      if (!visible.length && (filtering || key === UNGROUPED)) continue;
      result.push({
        key,
        group,
        all: services,
        items: sortItems(visible, sortKey, sortDir),
        health: health(state, services),
      });
    }
    return result;
  }

  function visibleIds(state) {
    return sections(state).flatMap((section) => section.items.map((item) => item.service.id));
  }

  window.ViewModel = { UNGROUPED, VIEWS, ACTIVE, isPinned, contextOf, namespaceOf, describe, counts, health, sections, visibleIds };
})();
