/* Sidebar: views, groups (click to focus, drag to reorder or to receive services)
 * and the kubeconfig status. */
(() => {
  'use strict';
  const { h, icon, $, on } = U;
  const { UNGROUPED } = ViewModel;
  const t = (key, params) => I18n.t(key, params);

  function create({ actions }) {
    const nav = $('#view-nav');
    const groups = $('#group-nav');
    const kube = $('#kube-note');
    const envFilter = $('#env-filter');

    const SHORT = { production: 'PROD', staging: 'STG', development: 'DEV', testing: 'TEST', legacy: 'OLD' };

    function groupItem(key, name, color, services, current, group = null) {
      const environment = group?.environment || '';
      const health = ViewModel.health(Store.state, services);
      const tone = health.errors ? 'err' : health.connecting ? 'warn' : health.healthy ? 'ok' : 'idle';
      return h`<li data-color="${color}">
        <button class="group-link" data-nav-group="${key}" aria-current="${current}" ${key === UNGROUPED ? '' : h`draggable="true" data-drag="group"`}
          title="${name}">
          ${group?.icon ? Icons.tile(group.icon, 'small') : h`<span class="group-swatch"></span>`}<span class="group-label">${name}</span>
          ${group?.pinned ? h`<span class="pin-mark">${icon('pin')}</span>` : ''}
          ${environment ? h`<span class="env small" data-env="${environment}" title="${t(ServiceList.ENV_LABELS[environment])}">${t(SHORT[environment])}</span>` : ''}
          <span class="group-health">${health.running ? h`<span class="status-dot" style="background:var(--${tone})"></span>` : ''}
          ${I18n.num(health.running)}/${I18n.num(health.total)}</span>
        </button></li>`;
    }

    function render(state) {
      const counts = ViewModel.counts(state);
      nav.querySelectorAll('[data-view]').forEach((button) => {
        button.setAttribute('aria-current', String(state.ui.view === button.dataset.view && !state.ui.group));
      });
      nav.querySelectorAll('[data-count]').forEach((badge) => {
        const value = counts[badge.dataset.count];
        badge.textContent = value || badge.dataset.count === 'all' ? I18n.num(value) : '';
      });
      const present = Object.keys(ServiceList.ENV_LABELS).filter((env) => state.config.groups.some((g) => g.environment === env));
      envFilter.hidden = present.length < 1;
      envFilter.innerHTML = h`${present.map((env) => h`<button class="env small" data-env="${env}" data-env-filter="${env}" aria-pressed="${state.ui.env === env}"
        title="${t('Show only {env} groups', { env: t(ServiceList.ENV_LABELS[env]) })}">${t(SHORT[env])}</button>`)}`;
      const ungrouped = state.config.services.filter((s) => !s.group || !Store.group(s.group));
      groups.innerHTML = h`${state.config.groups.map((group) =>
        groupItem(group.id, group.name, group.color, state.config.services.filter((s) => s.group === group.id), state.ui.group === group.id, group)
      )}${ungrouped.length || !state.config.groups.length ? groupItem(UNGROUPED, t('Ungrouped'), 'slate', ungrouped, state.ui.group === UNGROUPED) : ''}`;

      const info = state.meta.kube || {};
      kube.classList.toggle('ok', !!info.current);
      kube.classList.toggle('err', !!info.error);
      const text = $('#kube-note-text');
      if (info.error) text.textContent = t('kubeconfig: {problem}', { problem: Messages.problem(info.error, { localPort: '', kind: 'service', target: '' }).title });
      else if (info.current) text.textContent = t('Current context: {name}', { name: info.current });
      else text.textContent = t('No current context');
      kube.title = (info.contexts || []).map((c) => c.name).join(', ');
    }

    on(nav, 'click', '[data-view]', (_event, button) => {
      Store.ui({ view: button.dataset.view, group: null });
    });
    on(envFilter, 'click', '[data-env-filter]', (_event, button) => {
      const env = button.dataset.envFilter;
      Store.ui({ env: Store.state.ui.env === env ? null : env, group: null });
    });
    on(groups, 'click', '[data-nav-group]', (_event, button) => {
      const key = button.dataset.navGroup;
      Store.ui({ group: Store.state.ui.group === key ? null : key, view: 'all' });
    });
    groups.addEventListener('contextmenu', (event) => {
      const button = event.target.closest('[data-nav-group]');
      if (!button) return;
      event.preventDefault();
      actions.groupMenu(button.dataset.navGroup, { x: event.clientX, y: event.clientY });
    });
    $('#sidebar-new-group').onclick = () => actions.newGroup();
    $('#sort-groups').onclick = () => actions.sortGroups();
    window.DragDrop.create({ root: groups, actions });
    return { render };
  }

  window.Sidebar = { create };
})();
