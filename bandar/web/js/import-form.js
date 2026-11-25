/* Import a list of kubectl port-forward commands (optionally named and grouped)
 * with a line-by-line preview before anything changes; export writes the same format. */
(() => {
  'use strict';
  const { h, icon, $, debounce } = U;
  const t = (key, params) => I18n.t(key, params);
  const EXAMPLE = [
    '# One service per line:  name = kubectl … port-forward …',
    '# A [group] line puts the services below it into that group; [] ends the group.',
    '# Optionally tag the environment: @production, @staging, @development, @testing or @legacy.',
    '[orders @production]',
    'orders-postgresql = kubectl --context main -n orders-api port-forward svc/orders-psql-master 5432:5432',
    'orders-redis = kubectl --context main -n orders-api port-forward svc/orders-redis-haproxy 6379:6379',
    '',
    '[]',
    '# Without a name, the resource name is used.',
    'kubectl --context prod -n chat port-forward svc/chat-redis-main 6381:6379',
  ].join('\n');
  const LOOK = {
    add: ['plus', 'ok', 'New'],
    update: ['restart', 'info', 'Update'],
    group: ['layers', 'info', 'Group'],
    skip: ['info', 'idle', 'Skipped'],
    error: ['alert', 'err', 'Error'],
  };

  function create() {
    const dialog = $('#import-dialog');
    let latest = null;

    function line(entry) {
      const [iconName, tone, label] = LOOK[entry.action];
      let text = '';
      if (entry.action === 'error' || entry.action === 'skip') text = Messages.importText(entry.detail);
      else if (entry.action === 'group')
        text = entry.name ? t('{n} services join this group', { n: I18n.num(entry.detail.count) }) : t('Following services get no group');
      else {
        const d = entry.detail;
        text = `${d.group ? `[${d.group}] ` : ''}${d.context || t('current context')} · ${d.namespace || 'default'} · ${d.resource} · ${d.ports}`;
      }
      return h`<div class="import-line ${entry.action} tone-${tone}" title="${entry.text}">
        <span class="line-no">${entry.line}</span>${icon(iconName)}
        <div class="what"><strong>${entry.name || (entry.action === 'group' ? t('No group') : t(label))}${entry.name ? h` <span class="muted">· ${t(label)}</span>` : ''}</strong><small>${text}</small></div></div>`;
    }

    const preview = debounce(async () => {
      const text = dialog.querySelector('textarea').value;
      const update = dialog.querySelector('#import-update').checked;
      const result = await Native.call('import.preview', { text, update });
      latest = result;
      const s = result.summary;
      const summary = dialog.querySelector('.import-summary');
      const chips = [
        s.add && h`<span class="badge tone-ok">${t('{n} new', { n: I18n.num(s.add) })}</span>`,
        s.update && h`<span class="badge tone-info">${t('{n} updated', { n: I18n.num(s.update) })}</span>`,
        s.group && h`<span class="badge tone-info">${t('{n} groups', { n: I18n.num(s.group) })}</span>`,
        s.skip && h`<span class="badge tone-idle">${t('{n} skipped', { n: I18n.num(s.skip) })}</span>`,
        s.error && h`<span class="badge tone-err">${t('{n} errors', { n: I18n.num(s.error) })}</span>`,
      ].filter(Boolean);
      summary.innerHTML = chips.length ? h`${chips}` : h`<span class="muted">${t('Nothing to import yet')}</span>`;
      const lines = dialog.querySelector('.import-lines');
      lines.innerHTML = result.lines.length
        ? h`${result.lines.map(line)}`
        : h`<div class="import-empty">${t('Paste commands on the left to see what will be imported.')}</div>`;
      const changes = (s.add || 0) + (s.update || 0);
      const button = dialog.querySelector('[data-import]');
      button.disabled = !changes;
      button.lastChild.textContent = changes ? t('Import {n} changes', { n: I18n.num(changes) }) : t('Import');
    }, 200);

    function open() {
      Overlays.Sheet.open(
        dialog,
        h`<form method="dialog">
          ${Overlays.Sheet.head('import', t('Import and export'), t('One service per line: name = kubectl … port-forward …  ·  [group] starts a group'))}
          <div class="sheet-body"><div class="import-layout">
            <textarea spellcheck="false" placeholder="${EXAMPLE}" aria-label="${t('Commands')}"></textarea>
            <div class="import-preview"><div class="import-summary"></div><div class="import-lines"></div></div>
          </div></div>
          <footer class="sheet-foot">
            <label class="import-options"><span class="switch"><input type="checkbox" id="import-update" checked /><span></span></span>${t('Update services that already exist')}</label>
            <button type="button" class="button ghost" data-example>${t('Insert example')}</button>
            <button type="button" class="button ghost" data-export title="${t('Copy all services in this format')}">${icon('copy')}${t('Export current list')}</button>
            <span class="spacer"></span>
            <button class="button" data-dismiss>${t('Cancel')}</button>
            <button class="button primary" data-import disabled>${icon('import')}<span>${t('Import')}</span></button>
          </footer></form>`
      );
      const textarea = dialog.querySelector('textarea');
      textarea.addEventListener('input', preview);
      dialog.querySelector('#import-update').addEventListener('change', preview);
      dialog.querySelector('[data-example]').onclick = () => {
        textarea.value = EXAMPLE;
        preview();
      };
      dialog.querySelector('[data-export]').onclick = async () => {
        const ids = Store.state.ui.selected.size ? [...Store.state.ui.selected] : undefined;
        const result = await Native.call('import.export', { ids });
        textarea.value = result.text;
        preview();
        Native.call('shell.copy', { text: result.text });
        Overlays.Toast.show({ tone: 'ok', title: t('List copied to the clipboard'), body: ids ? t('{n} selected services', { n: I18n.num(ids.length) }) : t('All services'), key: 'copy' });
      };
      dialog.querySelector('[data-import]').onclick = async (event) => {
        event.preventDefault();
        const result = await Native.call('import.apply', {
          text: textarea.value,
          update: dialog.querySelector('#import-update').checked,
        });
        if (!result.ok) return;
        dialog.close();
        const s = result.summary;
        Overlays.Toast.show({
          tone: s.error ? 'warn' : 'ok',
          title: t('Import finished'),
          body: t('{added} added, {updated} updated, {errors} skipped with errors', {
            added: I18n.num(s.add || 0),
            updated: I18n.num(s.update || 0),
            errors: I18n.num(s.error || 0),
          }),
        });
      };
      preview();
      textarea.focus();
      latest = null;
    }

    return { open, get latest() { return latest; } };
  }

  window.ImportForm = { create };
})();
