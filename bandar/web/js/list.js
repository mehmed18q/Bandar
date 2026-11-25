/* The grouped service list: rendering, row actions, selection and drag & drop.
 * Rendering is a pure function of the store; actions go through the Actions facade. */
(() => {
  'use strict';
  const { h, raw, icon, $, on, highlight, contextHue } = U;
  const { UNGROUPED } = ViewModel;
  const t = (key, params) => I18n.t(key, params);

  const ENV_LABELS = { production: 'Production', staging: 'Staging', development: 'Development', testing: 'Testing', legacy: 'Legacy' };
  const COLUMNS = [
    ['name', 'Service'],
    ['context', 'Context'],
    ['namespace', 'Namespace'],
    ['status', 'Status'],
    ['uptime', 'Uptime'],
    ['local', 'Local'],
    ['remote', 'Remote'],
    ['restarts', 'Restarts'],
  ];

  function create({ actions }) {
    const head = $('#list-head');
    const body = $('#list-body');
    const list = $('#list');
    const empty = $('#empty');
    let lastAnchor = null;
    let deferred = false;

    // ---------------------------------------------------------------- rendering

    function renderHead(state) {
      const { sortKey, sortDir } = state.config.settings;
      const ids = ViewModel.visibleIds(state);
      const selected = ids.filter((id) => state.ui.selected.has(id)).length;
      head.innerHTML = h`<div class="select-cell"><input type="checkbox" class="check" data-select-all
          aria-label="${t('Select all')}" ${ids.length && selected === ids.length ? 'checked' : ''} /></div>
        ${COLUMNS.map(([key, label]) => {
          const active = sortKey === key;
          return h`<div><button class="head-cell" data-sort="${key}" ${active ? h`aria-sort="${sortDir === 'desc' ? 'descending' : 'ascending'}"` : ''}
            title="${t('Sort by {column}', { column: t(label) })}">${t(label)}${active ? icon(sortDir === 'desc' ? 'arrow-down' : 'arrow-up') : ''}</button></div>`;
        })}<div></div>`;
      const all = head.querySelector('[data-select-all]');
      all.indeterminate = selected > 0 && selected < ids.length;
    }

    function contextChip(context) {
      const hue = contextHue(context.name);
      return h`<span class="chip context ${context.inherited ? 'inherited' : ''}" style="--chip-hue:${hue}"
        title="${context.inherited ? t('Not set: uses the current kubectl context') : context.name}">
        <span class="truncate">${context.name}</span>${context.inherited ? h`<span class="tag">${t('current')}</span>` : ''}</span>`;
    }

    function statusBadge(runtime) {
      const tone = Messages.tone(runtime);
      let extra = '';
      if (runtime.state === 'retrying' && runtime.retryAt) {
        extra = h` <span data-countdown="${runtime.retryAt}"></span>`;
      }
      const busy = runtime.state === 'starting' || runtime.state === 'stopping';
      return h`<span class="badge tone-${tone} ${runtime.state === 'healthy' ? 'live' : ''}">
        ${busy ? h`<span class="spinner"></span>` : h`<span class="status-dot ${runtime.state === 'stopped' ? 'hollow' : ''}"></span>`}
        ${Messages.stateLabel(runtime)}${extra}</span>`;
    }

    function problemStrip(item, state) {
      const { service, runtime } = item;
      let error = null;
      let tone = 'err';
      if (runtime.state === 'error' || runtime.state === 'retrying') {
        error = runtime.error;
        tone = runtime.state === 'error' ? 'err' : 'warn';
      } else if (runtime.state === 'healthy' && runtime.warning) {
        error = runtime.warning;
        tone = 'warn';
      }
      // Hiding a message keeps the status badge; a new problem shows again.
      if (!error || state.ui.dismissed.has(`${service.id}:${error.at}`)) return '';
      const info = Messages.problem(error, service, { context: item.context.name, namespace: item.namespace.name });
      const buttons = {
        free: h`<button class="button" data-act="free">${icon('unplug')}${t('Free the port')}</button>`,
        retry: h`<button class="button" data-act="restart">${icon('restart')}${runtime.state === 'retrying' ? t('Retry now') : t('Retry')}</button>`,
        edit: h`<button class="button" data-act="edit">${icon('edit')}${t('Edit')}</button>`,
        logs: h`<button class="button" data-act="details">${icon('logs')}${t('Logs')}</button>`,
        settings: h`<button class="button" data-act="settings">${icon('settings')}${t('Settings')}</button>`,
      };
      const when = runtime.state === 'healthy' && error.at ? h` · <span data-ago="${error.at}"></span>` : '';
      return h`<div class="problem tone-${tone}" role="alert">
        ${icon(tone === 'err' ? 'alert' : 'info')}
        <div class="problem-text"><span class="problem-title">${info.title}${when}</span>
          <span class="problem-hint">${info.hint}</span>
          ${info.detail ? h`<span class="problem-detail">${info.detail}</span>` : ''}</div>
        <div class="problem-actions">${info.actions.map((name) => buttons[name] || '')}</div>
        <button class="icon-button small problem-close" data-act="dismiss" data-key="${service.id}:${error.at}"
          title="${t('Hide this message')}" aria-label="${t('Hide this message')}">${icon('close')}</button>
      </div>`;
    }

    function serviceRow(item, state, sorted) {
      const { service, runtime, context, namespace } = item;
      const query = state.ui.search;
      const active = ViewModel.ACTIVE.has(runtime.state) || runtime.state === 'error';
      const selected = state.ui.selected.has(service.id);
      const resource = Messages.resourceText(service);
      const tone = Messages.tone(runtime);
      return h`<div class="service-row row-grid ${selected ? 'selected' : ''} ${state.ui.drawer === service.id ? 'focused' : ''}"
          role="row" tabindex="${state.ui.cursor === service.id ? 0 : -1}" data-id="${service.id}" data-group="${service.group || UNGROUPED}">
        <div class="select-cell"><input type="checkbox" class="check" data-select ${selected ? 'checked' : ''} aria-label="${t('Select {name}', { name: service.name })}" /></div>
        <div class="service-name-cell">
          ${sorted ? '' : h`<span class="grip" draggable="true" data-drag="service" title="${t('Drag to reorder or move to another group')}">${icon('grip')}</span>`}
          <span class="status-dot" style="background:var(--${tone === 'info' ? 'accent' : tone === 'idle' ? 'idle' : tone})"></span>
          <div class="service-label">
            <span class="service-name" data-act="details" title="${service.note || service.name}">${raw(highlight(service.name, query))}${service.autoStart ? h` <span class="auto-mark" title="${t('Starts automatically')}">AUTO</span>` : ''}</span>
            <span class="service-target" title="${resource}">${raw(highlight(resource, query))}</span>
          </div>
        </div>
        <div>${contextChip(context)}</div>
        <div class="namespace truncate ${namespace.inherited ? 'inherited' : ''}" title="${namespace.inherited ? t('Not set: uses the context default') : namespace.name}">${raw(highlight(namespace.name, query))}</div>
        <div>${statusBadge(runtime)}</div>
        <div class="uptime">${runtime.state === 'healthy' && runtime.healthySince ? h`<span data-since="${runtime.healthySince}"></span>` : h`<span class="muted">—</span>`}</div>
        <div><button class="port" data-act="copy-address" title="${t('Copy {address}', { address: `${service.address.split(',')[0]}:${service.localPort}` })}">${raw(highlight(service.localPort, query))}</button></div>
        <div><span class="port">${raw(highlight(service.remotePort, query))}</span></div>
        <div class="restarts ${runtime.restarts ? 'some' : ''}" title="${runtime.connections ? t('{n} connections', { n: I18n.num(runtime.connections) }) : ''}">${I18n.num(runtime.restarts || 0)}</div>
        <div class="row-actions">
          ${active
            ? h`<button class="icon-button stop" data-act="stop" title="${t('Stop')}">${icon('stop')}</button>`
            : h`<button class="icon-button start" data-act="start" title="${t('Start')}">${icon('play')}</button>`}
          <button class="icon-button" data-act="restart" title="${t('Restart')}" ${active ? '' : 'disabled'}>${icon('restart')}</button>
          <button class="icon-button" data-act="details" title="${t('Details and logs')}">${icon('logs')}</button>
          <button class="icon-button" data-act="menu" title="${t('More actions')}" aria-haspopup="menu">${icon('more')}</button>
        </div>
        ${problemStrip(item, state)}
      </div>`;
    }

    function groupRow(section, state) {
      const { group, health, items, all } = section;
      const collapsed = group ? group.collapsed : state.config.settings.ungroupedCollapsed;
      const ids = items.map((item) => item.service.id);
      const selected = ids.filter((id) => state.ui.selected.has(id)).length;
      const total = health.total || 1;
      const parts = [];
      if (health.running) parts.push(t('{n} running', { n: I18n.num(health.running) }));
      if (health.errors) parts.push(t('{n} failed', { n: I18n.num(health.errors) }));
      if (!health.running && !health.errors && health.total) parts.push(t('all stopped'));
      const states = all.map((s) => Store.runtime(s.id).state);
      const startable = states.some((state) => state === 'stopped' || state === 'error');
      const stoppable = states.some((state) => ViewModel.ACTIVE.has(state) || state === 'error');
      return h`<div class="group-row row-grid" data-color="${group?.color || 'slate'}" data-group-row="${section.key}">
        <div class="select-cell"><input type="checkbox" class="check" data-select-group ${ids.length && selected === ids.length ? 'checked' : ''}
          ${ids.length ? '' : 'disabled'} aria-label="${t('Select all in group')}" /></div>
        <div class="group-title">
          ${group ? h`<span class="grip" draggable="true" data-drag="group" title="${t('Drag to reorder groups')}">${icon('grip')}</span>` : ''}
          <button class="caret-button" data-act="collapse" aria-expanded="${!collapsed}" title="${collapsed ? t('Expand') : t('Collapse')}">${icon('chevron')}</button>
          <span class="group-name ${group ? '' : 'ungrouped'}">${group ? group.name : t('Ungrouped')}</span>
          ${group?.environment ? h`<span class="env" data-env="${group.environment}">${t(ENV_LABELS[group.environment])}</span>` : ''}
          <span class="group-count">${t('{n} services', { n: I18n.num(health.total) })}</span>
          ${group?.note ? h`<span class="muted truncate" title="${group.note}">· ${group.note}</span>` : ''}
        </div>
        <div class="group-summary">
          <span class="health-bar" title="${parts.join(' · ')}">
            <span class="ok" style="width:${(health.healthy / total) * 100}%"></span>
            <span class="warn" style="width:${(health.connecting / total) * 100}%"></span>
            <span class="err" style="width:${(health.errors / total) * 100}%"></span>
          </span>
          <span>${parts.join(' · ')}</span>
        </div>
        <div class="row-actions">
          ${startable ? h`<button class="icon-button start" data-act="group-start" title="${health.running ? t('Start the stopped services') : t('Start group')}">${icon('play')}</button>` : ''}
          ${stoppable ? h`<button class="icon-button stop" data-act="group-stop" title="${t('Stop group')}">${icon('stop')}</button>
          <button class="icon-button" data-act="group-restart" title="${t('Restart group')}">${icon('restart')}</button>` : ''}
          <button class="icon-button" data-act="group-menu" title="${t('Group actions')}" aria-haspopup="menu">${icon('more')}</button>
        </div>
      </div>`;
    }

    function renderEmpty(state) {
      const hasServices = state.config.services.length > 0;
      empty.innerHTML = hasServices
        ? h`<div class="empty-art">${icon('search')}</div><h2>${t('Nothing matches')}</h2>
           <p>${t('No service matches the current search or filter.')}</p>
           <div class="actions"><button class="button" data-empty="clear">${t('Clear filters')}</button></div>`
        : h`<div class="empty-art">${icon('anchor')}</div><h2>${t('No port-forwards yet')}</h2>
           <p>${t('Add a service by hand, paste a kubectl port-forward command, or import a whole list of commands at once.')}</p>
           <div class="actions"><button class="button" data-empty="import">${icon('import')}${t('Import commands')}</button>
           <button class="button primary" data-empty="add">${icon('plus')}${t('New service')}</button></div>`;
    }

    function render(state) {
      if (state.ui.dragging) {
        deferred = true;
        return;
      }
      const focus = document.activeElement;
      const inside = focus && body.contains(focus);
      const focusKey = inside ? [focus.closest('[data-id]')?.dataset.id || focus.closest('[data-group-row]')?.dataset.groupRow, focus.dataset.act] : null;
      const rowFocused = inside && focus.classList.contains('service-row');
      const sections = ViewModel.sections(state);
      const sorted = !!state.config.settings.sortKey;
      list.classList.toggle('sorted', sorted);
      renderHead(state);
      body.innerHTML = h`${sections.map((section) => {
        const collapsed = section.group ? section.group.collapsed : state.config.settings.ungroupedCollapsed;
        const rows = collapsed
          ? ''
          : section.items.length
            ? section.items.map((item) => serviceRow(item, state, sorted))
            : h`<div class="group-empty" data-empty-group="${section.key}">${t('Empty group. Drag services here or add a new one.')}</div>`;
        return h`<section class="group-block ${collapsed ? 'collapsed' : ''}" data-color="${section.group?.color || 'slate'}" data-env="${section.group?.environment || ''}" data-section="${section.key}">${groupRow(section, state)}${rows}</section>`;
      })}`;
      const nothing = sections.length === 0;
      list.hidden = nothing;
      empty.hidden = !nothing;
      if (nothing) renderEmpty(state);
      tick();
      if (rowFocused && state.ui.cursor) body.querySelector(`.service-row[data-id="${CSS.escape(state.ui.cursor)}"]`)?.focus();
      else if (focusKey?.[0] && focusKey[1]) {
        body.querySelector(`[data-id="${CSS.escape(focusKey[0])}"] [data-act="${focusKey[1]}"], [data-group-row="${CSS.escape(focusKey[0])}"] [data-act="${focusKey[1]}"]`)?.focus();
      }
    }

    /** Live clocks: uptimes, retry countdowns and relative times, once per second. */
    function tick() {
      const now = Date.now();
      body.querySelectorAll('[data-since]').forEach((element) => {
        element.textContent = I18n.duration(now - Number(element.dataset.since));
      });
      body.querySelectorAll('[data-countdown]').forEach((element) => {
        const left = Math.max(0, Number(element.dataset.countdown) - now);
        element.textContent = t('in {time}', { time: I18n.duration(left + 999) });
      });
      body.querySelectorAll('[data-ago]').forEach((element) => {
        element.textContent = I18n.ago(Number(element.dataset.ago));
      });
    }

    // ---------------------------------------------------------------- events

    on(head, 'click', '[data-sort]', (_event, button) => {
      const { sortKey, sortDir } = Store.settings;
      const key = button.dataset.sort;
      if (sortKey !== key) actions.settings({ sortKey: key, sortDir: 'asc' });
      else if (sortDir === 'asc') actions.settings({ sortDir: 'desc' });
      else actions.settings({ sortKey: '', sortDir: 'asc' });
    });
    on(head, 'change', '[data-select-all]', (event) => {
      const ids = ViewModel.visibleIds(Store.state);
      Store.ui({ selected: event.target.checked ? new Set(ids) : new Set() });
    });

    on(body, 'click', '[data-select]', (event, input) => {
      const id = input.closest('[data-id]').dataset.id;
      const selected = new Set(Store.state.ui.selected);
      if (event.shiftKey && lastAnchor) {
        const ids = ViewModel.visibleIds(Store.state);
        const [from, to] = [ids.indexOf(lastAnchor), ids.indexOf(id)].sort((a, b) => a - b);
        if (from >= 0) ids.slice(from, to + 1).forEach((value) => (input.checked ? selected.add(value) : selected.delete(value)));
      } else if (input.checked) selected.add(id);
      else selected.delete(id);
      lastAnchor = id;
      Store.ui({ selected });
    });
    on(body, 'change', '[data-select-group]', (event, input) => {
      const key = input.closest('[data-section]').dataset.section;
      const section = ViewModel.sections(Store.state).find((s) => s.key === key);
      const selected = new Set(Store.state.ui.selected);
      section?.items.forEach((item) => (event.target.checked ? selected.add(item.service.id) : selected.delete(item.service.id)));
      Store.ui({ selected });
    });

    on(body, 'click', '[data-act]', (event, button) => {
      event.stopPropagation();
      const row = button.closest('[data-id]');
      const sectionKey = button.closest('[data-section]')?.dataset.section;
      const id = row?.dataset.id;
      const act = button.dataset.act;
      const groupIds = () => (ViewModel.sections(Store.state).find((s) => s.key === sectionKey)?.all || []).map((s) => s.id);
      const commands = {
        start: () => actions.forward('start', [id]),
        stop: () => actions.forward('stop', [id]),
        restart: () => actions.forward('restart', [id]),
        details: () => actions.details(id),
        edit: () => actions.editService(id),
        free: () => actions.freePort(id),
        settings: () => actions.openSettings(),
        'copy-address': () => actions.copyAddress(id),
        dismiss: () => {
          Store.state.ui.dismissed.add(button.dataset.key);
          Store.refresh();
        },
        menu: () => actions.serviceMenu(id, button),
        collapse: () => actions.collapse(sectionKey),
        'group-start': () => actions.forward('start', groupIds().filter((sid) => !ViewModel.ACTIVE.has(Store.runtime(sid).state))),
        'group-stop': () => actions.forward('stop', groupIds()),
        'group-restart': () => actions.forward('restart', groupIds().filter((sid) => Store.runtime(sid).state !== 'stopped')),
        'group-menu': () => actions.groupMenu(sectionKey, button),
      };
      commands[act]?.();
    });

    body.addEventListener('click', (event) => {
      const row = event.target.closest('.service-row');
      if (!row || event.target.closest('button, input, a, .problem')) return;
      if (event.ctrlKey || event.metaKey) {
        const selected = new Set(Store.state.ui.selected);
        selected.has(row.dataset.id) ? selected.delete(row.dataset.id) : selected.add(row.dataset.id);
        Store.ui({ selected });
        return;
      }
      actions.details(row.dataset.id);
    });
    body.addEventListener('dblclick', (event) => {
      const row = event.target.closest('.service-row');
      if (row && !event.target.closest('button, input, .problem')) actions.editService(row.dataset.id);
    });
    body.addEventListener('contextmenu', (event) => {
      const row = event.target.closest('.service-row');
      const groupRow = event.target.closest('[data-group-row]');
      if (row) actions.serviceMenu(row.dataset.id, { x: event.clientX, y: event.clientY });
      else if (groupRow) actions.groupMenu(groupRow.dataset.groupRow, { x: event.clientX, y: event.clientY });
      else return;
      event.preventDefault();
    });
    empty.addEventListener('click', (event) => {
      const kind = event.target.closest('[data-empty]')?.dataset.empty;
      if (kind === 'add') actions.newService();
      if (kind === 'import') actions.openImport();
      if (kind === 'clear') actions.clearFilters();
    });

    // ---------------------------------------------------------------- keyboard

    /* Arrow keys move between rows; the focused row takes single-key commands. */
    function moveCursor(step) {
      const rows = [...body.querySelectorAll('.service-row')];
      if (!rows.length) return;
      const index = rows.findIndex((row) => row.dataset.id === Store.state.ui.cursor);
      const next = step === Infinity ? rows.length - 1 : step === -Infinity ? 0 : Math.min(rows.length - 1, Math.max(0, index + step));
      rows.forEach((row) => (row.tabIndex = -1));
      rows[next].tabIndex = 0;
      rows[next].focus();
      rows[next].scrollIntoView({ block: 'nearest' });
      Store.state.ui.cursor = rows[next].dataset.id;
    }

    body.addEventListener('focusin', (event) => {
      const row = event.target.closest('.service-row');
      if (row) Store.state.ui.cursor = row.dataset.id;
    });
    body.addEventListener('keydown', (event) => {
      const row = event.target.closest('.service-row');
      if (!row || event.target !== row || event.ctrlKey || event.metaKey || event.altKey) return;
      const id = row.dataset.id;
      const runtime = Store.runtime(id);
      const running = ViewModel.ACTIVE.has(runtime.state) || runtime.state === 'error';
      const keys = {
        ArrowDown: () => moveCursor(1),
        ArrowUp: () => moveCursor(-1),
        Home: () => moveCursor(-Infinity),
        End: () => moveCursor(Infinity),
        Enter: () => actions.details(id),
        ' ': () => {
          const selected = new Set(Store.state.ui.selected);
          selected.has(id) ? selected.delete(id) : selected.add(id);
          Store.ui({ selected });
        },
        e: () => actions.editService(id),
        s: () => actions.forward(running ? 'stop' : 'start', [id]),
        r: () => running && actions.forward('restart', [id]),
        c: () => actions.copyAddress(id),
        ContextMenu: () => actions.serviceMenu(id, row.querySelector('[data-act="menu"]')),
      };
      const run = keys[event.key] || keys[event.key.toLowerCase()];
      if (!run) return;
      event.preventDefault();
      run();
    });
    head.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown' && event.target.matches('[data-select-all]')) {
        event.preventDefault();
        moveCursor(0);
      }
    });

    // ---------------------------------------------------------------- drag and drop

    const DnD = window.DragDrop.create({ root: body, actions });
    DnD.onEnd(() => {
      if (deferred) {
        deferred = false;
        render(Store.state);
      }
    });

    return { render, tick, focusList: () => moveCursor(0) };
  }

  window.ServiceList = { create, ENV_LABELS };
})();
