/* Add / edit a service. Suggestions come from the cluster asynchronously, the local
 * port is checked live (configuration and this machine), and the final word on
 * validity belongs to the backend. */
(() => {
  'use strict';
  const { h, icon, $, debounce } = U;
  const t = (key, params) => I18n.t(key, params);
  const KINDS = [
    ['service', 'Service'],
    ['pod', 'Pod'],
    ['deployment', 'Deployment'],
    ['statefulset', 'StatefulSet'],
    ['replicaset', 'ReplicaSet'],
  ];
  const NEW_GROUP = '__new__';
  const BLOCKING = new Set(['taken', 'busy', 'denied', 'unavailable']);

  const quote = (arg) => (/^[\w@%+=:,./-]+$/.test(arg) ? arg : `'${arg.replace(/'/g, `'\\''`)}'`);
  const joinArgs = (args) => (args || []).map(quote).join(' ');

  function create({ actions }) {
    const dialog = $('#service-dialog');
    let editing = null;
    let kind = 'service';
    let targets = [];
    let portStatus = null;
    let generation = 0;
    let iconState = { value: '', automatic: 'server' };
    let picker = null;

    const form = () => dialog.querySelector('form');
    const input = (name) => form().elements[name];

    function field(name, label, control, { span = false, hint = '', optional = false } = {}) {
      return h`<label class="field ${span ? 'span-2' : ''}" data-field="${name}">
        <span class="label">${label}${optional ? h` <span class="optional">${t('(optional)')}</span>` : ''}</span>
        ${control}<span class="hint" data-hint="${name}">${hint}</span><span class="error-text"></span></label>`;
    }

    function template(data) {
      const groups = Store.state.config.groups;
      const current = Store.state.meta.kube?.current;
      return h`<form method="dialog" novalidate>
        ${Overlays.Sheet.head(editing ? 'edit' : 'plus', editing ? t('Edit service') : t('New service'), editing ? data.name : t('Forward a port from a Kubernetes resource to this machine'))}
        <div class="sheet-body">
          <div class="paste-box">${icon('terminal')}
            <input name="paste" autocomplete="off" spellcheck="false" placeholder="${t('Paste a kubectl port-forward command to fill the form…')}" />
            <span class="paste-status" id="paste-status"></span></div>
          <div class="form-grid">
            ${field('name', t('Name'), h`<input name="name" value="${data.name}" autocomplete="off" maxlength="64" placeholder="${t('e.g. orders-postgresql')}" />`)}
            ${field('group', t('Group'), h`<select name="group">
                <option value="">${t('No group')}</option>
                ${groups.map((g) => h`<option value="${g.id}" ${g.id === data.group ? 'selected' : ''}>${g.name}</option>`)}
                <option value="${NEW_GROUP}">${t('+ New group…')}</option></select>`)}
            <div class="field span-2"><span class="label">${t('Icon')}</span>${IconPicker.markup(data.icon || '', '')}</div>
            <label class="field span-2" data-field="newGroup" hidden><span class="label">${t('New group name')}</span>
              <input name="newGroup" autocomplete="off" maxlength="64" /><span class="error-text"></span></label>
            ${field('context', t('Context'), h`<input name="context" class="ltr-input" list="dl-contexts" value="${data.context}" autocomplete="off" spellcheck="false"
                placeholder="${current ? t('Current context ({name})', { name: current }) : t('Current context')}" />`, { hint: t('Leave empty to follow kubectl’s current context.') })}
            ${field('namespace', t('Namespace'), h`<input name="namespace" class="ltr-input" list="dl-namespaces" value="${data.namespace}" autocomplete="off" spellcheck="false" />`)}
            <div class="field span-2" data-field="kind"><span class="label">${t('Resource type')}</span>
              <div class="segmented kind-picker">${KINDS.map(([value, label]) => h`<button type="button" data-kind="${value}" aria-pressed="${value === data.kind}">${t(label)}</button>`)}</div>
              <span class="error-text"></span></div>
            ${field('target', t('Resource name'), h`<input name="target" class="ltr-input" list="dl-targets" value="${data.target}" autocomplete="off" spellcheck="false" />`, { span: true })}
            ${field('remotePort', t('Remote port'), h`<input name="remotePort" class="ltr-input" list="dl-ports" value="${data.remotePort}" autocomplete="off" placeholder="5432" />`, { hint: t('The port inside the cluster.') })}
            ${field('localPort', t('Local port'), h`<span class="input-row"><input name="localPort" class="ltr-input" inputmode="numeric" value="${data.localPort}" autocomplete="off" placeholder="5432" />
                <button type="button" class="button" data-suggest title="${t('Find a free port')}">${t('Auto')}</button></span>`)}
            <details class="advanced span-2" ${data.address !== '127.0.0.1' || data.extraArgs || data.note || data.autoStart ? 'open' : ''}>
              <summary>${t('Advanced')}</summary>
              <div class="form-grid">
                ${field('address', t('Bind address'), h`<input name="address" class="ltr-input" value="${data.address}" autocomplete="off" />`, { hint: t('127.0.0.1 keeps the port private to this machine.') })}
                ${field('extraArgs', t('Extra kubectl flags'), h`<input name="extraArgs" class="ltr-input mono" value="${data.extraArgs}" autocomplete="off" spellcheck="false" placeholder="--pod-running-timeout=1m" />`, { optional: true })}
                ${field('note', t('Note'), h`<input name="note" value="${data.note}" maxlength="300" autocomplete="off" />`, { span: true, optional: true })}
                <label class="toggle-row span-2"><span class="text"><span>${t('Start automatically')}</span>
                  <small>${t('Start this forward whenever Bandar starts.')}</small></span>
                  <span class="switch"><input type="checkbox" name="autoStart" ${data.autoStart ? 'checked' : ''} /><span></span></span></label>
              </div>
            </details>
          </div>
          <div class="command-preview"><span class="prompt">$</span><code id="command-preview"></code>
            <button type="button" class="icon-button small" data-copy-command title="${t('Copy command')}">${icon('copy')}</button></div>
          <datalist id="dl-contexts">${(Store.state.meta.kube?.contexts || []).map((c) => h`<option value="${c.name}">${c.cluster}</option>`)}</datalist>
          <datalist id="dl-namespaces"></datalist><datalist id="dl-targets"></datalist><datalist id="dl-ports"></datalist>
        </div>
        <footer class="sheet-foot">
          <span class="muted" id="form-status"></span><span class="spacer"></span>
          <button class="button" data-dismiss>${t('Cancel')}</button>
          <button class="button" data-save="plain" type="submit">${t('Save')}</button>
          <button class="button primary" data-save="start" type="submit">${icon('play')}${editing ? t('Save and restart') : t('Save and start')}</button>
        </footer>
      </form>`;
    }

    // ------------------------------------------------------------ data

    function values() {
      const f = form();
      return {
        name: f.elements.name.value,
        group: f.elements.group.value,
        context: f.elements.context.value.trim(),
        namespace: f.elements.namespace.value.trim(),
        kind,
        target: f.elements.target.value.trim(),
        remotePort: f.elements.remotePort.value.trim(),
        localPort: f.elements.localPort.value.trim(),
        address: f.elements.address.value.trim() || '127.0.0.1',
        extraArgs: f.elements.extraArgs.value,
        note: f.elements.note.value,
        autoStart: f.elements.autoStart.checked,
        icon: iconState.value,
      };
    }

    function setHint(name, text, tone = '') {
      const hint = dialog.querySelector(`[data-hint="${name}"]`);
      if (!hint) return;
      hint.className = `hint ${tone}`;
      hint.innerHTML = h`${text}`;
    }

    function setErrors(errors) {
      dialog.querySelectorAll('.field').forEach((element) => {
        element.classList.remove('invalid');
        const text = element.querySelector('.error-text');
        if (text) text.textContent = '';
      });
      let first = null;
      for (const [name, error] of Object.entries(errors || {})) {
        const element = dialog.querySelector(`[data-field="${name}"]`);
        if (!element) continue;
        element.classList.add('invalid');
        element.querySelector('.error-text').textContent = Messages.field(error);
        if (name === 'extraArgs' || name === 'address') dialog.querySelector('details.advanced').open = true;
        first ??= element.querySelector('input, select, button');
      }
      first?.focus();
    }

    const preview = debounce(async () => {
      if (!dialog.open) return;
      const result = await Native.call('command.preview', { data: values() });
      const code = dialog.querySelector('#command-preview');
      if (code) code.textContent = result.command;
    }, 120);

    // ------------------------------------------------------------ cluster suggestions

    function fillList(id, options) {
      const list = dialog.querySelector(`#${id}`);
      if (list) list.innerHTML = h`${options.map(([value, label]) => h`<option value="${value}">${label || ''}</option>`)}`;
    }

    function contextName() {
      return input('context').value.trim() || Store.state.meta.kube?.current || '';
    }

    function contextDefaultNamespace() {
      const entry = (Store.state.meta.kube?.contexts || []).find((c) => c.name === contextName());
      return entry?.namespace || 'default';
    }

    const loadNamespaces = debounce(async () => {
      if (!dialog.open) return;
      const mine = ++generation;
      input('namespace').placeholder = contextDefaultNamespace();
      setHint('namespace', h`<span class="spinner"></span>${t('Loading namespaces…')}`);
      const result = await Native.call('kube.query', { op: 'namespaces', context: input('context').value.trim() });
      if (mine !== generation || !dialog.open) return;
      if (result.ok) {
        fillList('dl-namespaces', result.data.map((name) => [name]));
        setHint('namespace', t('{n} namespaces in this context', { n: I18n.num(result.data.length) }));
      } else {
        setHint('namespace', t('Suggestions unavailable: {problem}', { problem: Messages.problem(result.error, { localPort: '', kind, target: '' }).title }), 'warn');
      }
      loadTargets();
    }, 350);

    let targetGeneration = 0;
    const loadTargets = debounce(async () => {
      if (!dialog.open) return;
      const mine = ++targetGeneration;
      const namespace = input('namespace').value.trim();
      setHint('target', h`<span class="spinner"></span>${t('Loading resources…')}`);
      const result = await Native.call('kube.query', { op: 'targets', context: input('context').value.trim(), namespace, kind });
      if (mine !== targetGeneration || !dialog.open) return;
      if (result.ok) {
        targets = result.data;
        fillList('dl-targets', targets.map((item) => [item.name, item.ports.map((p) => p.port).join(', ')]));
        setHint('target', t('{n} found in {namespace}', { n: I18n.num(targets.length), namespace: namespace || contextDefaultNamespace() }));
        suggestPorts();
      } else {
        targets = [];
        setHint('target', t('Suggestions unavailable: {problem}', { problem: Messages.problem(result.error, { localPort: '', kind, target: '' }).title }), 'warn');
      }
    }, 300);

    function suggestPorts() {
      const match = targets.find((item) => item.name === input('target').value.trim());
      const ports = match?.ports || [];
      fillList('dl-ports', ports.map((p) => [p.port, p.name]));
      if (ports.length && !input('remotePort').value.trim()) {
        input('remotePort').value = ports[0].port;
        onRemoteChanged();
      }
      setHint('remotePort', ports.length ? t('Exposed: {ports}', { ports: ports.map((p) => (p.name ? `${p.port} (${p.name})` : p.port)).join(', ') }) : t('The port inside the cluster.'));
    }

    function onRemoteChanged() {
      const remote = input('remotePort').value.trim();
      if (!input('localPort').value.trim() && /^\d+$/.test(remote)) {
        input('localPort').value = remote;
        checkPort();
      }
      preview();
    }

    // ------------------------------------------------------------ live port check

    let portGeneration = 0;
    const checkPort = debounce(async () => {
      if (!dialog.open) return;
      const mine = ++portGeneration;
      const port = input('localPort').value.trim();
      if (!port) {
        portStatus = null;
        setHint('localPort', t('The port you connect to on this machine.'));
        updateButtons();
        return;
      }
      setHint('localPort', h`<span class="spinner"></span>${t('Checking…')}`);
      const result = await Native.call('port.check', { port, address: input('address').value.trim() || '127.0.0.1', exclude: editing });
      if (mine !== portGeneration || !dialog.open) return;
      portStatus = result.status;
      const messages = {
        free: [t('Port {port} is free.', { port }), 'ok'],
        own: [t('This service is using it right now.'), 'ok'],
        taken: [t('Assigned to “{service}”. Each service needs its own local port.', { service: result.service }), 'err'],
        busy: [t('In use on this machine by {owner}.', { owner: Messages.ownerText(result.owner) || t('another program') }), 'err'],
        denied: [t('Ports below 1024 need administrator rights.'), 'err'],
        unavailable: [t('The bind address does not exist on this machine.'), 'err'],
        invalid: [t('Enter a port between 1 and 65535.'), 'err'],
      };
      const [text, tone] = messages[result.status] || ['', ''];
      setHint('localPort', text, tone);
      dialog.querySelector('[data-field="localPort"]').classList.toggle('invalid', tone === 'err');
      updateButtons();
    }, 250);

    function updateButtons() {
      const blocked = BLOCKING.has(portStatus);
      dialog.querySelectorAll('[data-save]').forEach((button) => {
        button.disabled = blocked;
        button.title = blocked ? t('Choose a free local port first') : '';
      });
    }

    async function suggest() {
      const preferred = input('localPort').value.trim() || input('remotePort').value.trim() || 10000;
      const result = await Native.call('port.suggest', { preferred, address: input('address').value.trim(), exclude: editing });
      if (result.port) {
        input('localPort').value = result.port;
        checkPort();
        preview();
      }
    }

    // ------------------------------------------------------------ paste a command

    const parsePaste = debounce(async () => {
      const text = input('paste').value.trim();
      const status = dialog.querySelector('#paste-status');
      if (!text) {
        status.textContent = '';
        return;
      }
      const result = await Native.call('command.parse', { text });
      if (!result.ok) {
        status.className = 'paste-status err';
        status.textContent = Messages.importText(result.error);
        return;
      }
      const f = result.fields;
      input('context').value = f.context;
      input('namespace').value = f.namespace;
      input('target').value = f.target;
      input('remotePort').value = f.remotePort;
      input('localPort').value = f.localPort;
      input('address').value = f.address;
      input('extraArgs').value = joinArgs(f.extraArgs);
      if (!input('name').value.trim()) input('name').value = f.target;
      setKind(f.kind);
      guessIcon();
      status.className = 'paste-status ok';
      status.textContent = t('Form filled ✓');
      checkPort();
      loadNamespaces();
      preview();
    }, 200);

    // ------------------------------------------------------------ wiring

    function setKind(value) {
      kind = value;
      dialog.querySelectorAll('[data-kind]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.kind === value)));
      loadTargets();
      preview();
    }

    function guessIcon() {
      const v = values();
      iconState.automatic = Icons.guess({ name: v.name, target: v.target, remotePort: Number(v.remotePort) || v.remotePort, localPort: Number(v.localPort) });
      picker?.refresh();
    }

    function bind() {
      const f = form();
      f.addEventListener('input', (event) => {
        const name = event.target.name;
        event.target.closest('.field')?.classList.remove('invalid');
        if (name === 'paste') return parsePaste();
      if (name === 'name' || name === 'target' || name === 'remotePort' || name === 'localPort') guessIcon();
        if (name === 'context') loadNamespaces();
        if (name === 'namespace') loadTargets();
        if (name === 'target') suggestPorts();
        if (name === 'remotePort') onRemoteChanged();
        if (name === 'localPort' || name === 'address') checkPort();
        preview();
      });
      f.elements.group.addEventListener('change', () => {
        const fresh = f.elements.group.value === NEW_GROUP;
        dialog.querySelector('[data-field="newGroup"]').hidden = !fresh;
        if (fresh) f.elements.newGroup.focus();
      });
      dialog.querySelectorAll('[data-kind]').forEach((button) => (button.onclick = () => setKind(button.dataset.kind)));
      dialog.querySelector('[data-suggest]').onclick = suggest;
      dialog.querySelector('[data-copy-command]').onclick = () => actions.copy(dialog.querySelector('#command-preview').textContent, t('Command copied'));
      f.addEventListener('submit', (event) => {
        event.preventDefault();
        save(event.submitter?.dataset.save === 'start');
      });
    }

    async function save(start) {
      const data = values();
      const buttons = dialog.querySelectorAll('[data-save]');
      buttons.forEach((button) => (button.disabled = true));
      dialog.querySelector('#form-status').innerHTML = h`<span class="spinner"></span> ${t('Saving…')}`;
      try {
        if (data.group === NEW_GROUP) {
          const created = await Native.call('group.save', { data: { name: input('newGroup').value } });
          if (!created.ok) {
            setErrors({ newGroup: created.errors.name });
            return;
          }
          data.group = created.id;
        }
        const result = await Native.call('service.save', { id: editing, data, start });
        if (!result.ok) {
          setErrors(result.errors);
          return;
        }
        dialog.close();
        Overlays.Toast.show({ tone: 'ok', title: start ? t('Saved and started') : t('Saved'), body: data.name });
      } finally {
        if (dialog.open) {
          dialog.querySelector('#form-status').textContent = '';
          updateButtons();
          buttons.forEach((button) => (button.disabled = BLOCKING.has(portStatus)));
        }
      }
    }

    function open({ id = null, group = '', prefill = null } = {}) {
      editing = id;
      targets = [];
      portStatus = null;
      const service = id ? Store.service(id) : null;
      const base = { name: '', group, context: '', namespace: '', kind: 'service', target: '', remotePort: '', localPort: '', address: '127.0.0.1', extraArgs: '', autoStart: false, note: '', icon: '' };
      const data = service ? { ...service, extraArgs: joinArgs(service.extraArgs) } : { ...base, ...(prefill || {}) };
      kind = data.kind;
      iconState = { value: data.icon || '', automatic: 'server' };
      Overlays.Sheet.open(dialog, template(data), { onClose: () => (editing = null) });
      bind();
      picker = IconPicker.bind(dialog.querySelector('.icon-picker'), iconState, () => {});
      guessIcon();
      preview();
      loadNamespaces();
      if (data.localPort) checkPort();
      else setHint('localPort', t('The port you connect to on this machine.'));
      (service ? input('name') : input('paste')).focus();
    }

    return { open };
  }

  window.ServiceForm = { create, joinArgs };
})();
