/* Create / edit a group: name, color, environment, note and members, with a live
 * preview of how the group row will look. */
(() => {
  'use strict';
  const { h, icon, $ } = U;
  const t = (key, params) => I18n.t(key, params);
  const COLORS = ['blue', 'teal', 'green', 'amber', 'orange', 'red', 'pink', 'violet', 'slate'];
  const ENVIRONMENTS = ['', 'production', 'staging', 'development', 'testing', 'legacy'];

  function create() {
    const dialog = $('#group-dialog');
    let editing = null;
    let color = 'blue';
    let environment = '';

    const envLabel = (env) => (env ? t(ServiceList.ENV_LABELS[env]) : t('Not set'));

    function member(service, checked) {
      const other = service.group && service.group !== editing ? Store.group(service.group) : null;
      return h`<label class="${checked ? 'checked' : ''}" data-name="${`${service.name} ${service.target}`.toLowerCase()}">
        <input type="checkbox" class="check" value="${service.id}" ${checked ? 'checked' : ''} />
        <span class="member-text"><span class="member-name">${service.name}</span>
          <span class="member-target">${Messages.resourceText(service)} · ${service.localPort}</span></span>
        ${other ? h`<span class="member-group" data-color="${other.color}" title="${t('Currently in {group}', { group: other.name })}">${other.name}</span>` : ''}
      </label>`;
    }

    function template(group, selected) {
      const services = Store.state.config.services;
      return h`<form method="dialog" novalidate>
        ${Overlays.Sheet.head('layers', group ? t('Edit group') : t('New group'), t('Group services to start, stop and watch them together'))}
        <div class="sheet-body"><div class="form-grid">
          <div class="span-2 group-preview" data-color="${color}" id="group-preview"></div>
          <label class="field span-2" data-field="name"><span class="label">${t('Name')}</span>
            <input name="name" value="${group?.name || ''}" maxlength="64" autocomplete="off" placeholder="${t('e.g. payments')}" />
            <span class="error-text"></span></label>
          <div class="field span-2"><span class="label">${t('Color')}</span>
            <div class="color-picker">${COLORS.map((c) => h`<button type="button" data-color="${c}" data-pick-color="${c}" aria-pressed="${c === color}" title="${t(c)}">${icon('check')}</button>`)}</div></div>
          <div class="field span-2"><span class="label">${t('Environment')}</span>
            <div class="env-grid">${ENVIRONMENTS.map((env) => h`<button type="button" class="env-option" data-env="${env}" data-pick-env="${env}" aria-pressed="${env === environment}">
              <span class="env-dot"></span><span>${envLabel(env)}</span></button>`)}</div>
            <span class="hint">${t('Shown as a colored badge so production, staging and legacy groups are easy to tell apart.')}</span></div>
          <label class="field span-2"><span class="label">${t('Note')} <span class="optional">${t('(optional)')}</span></span>
            <input name="note" value="${group?.note || ''}" maxlength="300" autocomplete="off" /></label>
          <div class="field span-2">
            <div class="member-head"><span class="label">${t('Services')} <span class="optional" id="member-count"></span></span>
              ${services.length ? h`<input class="input" id="member-filter" type="search" placeholder="${t('Filter services…')}" />
              <button type="button" class="button ghost" data-members="all">${t('All')}</button>
              <button type="button" class="button ghost" data-members="none">${t('None')}</button>` : ''}</div>
            <div class="member-list">${services.length ? services.map((s) => member(s, selected.has(s.id))) : h`<div class="member-empty">${t('No services yet. You can add services to this group later.')}</div>`}</div>
            <span class="hint">${t('A service belongs to one group; checking it here moves it.')}</span>
          </div>
        </div></div>
        <footer class="sheet-foot"><span class="spacer"></span>
          <button class="button" data-dismiss>${t('Cancel')}</button>
          <button class="button primary" type="submit">${group ? t('Save') : t('Create group')}</button></footer>
      </form>`;
    }

    function refresh() {
      const form = dialog.querySelector('form');
      const checked = dialog.querySelectorAll('.member-list input:checked').length;
      const preview = dialog.querySelector('#group-preview');
      preview.dataset.color = color;
      preview.innerHTML = h`<strong>${form.elements.name.value.trim() || t('Group name')}</strong>
        ${environment ? h`<span class="env" data-env="${environment}">${envLabel(environment)}</span>` : ''}
        <span class="muted">${t('{n} services', { n: I18n.num(checked) })}</span>`;
      const count = dialog.querySelector('#member-count');
      if (count) count.textContent = t('{n} of {total} selected', { n: I18n.num(checked), total: I18n.num(Store.state.config.services.length) });
      dialog.querySelectorAll('.member-list label').forEach((label) => label.classList.toggle('checked', label.querySelector('input').checked));
    }

    function open(id = null, preselect = []) {
      editing = id;
      const group = id ? Store.group(id) : null;
      const used = new Set(Store.state.config.groups.map((g) => g.color));
      color = group?.color || COLORS.find((c) => !used.has(c)) || 'blue';
      environment = group?.environment || '';
      const selected = new Set(preselect);
      for (const s of Store.state.config.services) if (id && s.group === id) selected.add(s.id);
      Overlays.Sheet.open(dialog, template(group, selected));
      const form = dialog.querySelector('form');
      refresh();
      dialog.addEventListener('click', onClick);
      dialog.onclose = () => dialog.removeEventListener('click', onClick);
      form.addEventListener('input', (event) => {
        if (event.target.id === 'member-filter') {
          const query = event.target.value.trim().toLowerCase();
          dialog.querySelectorAll('.member-list label').forEach((label) => (label.hidden = !label.dataset.name.includes(query)));
          return;
        }
        if (event.target.name === 'name') dialog.querySelector('[data-field="name"]').classList.remove('invalid');
        refresh();
      });
      form.addEventListener('change', refresh);
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        save(form);
      });
      form.elements.name.focus();
    }

    function onClick(event) {
      const colorButton = event.target.closest('[data-pick-color]');
      const envButton = event.target.closest('[data-pick-env]');
      const members = event.target.closest('[data-members]');
      if (colorButton) {
        color = colorButton.dataset.pickColor;
        dialog.querySelectorAll('[data-pick-color]').forEach((b) => b.setAttribute('aria-pressed', String(b === colorButton)));
      } else if (envButton) {
        environment = envButton.dataset.pickEnv;
        dialog.querySelectorAll('[data-pick-env]').forEach((b) => b.setAttribute('aria-pressed', String(b === envButton)));
      } else if (members) {
        const all = members.dataset.members === 'all';
        dialog.querySelectorAll('.member-list label:not([hidden]) input').forEach((box) => (box.checked = all));
      } else return;
      refresh();
    }

    async function save(form) {
      const services = [...dialog.querySelectorAll('.member-list input:checked')].map((box) => box.value);
      const name = form.elements.name.value;
      const result = await Native.call('group.save', {
        id: editing,
        data: { name, color, environment, note: form.elements.note.value },
        services,
      });
      if (!result.ok) {
        const field = dialog.querySelector('[data-field="name"]');
        field.classList.add('invalid');
        field.querySelector('.error-text').textContent = Messages.field(result.errors.name);
        form.elements.name.focus();
        return;
      }
      const created = !editing;
      dialog.close();
      Overlays.Toast.show({ tone: 'ok', title: created ? t('Group created') : t('Group saved'), body: name });
    }

    return { open };
  }

  window.GroupForm = { create };
})();
