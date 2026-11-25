/* Details drawer: facts, the exact kubectl command, the current problem and live logs. */
(() => {
  'use strict';
  const { h, icon, $ } = U;
  const t = (key, params) => I18n.t(key, params);
  const LOG_LIMIT = 500;

  function create({ actions }) {
    const drawer = $('#drawer');
    let current = null;
    let logs = [];
    let errorsOnly = false;
    let command = '';

    async function open(id) {
      if (current !== id) {
        current = id;
        logs = [];
        command = '';
        const [result, preview] = await Promise.all([
          Native.call('forward.logs', { id }),
          Native.call('command.preview', { data: Store.service(id) || {} }),
        ]);
        if (current !== id) return;
        logs = result.logs || [];
        command = preview.command;
      }
      Store.ui({ drawer: id });
    }

    function close() {
      current = null;
      Store.ui({ drawer: null });
    }

    function logLine(entry) {
      return h`<div class="log-line ${entry.level}"><time>${I18n.clock(entry.t)}</time><span>${entry.text}</span></div>`;
    }

    function renderLogs() {
      const box = drawer.querySelector('.logs');
      if (!box) return;
      const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
      const shown = errorsOnly ? logs.filter((e) => e.level === 'error' || e.level === 'warn') : logs;
      box.innerHTML = shown.length ? h`${shown.map(logLine)}` : h`<div class="logs-empty">${t('No output yet. Start the service to see kubectl output here.')}</div>`;
      if (stick) box.scrollTop = box.scrollHeight;
    }

    function render(state) {
      const id = state.ui.drawer;
      drawer.hidden = !id;
      if (!id) {
        drawer.innerHTML = '';
        return;
      }
      if (id !== current) {
        open(id);
        return;
      }
      const service = Store.service(id);
      if (!service) return close();
      const item = ViewModel.describe(state, service);
      const { runtime, context, namespace } = item;
      const tone = Messages.tone(runtime);
      const group = Store.group(service.group);
      const active = ViewModel.ACTIVE.has(runtime.state) || runtime.state === 'error';
      const error = runtime.error || (runtime.state === 'healthy' ? runtime.warning : null);
      const scroll = drawer.querySelector('.logs')?.scrollTop;
      const facts = [
        [t('Status'), h`<span class="badge tone-${tone}"><span class="status-dot"></span>${Messages.stateLabel(runtime)}</span>`],
        [t('Group'), group ? h`<span class="chip" data-color="${group.color}"><span class="status-dot" style="background:var(--group)"></span>${group.name}</span>` : h`<span class="muted">${t('Ungrouped')}</span>`],
        [t('Context'), h`<span class="mono">${context.name}</span>${context.inherited ? h` <span class="muted">(${t('current')})</span>` : ''}`],
        [t('Namespace'), h`<span class="mono">${namespace.name}</span>${namespace.inherited ? h` <span class="muted">(${t('default')})</span>` : ''}`],
        [t('Resource'), h`<span class="mono">${Messages.resourceText(service)}</span>`],
        [t('Ports'), h`<span class="port">${service.address.split(',')[0]}:${service.localPort}</span> → <span class="port">${service.remotePort}</span>`],
        [t('Uptime'), runtime.healthySince ? h`<span data-since="${runtime.healthySince}"></span>` : '—'],
        [t('Restarts'), I18n.num(runtime.restarts || 0)],
        [t('Connections'), h`${I18n.num(runtime.connections || 0)}${runtime.lastActivity ? h` · <span class="muted" data-ago="${runtime.lastActivity}"></span>` : ''}`],
        [t('Process'), runtime.pid ? h`<span class="mono">PID ${runtime.pid}</span>` : '—'],
      ];
      if (service.note) facts.push([t('Note'), service.note]);
      let problem = '';
      if (error) {
        const info = Messages.problem(error, service, { context: context.name, namespace: namespace.name });
        problem = h`<div class="problem tone-${runtime.state === 'error' ? 'err' : 'warn'}">${icon('alert')}
          <div class="problem-text"><span class="problem-title">${info.title}</span><span class="problem-hint">${info.hint}</span>
          ${info.detail ? h`<span class="problem-detail">${info.detail}</span>` : ''}</div></div>`;
      } else if (runtime.lastError && runtime.state === 'healthy') {
        const info = Messages.problem(runtime.lastError, service, { context: context.name, namespace: namespace.name });
        problem = h`<div class="problem tone-ok">${icon('check')}<div class="problem-text">
          <span class="problem-title">${t('Recovered')}</span><span class="problem-hint">${t('Last problem: {title}', { title: info.title })}</span></div></div>`;
      }
      drawer.innerHTML = h`<header class="drawer-head">
          <span class="icon-with-status">${Icons.tile(Icons.forService(service), { size: 'large', tint: group?.color })}
            <span class="status-dot" style="background:var(--${tone === 'info' ? 'accent' : tone === 'idle' ? 'idle' : tone})"></span></span>
          <div class="title"><h2 title="${service.name}">${service.name}</h2><span class="muted mono">${Messages.resourceText(service)}</span></div>
          <button class="icon-button" data-drawer="close" title="${t('Close (Esc)')}">${icon('close')}</button>
        </header>
        <div class="drawer-actions">
          ${active
            ? h`<button class="button" data-drawer="stop">${icon('stop')}${t('Stop')}</button>`
            : h`<button class="button primary" data-drawer="start">${icon('play')}${t('Start')}</button>`}
          <button class="button" data-drawer="restart" ${active ? '' : 'disabled'}>${icon('restart')}${t('Restart')}</button>
          <button class="button" data-drawer="edit">${icon('edit')}${t('Edit')}</button>
          <button class="button" data-drawer="copy-address">${icon('link')}${t('Copy address')}</button>
        </div>
        <div class="drawer-body">
          ${problem}
          <dl class="facts">${facts.map(([label, value]) => h`<dt>${label}</dt><dd>${value}</dd>`)}</dl>
          <div class="command-preview"><span class="prompt">$</span><code>${command}</code>
            <button class="icon-button small" data-drawer="copy-command" title="${t('Copy command')}">${icon('copy')}</button></div>
          <div class="logs-head">${icon('terminal')}<span>${t('Logs')}</span><span class="spacer"></span>
            <label class="import-options"><span class="switch"><input type="checkbox" data-drawer="errors-only" ${errorsOnly ? 'checked' : ''} /><span></span></span>${t('Errors only')}</label>
            <button class="icon-button small" data-drawer="copy-logs" title="${t('Copy logs')}">${icon('copy')}</button>
            <button class="icon-button small" data-drawer="clear-logs" title="${t('Clear logs')}">${icon('trash')}</button>
          </div>
          <div class="logs" role="log"></div>
        </div>`;
      renderLogs();
      if (scroll !== undefined) {
        const box = drawer.querySelector('.logs');
        if (box.scrollTop + box.clientHeight < box.scrollHeight - 30) box.scrollTop = scroll;
      }
      tick();
    }

    function tick() {
      const now = Date.now();
      drawer.querySelectorAll('[data-since]').forEach((e) => (e.textContent = I18n.duration(now - Number(e.dataset.since))));
      drawer.querySelectorAll('[data-ago]').forEach((e) => (e.textContent = I18n.ago(Number(e.dataset.ago))));
    }

    function appendLog(id, entry) {
      if (id !== current) return;
      logs.push(entry);
      if (logs.length > LOG_LIMIT) logs.splice(0, logs.length - LOG_LIMIT);
      renderLogs();
    }

    drawer.addEventListener('click', async (event) => {
      const button = event.target.closest('[data-drawer]');
      if (!button || !current) return;
      const id = current;
      switch (button.dataset.drawer) {
        case 'close':
          return close();
        case 'start':
        case 'stop':
        case 'restart':
          return actions.forward(button.dataset.drawer, [id]);
        case 'edit':
          return actions.editService(id);
        case 'copy-address':
          return actions.copyAddress(id);
        case 'copy-command':
          return actions.copy(command, t('Command copied'));
        case 'copy-logs':
          return actions.copy(logs.map((e) => `${I18n.clock(e.t)} ${e.text}`).join('\n'), t('Logs copied'));
        case 'clear-logs':
          await Native.call('forward.clearLogs', { id });
          logs = [];
          return renderLogs();
      }
    });
    drawer.addEventListener('change', (event) => {
      if (event.target.dataset.drawer === 'errors-only') {
        errorsOnly = event.target.checked;
        renderLogs();
      }
    });

    async function refreshCommand() {
      if (!current) return;
      const preview = await Native.call('command.preview', { data: Store.service(current) || {} });
      command = preview.command;
    }

    return { render, open, close, appendLog, tick, refreshCommand, get current() { return current; } };
  }

  window.Drawer = { create };
})();
