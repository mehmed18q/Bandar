/* The interface state and its observers. Server data (config, runtime, meta) is
 * replaced wholesale on every push; ui holds view-only choices. Notifications
 * are batched per task so a burst of changes renders once. */
(() => {
  'use strict';
  const listeners = new Set();
  let queued = false;

  const state = {
    info: {},
    config: { settings: {}, groups: [], services: [], session: { running: [] } },
    runtime: {},
    meta: { kube: { current: '', contexts: [] } },
    ui: {
      view: 'all',
      group: null,
      search: '',
      selected: new Set(),
      drawer: null,
      dismissed: new Set(),
      env: null,
      cursor: null,
      saveError: '',
      dragging: false,
    },
  };

  function notify() {
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      for (const listener of listeners) listener(state);
    });
  }

  window.Store = {
    state,
    subscribe(listener) {
      listeners.add(listener);
    },
    replace(snapshot) {
      state.config = snapshot.config;
      state.runtime = snapshot.runtime;
      state.meta = snapshot.meta;
      const known = new Set(state.config.services.map((s) => s.id));
      state.ui.selected = new Set([...state.ui.selected].filter((id) => known.has(id)));
      if (state.ui.drawer && !known.has(state.ui.drawer)) state.ui.drawer = null;
      const groups = new Set(state.config.groups.map((g) => g.id));
      if (state.ui.group && state.ui.group !== '__ungrouped__' && !groups.has(state.ui.group)) state.ui.group = null;
      notify();
    },
    ui(patch) {
      Object.assign(state.ui, patch);
      notify();
    },
    refresh: notify,
    service: (id) => state.config.services.find((s) => s.id === id),
    group: (id) => state.config.groups.find((g) => g.id === id),
    runtime: (id) => state.runtime[id] || { state: 'stopped', desired: false, restarts: 0 },
    get settings() {
      return state.config.settings;
    },
  };
})();
