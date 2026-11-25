/* Composition root: builds the modules, owns the Actions facade they share, renders
 * the shell (stats, toolbar, footer) and wires shortcuts, theme and events. */
(() => {
  'use strict';
  const { h, icon, $ } = U;
  const { Menu, Toast, Confirm } = Overlays;
  const { UNGROUPED } = ViewModel;
  const t = (key, params) => I18n.t(key, params);
  const call = (method, params) => Native.call(method, params);
  const media = matchMedia('(prefers-color-scheme: dark)');

  // ------------------------------------------------------------------ actions
  /* Every user intention passes through here; modules never call Native directly
   * for mutations, so confirmations and feedback stay consistent. */
  const actions = {
    forward(command, ids) {
      if (!ids.length) return;
      call(`forward.${command}`, { ids });
    },
    details(id) {
      drawer.open(id);
    },
    newService(options = {}) {
      serviceForm.open(options);
    },
    editService(id) {
      serviceForm.open({ id });
    },
    duplicate(id) {
      call('service.duplicate', { id }).then((result) => {
        if (result.ok) serviceForm.open({ id: result.id });
      });
    },
    newGroup() {
      groupForm.open();
    },
    editGroup(id) {
      groupForm.open(id);
    },
    openImport() {
      importForm.open();
    },
    openSettings() {
      settingsForm.open();
    },
    settings(patch) {
      Object.assign(Store.settings, patch);
      Store.refresh();
      call('settings.update', patch);
    },
    copy(text, message) {
      call('shell.copy', { text });
      Toast.show({ tone: 'ok', title: message || t('Copied'), body: text.length > 120 ? '' : text, key: 'copy', timeout: 2200 });
    },
    copyAddress(id) {
      const service = Store.service(id);
      if (!service) return;
      const host = service.address.split(',')[0].replace(/^0\.0\.0\.0$/, '127.0.0.1');
      this.copy(`${host}:${service.localPort}`, t('Address copied'));
    },
    async copyCommand(id) {
      const result = await call('command.preview', { data: Store.service(id) });
      this.copy(result.command, t('Command copied'));
    },
    moveService(id, group, before) {
      call('service.move', { id, group, before });
    },
    moveGroup(id, before) {
      call('group.move', { id, before });
    },
    assign(ids, group) {
      call('service.assign', { ids, group }).then(() => Store.ui({ selected: new Set() }));
    },
    sortGroups() {
      call('group.sort');
    },
    collapse(key) {
      if (key === UNGROUPED) actions.settings({ ungroupedCollapsed: !Store.settings.ungroupedCollapsed });
      else {
        const group = Store.group(key);
        if (!group) return;
        group.collapsed = !group.collapsed;
        Store.refresh();
        call('group.collapse', { id: key, collapsed: group.collapsed });
      }
    },
    clearFilters() {
      $('#search').value = '';
      Store.ui({ search: '', view: 'all', group: null, env: null });
    },
    async deleteServices(ids) {
      if (!ids.length) return;
      const names = ids.map((id) => Store.service(id)?.name).filter(Boolean);
      if (Store.settings.confirmDelete) {
        const answer = await Confirm.ask({
          title: ids.length === 1 ? t('Delete “{name}”?', { name: names[0] }) : t('Delete {n} services?', { n: I18n.num(ids.length) }),
          message: t('Running forwards are stopped. This cannot be undone.'),
          confirm: t('Delete'),
        });
        if (!answer) return;
      }
      await call('service.delete', { ids });
      Store.ui({ selected: new Set() });
      Toast.show({ tone: 'ok', title: ids.length === 1 ? t('Service deleted') : t('{n} services deleted', { n: I18n.num(ids.length) }), body: names.slice(0, 3).join(', ') });
    },
    async deleteGroup(id, withServices) {
      const group = Store.group(id);
      if (!group) return;
      const count = Store.state.config.services.filter((s) => s.group === id).length;
      if (Store.settings.confirmDelete || withServices) {
        const answer = await Confirm.ask({
          title: t('Delete group “{name}”?', { name: group.name }),
          message: withServices
            ? t('The group and its {n} services are removed. Running forwards are stopped.', { n: I18n.num(count) })
            : t('Its {n} services move to “Ungrouped”.', { n: I18n.num(count) }),
          confirm: withServices ? t('Delete group and services') : t('Delete group'),
        });
        if (!answer) return;
      }
      await call('group.delete', { id, withServices });
      Toast.show({ tone: 'ok', title: t('Group deleted'), body: group.name });
    },
    async freePort(id) {
      const service = Store.service(id);
      const owner = Store.runtime(id).error?.owner;
      const answer = await Confirm.ask({
        title: t('Free port {port}?', { port: service.localPort }),
        message: t('Stop {owner} so this service can use the port.', { owner: Messages.ownerText(owner) }),
        confirm: t('Stop it and retry'),
      });
      if (!answer) return;
      const result = await call('port.release', { id });
      if (result.ok) Toast.show({ tone: 'ok', title: t('Port freed'), body: t('Retrying {name}…', { name: service.name }) });
      else Toast.show({ tone: 'err', title: t('Could not free the port'), body: result.code === 'not_kubectl' ? t('It is not a kubectl port-forward, so Bandar leaves it alone.') : result.detail || '' });
    },
    groupPicker(ids, anchor) {
      const current = ids.length === 1 ? Store.service(ids[0])?.group || '' : null;
      Menu.open(anchor, [
        { heading: t('Move to group') },
        ...Store.state.config.groups.map((g) => ({ label: g.name, color: g.color, checked: current === g.id, run: () => actions.assign(ids, g.id) })),
        { label: t('Ungrouped'), icon: 'list', checked: current === '', run: () => actions.assign(ids, '') },
        '-',
        { label: t('New group…'), icon: 'plus', run: () => actions.newGroupWith(ids) },
      ]);
    },
    newGroupWith(ids) {
      groupForm.open(null, ids);
    },
    /* Switch kubectl's current context (global, like `kubectl config use-context`). */
    contextMenu(anchor) {
      const kube = Store.state.meta.kube || {};
      const followers = Store.state.config.services.filter((s) => !s.context && ViewModel.ACTIVE.has(Store.runtime(s.id).state));
      Menu.open(anchor, [
        { heading: t('Current kubectl context') },
        { note: t('Changes the current context for kubectl everywhere, like “kubectl config use-context”.') },
        ...(kube.contexts || []).map((c) => ({
          label: c.name,
          sub: c.namespace || '',
          icon: c.name === kube.current ? 'check' : '',
          checked: c.name === kube.current,
          run: () => c.name !== kube.current && actions.useContext(c.name, followers.map((s) => s.id)),
        })),
        '-',
        { label: t('Open kubeconfig file'), icon: 'edit', run: () => actions.openKubeconfig(false) },
        { label: t('Open kubeconfig folder'), icon: 'folder', run: () => actions.openKubeconfig(true) },
        { label: t('Reload kubeconfig'), icon: 'restart', run: () => call('kube.refresh') },
      ]);
    },
    async openKubeconfig(folder) {
      const result = await call('shell.openKubeconfig', { folder });
      if (!result.ok) Toast.show({ tone: 'err', title: t('The kubeconfig was not found'), body: result.path });
    },
    async useContext(name, followers) {
      const result = await call('kube.useContext', { name });
      if (!result.ok) {
        const info = Messages.problem(result.error || {}, { localPort: '', kind: 'service', target: '' });
        Toast.show({ tone: 'err', title: t('Could not switch the context'), body: `${info.title} ${result.error?.detail || ''}` });
        return;
      }
      Toast.show({
        tone: 'ok',
        title: t('Current context: {name}', { name }),
        body: followers.length ? t('{n} running services follow the current context and still use the previous one.', { n: I18n.num(followers.length) }) : '',
        actions: followers.length ? [{ label: t('Restart them'), run: () => actions.forward('restart', followers) }] : [],
        timeout: followers.length ? 12000 : 3500,
      });
    },
    serviceMenu(id, anchor) {
      const service = Store.service(id);
      if (!service) return;
      const runtime = Store.runtime(id);
      const active = ViewModel.ACTIVE.has(runtime.state) || runtime.state === 'error';
      const siblings = Store.state.config.services.filter((s) => (s.group || '') === (service.group || ''));
      const index = siblings.findIndex((s) => s.id === id);
      const sorted = !!Store.settings.sortKey;
      Menu.open(anchor, [
        active
          ? { label: t('Stop'), icon: 'stop', run: () => actions.forward('stop', [id]) }
          : { label: t('Start'), icon: 'play', run: () => actions.forward('start', [id]) },
        { label: t('Restart'), icon: 'restart', disabled: !active, run: () => actions.forward('restart', [id]) },
        { label: t('Details and logs'), icon: 'logs', run: () => actions.details(id) },
        '-',
        { label: t('Edit…'), icon: 'edit', run: () => actions.editService(id) },
        { label: t('Duplicate'), icon: 'duplicate', run: () => actions.duplicate(id) },
        { label: t('Copy address'), icon: 'link', run: () => actions.copyAddress(id) },
        { label: t('Copy kubectl command'), icon: 'terminal', run: () => actions.copyCommand(id) },
        '-',
        { label: t('Move to group…'), icon: 'layers', run: () => actions.groupPicker([id], anchor) },
        { label: t('Move up'), icon: 'arrow-up', disabled: sorted || index <= 0, run: () => actions.moveService(id, service.group, siblings[index - 1].id) },
        { label: t('Move down'), icon: 'arrow-down', disabled: sorted || index >= siblings.length - 1, run: () => actions.moveService(id, service.group, siblings[index + 2]?.id ?? null) },
        '-',
        { label: t('Delete'), icon: 'trash', danger: true, shortcut: 'Del', run: () => actions.deleteServices([id]) },
      ]);
    },
    groupMenu(key, anchor) {
      if (key === UNGROUPED) {
        Menu.open(anchor, [
          { label: t('Add a service here'), icon: 'plus', run: () => actions.newService({ group: '' }) },
          { label: t('Sort services A→Z'), icon: 'sort-az', run: () => call('service.sort', { group: UNGROUPED }) },
        ]);
        return;
      }
      const groups = Store.state.config.groups;
      const index = groups.findIndex((g) => g.id === key);
      Menu.open(anchor, [
        { label: t('Add a service here'), icon: 'plus', run: () => actions.newService({ group: key }) },
        { label: t('Edit group…'), icon: 'edit', run: () => actions.editGroup(key) },
        { label: t('Sort services A→Z'), icon: 'sort-az', run: () => call('service.sort', { group: key }) },
        { label: t('Move group up'), icon: 'arrow-up', disabled: index <= 0, run: () => actions.moveGroup(key, groups[index - 1].id) },
        { label: t('Move group down'), icon: 'arrow-down', disabled: index >= groups.length - 1, run: () => actions.moveGroup(key, groups[index + 2]?.id ?? null) },
        '-',
        { label: t('Delete group, keep services'), icon: 'trash', danger: true, run: () => actions.deleteGroup(key, false) },
        { label: t('Delete group and its services'), icon: 'trash', danger: true, run: () => actions.deleteGroup(key, true) },
      ]);
    },
  };

  // ------------------------------------------------------------------ modules
  const list = ServiceList.create({ actions });
  const sidebar = Sidebar.create({ actions });
  const drawer = Drawer.create({ actions });
  const serviceForm = ServiceForm.create({ actions });
  const groupForm = GroupForm.create({ actions });
  const importForm = ImportForm.create({ actions });
  const settingsForm = SettingsForm.create({ actions });
  const header = Header.create({ actions, systemDark: () => media.matches });

  // ------------------------------------------------------------------ shell rendering
  const VIEW_TITLES = {
    all: 'All services',
    running: 'Running',
    problems: 'Problems',
    stopped: 'Stopped',
    healthy: 'Healthy',
    connecting: 'Connecting',
    errors: 'Errors',
  };
  let appliedLanguage = null;

  function applyAppearance(settings) {
    const dark = settings.theme === 'dark' || (settings.theme === 'auto' && media.matches);
    document.body.dataset.theme = dark ? 'dark' : 'light';
    document.body.dataset.palette = settings.palette || 'ocean';
    document.body.dataset.density = settings.density || 'comfortable';
    $('#app').classList.toggle('sidebar-collapsed', !!settings.sidebarCollapsed);
    if (appliedLanguage !== settings.language) {
      appliedLanguage = settings.language;
      I18n.setLanguage(settings.language);
    }
    header.render(settings, dark);
  }

  function renderStats(state) {
    const counts = ViewModel.counts(state);
    const total = counts.all || 1;
    const cards = [
      ['healthy', 'Healthy', 'pulse', 'ok', counts.healthy],
      ['connecting', 'Connecting', 'restart', 'warn', counts.connecting],
      ['errors', 'Errors', 'alert', 'err', counts.errors],
      ['stopped', 'Stopped', 'pause', 'idle', counts.stopped],
    ];
    $('#stats').innerHTML = h`${cards.map(([view, label, iconName, tone, value]) => h`
      <button class="stat tone-${tone}" data-stat="${view}" aria-pressed="${state.ui.view === view}">
        <span class="stat-icon">${icon(iconName)}</span>
        <span><div class="stat-value">${I18n.num(value)}</div><div class="stat-label">${t(label)}</div></span>
        <span class="stat-meter"><span style="width:${(value / total) * 100}%"></span></span>
      </button>`)}`;
  }

  function filtering(state) {
    return state.ui.view !== 'all' || !!state.ui.group || !!state.ui.env || !!state.ui.search.trim();
  }

  function renderToolbar(state) {
    const selected = state.ui.selected.size;
    $('#bulk-actions').hidden = !selected;
    $('#global-actions').hidden = !!selected;
    $('#bulk-count').textContent = t('{n} selected', { n: I18n.num(selected) });
    const shown = filtering(state);
    $('#start-all span').textContent = shown ? t('Start shown') : t('Start all');
    $('#stop-all span').textContent = shown ? t('Stop shown') : t('Stop all');
    const counts = ViewModel.counts(state);
    const scope = scopeIds().map((id) => Store.runtime(id).state);
    // Like the group buttons: offer only what applies to the services in view.
    $('#start-all').hidden = !scope.some((s) => s === 'stopped' || s === 'error');
    $('#stop-all').hidden = !scope.some((s) => ViewModel.ACTIVE.has(s) || s === 'error');
    $('#retry-failed').hidden = !counts.problems;
    const { sortKey, sortDir } = state.config.settings;
    $('#sort-note').hidden = !sortKey;
    if (sortKey) {
      const column = { name: 'Service', context: 'Context', namespace: 'Namespace', status: 'Status', uptime: 'Uptime', local: 'Local', remote: 'Remote', restarts: 'Restarts' }[sortKey];
      $('#sort-note-text').textContent = t('Sorted by {column} ({direction}). Drag and drop is off while sorting.', {
        column: t(column),
        direction: sortDir === 'desc' ? t('descending') : t('ascending'),
      });
    }
  }

  function renderTitle(state) {
    const group = state.ui.group;
    const env = state.ui.env;
    const title =
      group === UNGROUPED
        ? t('Ungrouped')
        : group
          ? Store.group(group)?.name
          : env
            ? t('{env} groups', { env: t(ServiceList.ENV_LABELS[env]) })
            : t(VIEW_TITLES[state.ui.view]);
    $('#page-title').textContent = title || '';
    const counts = ViewModel.counts(state);
    $('#page-subtitle').textContent = t('{services} services · {groups} groups · {running} running', {
      services: I18n.num(counts.all),
      groups: I18n.num(state.config.groups.length),
      running: I18n.num(counts.running),
    });
    document.title = counts.errors ? `(${counts.errors}) Bandar` : 'Bandar';
  }

  function renderFooter(state) {
    const path = state.meta.configPath || '';
    $('#status-config-path').textContent = path.replace(/^\/home\/[^/]+/, '~');
    $('#status-kubectl').textContent = state.meta.kube?.version ? `kubectl ${state.meta.kube.version}` : 'kubectl';
    $('#status-context').textContent = state.meta.kube?.current ? t('context: {name}', { name: state.meta.kube.current }) : t('no current context');
    $('#status-context').title = t('Switch the current kubectl context');
    const save = $('#status-save');
    save.classList.toggle('err', !!(state.meta.readOnly || state.ui.saveError));
    save.textContent = state.meta.readOnly ? t('Read-only: fix the configuration file') : state.ui.saveError ? t('Saving failed') : t('Auto-saved');
    $('#config-banner').hidden = !state.meta.configError;
    $('#config-banner-detail').textContent = state.meta.configError || '';
  }

  function render(state) {
    applyAppearance(state.config.settings);
    renderStats(state);
    renderToolbar(state);
    renderTitle(state);
    renderFooter(state);
    sidebar.render(state);
    list.render(state);
    drawer.render(state);
    if (settingsForm.isOpen) settingsForm.render();
  }

  // ------------------------------------------------------------------ static wiring
  function scopeIds() {
    return filtering(Store.state) ? ViewModel.visibleIds(Store.state) : Store.state.config.services.map((s) => s.id);
  }

  function wire() {
    $('#stats').addEventListener('click', (event) => {
      const view = event.target.closest('[data-stat]')?.dataset.stat;
      if (view) Store.ui({ view: Store.state.ui.view === view ? 'all' : view, group: null });
    });
    $('#start-all').onclick = () => actions.forward('start', scopeIds());
    $('#stop-all').onclick = () => actions.forward('stop', scopeIds());
    $('#retry-failed').onclick = () => call('forward.retryFailed');
    $('#new-service-button').onclick = () => actions.newService({ group: Store.state.ui.group && Store.state.ui.group !== UNGROUPED ? Store.state.ui.group : '' });
    $('#new-group-button').onclick = () => actions.newGroup();
    $('#import-button').onclick = () => actions.openImport();
    $('#settings-button').onclick = () => actions.openSettings();
    $('#theme-button').onclick = () => actions.settings({ theme: document.body.dataset.theme === 'dark' ? 'light' : 'dark' });
    $('#kube-note').onclick = (event) => actions.contextMenu(event.currentTarget);
    $('#status-context').onclick = (event) => actions.contextMenu(event.currentTarget);
    $('#toggle-sidebar').onclick = () => actions.settings({ sidebarCollapsed: !Store.settings.sidebarCollapsed });
    $('#sort-reset').onclick = () => actions.settings({ sortKey: '', sortDir: 'asc' });
    $('#search').addEventListener('input', (event) => Store.ui({ search: event.target.value }));
    $('#search').addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && event.target.value) {
        event.stopPropagation();
        event.target.value = '';
        Store.ui({ search: '' });
      }
    });
    $('#bulk-actions').addEventListener('click', (event) => {
      const button = event.target.closest('[data-bulk]');
      if (!button) return;
      const ids = [...Store.state.ui.selected];
      const kind = button.dataset.bulk;
      if (kind === 'start' || kind === 'stop' || kind === 'restart') actions.forward(kind, ids);
      if (kind === 'move') actions.groupPicker(ids, button);
      if (kind === 'delete') actions.deleteServices(ids);
      if (kind === 'clear') Store.ui({ selected: new Set() });
    });
    $('#status-config').onclick = () => call('shell.revealConfig');
    $('#config-banner-open').onclick = () => call('shell.revealConfig');
    $('#config-banner-reset').onclick = async () => {
      const answer = await Confirm.ask({
        title: t('Reset the configuration?'),
        message: t('The current file is kept as a backup next to it, and Bandar starts with an empty configuration.'),
        confirm: t('Back up and reset'),
      });
      if (answer) {
        const result = await call('config.reset');
        Toast.show({ tone: 'ok', title: t('Configuration reset'), body: result.backup });
      }
    };
    $('#open-logs').onclick = () => call('shell.openLogs');
    $('#repository-link').onclick = (event) => {
      event.preventDefault();
      call('shell.openUrl', { url: Store.state.info.repository });
    };
    $('#developer-link').onclick = (event) => {
      event.preventDefault();
      call('shell.openUrl', { url: Store.state.info.authorUrl });
    };
    media.addEventListener('change', () => Store.refresh());
    addEventListener('focus', () => call('kube.refresh'));
    document.addEventListener('keydown', shortcuts);
  }

  function shortcuts(event) {
    if (document.querySelector('dialog[open]')) return;
    const typing = event.target.closest('input, textarea, select, [contenteditable]');
    const mod = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();
    if (mod && key === 'n') return stop(event, () => actions.newService());
    if (mod && key === 'g') return stop(event, () => actions.newGroup());
    if (mod && key === 'i') return stop(event, () => actions.openImport());
    if (mod && key === ',') return stop(event, () => actions.openSettings());
    if (mod && key === 'f') return stop(event, () => $('#search').focus());
    if (typing) return;
    if (key === '/') return stop(event, () => $('#search').focus());
    if (mod && key === 'a') return stop(event, () => Store.ui({ selected: new Set(ViewModel.visibleIds(Store.state)) }));
    if (key === 'j' || key === 'arrowdown') return stop(event, () => list.focusList());
    if (key === 'delete' && Store.state.ui.selected.size) return stop(event, () => actions.deleteServices([...Store.state.ui.selected]));
    if (key === 'escape') {
      if (Menu.isOpen) return Menu.close();
      header.close();
      if (Store.state.ui.drawer) return drawer.close();
      if (Store.state.ui.selected.size) return Store.ui({ selected: new Set() });
      if (filtering(Store.state)) return actions.clearFilters();
    }
  }

  function stop(event, run) {
    event.preventDefault();
    run();
  }

  // ------------------------------------------------------------------ closing

  /* The window's close button: keep forwards running in the background, or quit. */
  function askClose({ tray, running }) {
    const dialog = $('#confirm-dialog');
    if (dialog.open) return;
    let choice = null;
    Overlays.Sheet.open(
      dialog,
      h`<form method="dialog">
        ${Overlays.Sheet.head('anchor', t('Close Bandar?'), '')}
        <div class="sheet-body">
          <p>${running ? t('{n} forwards are running. Keep them running in the background, or quit and stop them?', { n: I18n.num(running) }) : t('Keep Bandar running in the background, or quit?')}</p>
          <p class="muted">${tray ? t('In the background, click the tray icon to show the window again.') : t('In the background, open Bandar again from the applications menu to show the window.')}</p>
          <label class="toggle-row"><span>${t('Remember my choice')}</span>
            <span class="switch"><input type="checkbox" id="close-remember" /><span></span></span></label>
        </div>
        <footer class="sheet-foot">
          <button class="button" data-dismiss>${t('Cancel')}</button><span class="spacer"></span>
          <button class="button danger" data-close-choice="quit">${icon('stop')}${t('Quit')}</button>
          <button class="button primary" data-close-choice="background">${icon('layers')}${t('Run in background')}</button>
        </footer></form>`,
      {
        onClose: () => {
          if (choice) call('shell.closeChoice', { choice, remember: $('#close-remember')?.checked });
        },
      }
    );
    dialog.querySelectorAll('[data-close-choice]').forEach((button) => {
      button.onclick = (event) => {
        event.preventDefault();
        choice = button.dataset.closeChoice;
        dialog.close();
      };
    });
    dialog.querySelector('[data-close-choice="background"]').focus();
  }

  // ------------------------------------------------------------------ events from Python
  function notice({ notice: n }) {
    if (n.code === 'forward_failed') {
      const service = Store.service(n.id);
      if (!service) return;
      const info = Messages.problem(n.error || {}, service, {});
      Toast.show({
        tone: n.level === 'error' ? 'err' : 'warn',
        title: `${n.service}: ${info.title}`,
        body: n.state === 'retrying' ? t('Reconnecting automatically…') : info.hint,
        key: `fail:${n.id}`,
        actions: [{ label: t('Details'), run: () => actions.details(n.id) }],
      });
    } else if (n.code === 'forward_recovered') {
      Toast.show({ tone: 'ok', title: t('{name}: reconnected', { name: n.service }), key: `fail:${n.id}`, timeout: 3500 });
    } else if (n.code === 'config_reloaded') {
      Toast.show({ tone: 'info', title: t('Configuration reloaded'), body: t('The JSON file was changed outside Bandar.') });
    } else if (n.code === 'config_invalid' || n.code === 'config_unreadable') {
      Toast.show({ tone: 'err', title: t('The configuration file has an error. Changes are not being saved.'), body: n.detail, key: 'config' });
    } else if (n.code === 'save_failed') {
      Store.ui({ saveError: n.detail });
      Toast.show({ tone: 'err', title: t('Could not save the configuration'), body: n.detail, key: 'save' });
    }
  }

  async function start() {
    I18n.apply();
    try {
      Store.state.info = await Native.connect();
    } catch (error) {
      $('#loading').innerHTML = h`<p>${error.message}</p>`;
      return;
    }
    const info = Store.state.info;
    $('#app-version').textContent = `v${info.version}`;
    $('#status-version').textContent = `v${info.version}`;
    $('#developer-link').textContent = info.author;
    $('#repository-link').href = info.repository;
    $('#developer-link').href = info.authorUrl;
    Store.subscribe(render);
    Native.on('state', (event) => Store.replace(event.state));
    Native.on('log', (event) => drawer.appendLog(event.id, event.entry));
    Native.on('notice', notice);
    Native.on('focus', (event) => Store.service(event.id) && actions.details(event.id));
    Native.on('close-request', askClose);
    wire();
    Store.replace(await call('state'));
    setInterval(() => {
      list.tick();
      drawer.tick();
    }, 1000);
    requestAnimationFrame(() => $('#loading').classList.add('done'));
    window.bandar = { Store, actions, ViewModel, Overlays, closePopovers: () => header.close() };
  }

  start();
})();
