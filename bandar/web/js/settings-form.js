/* Settings apply immediately and are stored in the JSON configuration. */
(() => {
  'use strict';
  const { h, icon, $ } = U;
  const t = (key, params) => I18n.t(key, params);
  const PALETTES = ['ocean', 'forest', 'violet', 'rose', 'amber', 'slate'];
  const SHORTCUTS = [
    ['Ctrl+N', 'New service'],
    ['Ctrl+G', 'New group'],
    ['Ctrl+I', 'Import and export'],
    ['Ctrl+,', 'Settings'],
    ['/', 'Search'],
    ['Ctrl+A', 'Select all visible services'],
    ['Delete', 'Delete selected services'],
    ['P', 'Pin or unpin the focused service'],
    ['Esc', 'Close panels or clear the selection'],
  ];

  function create({ actions }) {
    const dialog = $('#settings-dialog');

    function segmented(key, options, value) {
      return h`<div class="segmented" data-setting="${key}">${options.map(([option, label]) =>
        h`<button type="button" data-value="${option}" aria-pressed="${option === value}">${label}</button>`)}</div>`;
    }

    function toggle(key, title, description, value) {
      return h`<label class="setting"><span class="text"><span>${title}</span><small>${description}</small></span>
        <span class="switch"><input type="checkbox" data-setting="${key}" ${value ? 'checked' : ''} /><span></span></span></label>`;
    }

    function number(key, title, description, value, min, max) {
      return h`<label class="setting"><span class="text"><span>${title}</span><small>${description}</small></span>
        <input class="input ltr-input" type="number" data-setting="${key}" value="${value}" min="${min}" max="${max}" /></label>`;
    }

    function text(key, title, description, value, placeholder) {
      return h`<label class="setting"><span class="text"><span>${title}</span><small>${description}</small></span>
        <input class="input wide ltr-input mono" data-setting="${key}" value="${value}" placeholder="${placeholder}" spellcheck="false" /></label>`;
    }

    function body(s) {
      const info = Store.state.info;
      const meta = Store.state.meta;
      return h`
        <section class="settings-section"><h3>${t('Appearance')}</h3>
          <div class="setting"><span class="text"><span>${t('Theme')}</span></span>
            ${segmented('theme', [['auto', t('System')], ['light', t('Light')], ['dark', t('Dark')]], s.theme)}</div>
          <div class="setting"><span class="text"><span>${t('Language')}</span></span>
            ${segmented('language', Header.LANGUAGES, s.language)}</div>
          <div class="setting"><span class="text"><span>${t('Density')}</span></span>
            ${segmented('density', [['comfortable', t('Comfortable')], ['compact', t('Compact')]], s.density)}</div>
          <div class="palette-grid">${PALETTES.map((p) => h`<button type="button" class="palette-choice" data-palette="${p}" data-setting-palette="${p}" aria-pressed="${p === s.palette}">
            <span class="palette-swatch"></span>${t(p)}</button>`)}</div>
        </section>
        <section class="settings-section"><h3>${t('Connections')}</h3>
          ${toggle('autoRetry', t('Reconnect automatically'), t('Retry with exponential backoff when a tunnel drops or the cluster is unreachable.'), s.autoRetry)}
          ${number('maxRetries', t('Maximum attempts'), t('0 keeps trying forever.'), s.maxRetries, 0, 1000)}
          ${number('retryMaxDelay', t('Longest wait between attempts (s)'), t('Backoff doubles from one second up to this limit.'), s.retryMaxDelay, 2, 600)}
          ${number('startTimeout', t('Start timeout (s)'), t('How long kubectl may take to start listening.'), s.startTimeout, 5, 300)}
          ${number('clusterCheckInterval', t('Check cluster connectivity every (s)'), t('Notices lost connectivity (network, VPN or cluster down) within seconds, rebuilds the tunnels and notifies you. 0 turns it off.'), s.clusterCheckInterval, 0, 600)}
          ${number('healthCheckInterval', t('Health check every (s)'), t('Opens a test connection through each tunnel to detect silent failures. 0 turns it off.'), s.healthCheckInterval, 0, 3600)}
        </section>
        <section class="settings-section"><h3>${t('Behavior')}</h3>
          <div class="setting"><span class="text"><span>${t('When Bandar starts')}</span><small>${t('Services marked “start automatically” always start.')}</small></span>
            ${segmented('startup', [['restore', t('Resume previous forwards')], ['manual', t('Start nothing else')]], s.startup)}</div>
          <div class="setting"><span class="text"><span>${t('When the window is closed')}</span>
            <small>${t('In the background, forwards stay up while the window is hidden.')}</small></span>
            ${segmented('closeAction', [['ask', t('Ask')], ['background', t('Run in background')], ['quit', t('Quit')]], s.closeAction)}</div>
          <div class="setting"><span class="text"><span>${t('Desktop notifications')}</span>
            <small>${t('A system notification when a forward drops, fails to start or reconnects.')}</small></span>
            ${segmented('notifications', [['always', t('Always')], ['background', t('In background')], ['off', t('Off')]], s.notifications)}</div>
          ${toggle('confirmDelete', t('Confirm before deleting'), t('Ask before services or groups are removed.'), s.confirmDelete)}
        </section>
        <section class="settings-section"><h3>kubectl</h3>
          ${text('kubectl', t('kubectl program'), t('A name on PATH or a full path.'), s.kubectl, 'kubectl')}
          ${text('kubeconfig', t('kubeconfig file'), t('Empty uses KUBECONFIG or ~/.kube/config.'), s.kubeconfig, '~/.kube/config')}
          <div class="setting"><span class="text"><span class="mono" dir="ltr">${meta.kubeconfig || ''}</span>
            <small>${t('The kubeconfig in use. Edit it to add clusters, users or contexts.')}</small></span>
            <span class="toolbar-group"><button type="button" class="button" data-shell="kubeconfig">${icon('edit')}${t('Open file')}</button>
            <button type="button" class="icon-button" data-shell="kubeconfig-folder" title="${t('Open kubeconfig folder')}">${icon('folder')}</button></span></div>
          <div class="setting"><span class="text"><span>${t('Detected')}</span></span>
            <span class="mono muted">${meta.kube?.version || t('unknown')} · ${t('{n} contexts', { n: I18n.num(meta.kube?.contexts?.length || 0) })}</span></div>
        </section>
        <section class="settings-section"><h3>${t('Configuration file')}</h3>
          <div class="setting"><span class="text"><span class="mono" dir="ltr">${meta.configPath}</span>
            <small>${t('Services, groups and settings live in this JSON file. Edits made by hand are picked up automatically.')}</small></span>
            <span class="toolbar-group"><button type="button" class="button" data-shell="reveal">${icon('folder')}${t('Open folder')}</button>
            <button type="button" class="icon-button" data-shell="copy-path" title="${t('Copy path')}">${icon('copy')}</button></span></div>
        </section>
        <section class="settings-section"><h3>${t('Keyboard shortcuts')}</h3>
          <div class="shortcuts">${SHORTCUTS.map(([keys, label]) => h`<kbd>${keys}</kbd><span>${t(label)}</span>`)}</div>
        </section>
        <section class="settings-section"><h3>${t('About')}</h3>
          <div class="setting"><span class="text"><span><strong>Bandar</strong> ${info.version}</span>
            <small>${t('Development by')} <span translate="no">${info.author}</span> · ${t('Forward. Watch. Recover.')}</small></span>
            <button type="button" class="button" data-shell="github">${icon('github')}GitHub</button></div>
        </section>`;
    }

    function render() {
      const container = dialog.querySelector('.sheet-body');
      if (!container) return;
      const scroll = container.scrollTop;
      const focused = document.activeElement?.dataset?.setting;
      container.innerHTML = h`${body(Store.settings)}`;
      container.scrollTop = scroll;
      if (focused) container.querySelector(`input[data-setting="${focused}"]`)?.focus();
    }

    function open() {
      Overlays.Sheet.open(
        dialog,
        h`<form method="dialog">${Overlays.Sheet.head('settings', t('Settings'), t('Saved instantly to the configuration file'))}
          <div class="sheet-body"></div>
          <footer class="sheet-foot"><span class="spacer"></span><button class="button primary" data-dismiss>${t('Done')}</button></footer></form>`
      );
      render();
      const container = dialog.querySelector('.sheet-body');
      container.addEventListener('click', (event) => {
        const choice = event.target.closest('[data-value]');
        const group = choice?.closest('[data-setting]');
        if (group) actions.settings({ [group.dataset.setting]: choice.dataset.value });
        const palette = event.target.closest('[data-setting-palette]');
        if (palette) actions.settings({ palette: palette.dataset.settingPalette });
        const shell = event.target.closest('[data-shell]')?.dataset.shell;
        if (shell === 'reveal') Native.call('shell.revealConfig');
        if (shell === 'copy-path') actions.copy(Store.state.meta.configPath, t('Path copied'));
        if (shell === 'github') Native.call('shell.openUrl', { url: Store.state.info.repository });
        if (shell === 'kubeconfig') actions.openKubeconfig(false);
        if (shell === 'kubeconfig-folder') actions.openKubeconfig(true);
      });
      container.addEventListener('change', (event) => {
        const key = event.target.dataset.setting;
        if (!key) return;
        const value = event.target.type === 'checkbox' ? event.target.checked : event.target.type === 'number' ? Number(event.target.value) : event.target.value.trim();
        actions.settings({ [key]: value });
      });
    }

    return { open, render, get isOpen() { return dialog.open; } };
  }

  window.SettingsForm = { create };
})();
