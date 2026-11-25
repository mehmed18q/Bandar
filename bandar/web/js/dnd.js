/* Drag & drop for manual ordering: services within and across groups, and groups
 * themselves. Shared by the list and the sidebar; the drop becomes one request. */
(() => {
  'use strict';
  const { UNGROUPED } = ViewModel;
  const MARKS = ['drop-before', 'drop-after', 'drop-into', 'drop-target', 'dragging'];
  let payload = null;
  const endListeners = [];

  function clearMarks() {
    document.querySelectorAll(MARKS.map((c) => `.${c}`).join(',')).forEach((element) => element.classList.remove(...MARKS));
  }

  function begin(event, data, image) {
    payload = data;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', data.id);
    if (image) event.dataTransfer.setDragImage(image, 24, 18);
    Store.state.ui.dragging = true;
    requestAnimationFrame(() => image?.classList.add('dragging'));
  }

  function finish() {
    payload = null;
    Store.state.ui.dragging = false;
    clearMarks();
    endListeners.forEach((listener) => listener());
  }

  /** The id that should follow ``id`` once dropped after ``anchor`` (null: last). */
  function serviceAfter(anchor, moving) {
    const group = Store.service(anchor)?.group || '';
    const members = Store.state.config.services.filter((s) => (s.group || '') === group && s.id !== moving);
    const index = members.findIndex((s) => s.id === anchor);
    return members[index + 1]?.id ?? null;
  }

  function groupAfter(anchor, moving) {
    const groups = Store.state.config.groups.filter((g) => g.id !== moving);
    const index = groups.findIndex((g) => g.id === anchor);
    return groups[index + 1]?.id ?? null;
  }

  const half = (event, element) => {
    const box = element.getBoundingClientRect();
    return event.clientY < box.top + box.height / 2 ? 'before' : 'after';
  };

  /** Resolve where a drop over ``event.target`` would land, or null. */
  function target(event) {
    if (!payload) return null;
    const element = event.target;
    if (payload.type === 'service') {
      const row = element.closest('.service-row');
      if (row && row.dataset.id !== payload.id && !Store.settings.sortKey) {
        return { element: row, mark: `drop-${half(event, row)}`, kind: 'row', id: row.dataset.id, group: row.dataset.group };
      }
      const into = element.closest('[data-group-row], [data-empty-group], [data-nav-group]');
      if (into) {
        const group = into.dataset.groupRow || into.dataset.emptyGroup || into.dataset.navGroup;
        return { element: into, mark: into.dataset.navGroup ? 'drop-target' : 'drop-into', kind: 'into', group };
      }
      return null;
    }
    const groupElement = element.closest('[data-group-row], [data-nav-group]');
    const id = groupElement && (groupElement.dataset.groupRow || groupElement.dataset.navGroup);
    if (!id || id === UNGROUPED || id === payload.id) return null;
    const holder = groupElement.closest('li') || groupElement;
    return { element: holder, mark: `drop-${half(event, groupElement)}`, kind: 'group', id };
  }

  function drop(found, actions) {
    if (payload.type === 'service') {
      if (found.kind === 'row') {
        const before = found.mark === 'drop-before' ? found.id : serviceAfter(found.id, payload.id);
        actions.moveService(payload.id, found.group, before);
      } else {
        actions.moveService(payload.id, found.group, null);
      }
    } else {
      const before = found.mark === 'drop-before' ? found.id : groupAfter(found.id, payload.id);
      actions.moveGroup(payload.id, before);
    }
  }

  function create({ root, actions }) {
    root.addEventListener('dragstart', (event) => {
      const handle = event.target.closest?.('[data-drag]');
      if (!handle) return;
      const type = handle.dataset.drag;
      const holder =
        type === 'service'
          ? handle.closest('.service-row')
          : handle.closest('[data-group-row]')?.parentElement || handle.closest('li');
      const id =
        type === 'service'
          ? holder.dataset.id
          : handle.closest('[data-group-row]')?.dataset.groupRow || handle.closest('[data-nav-group]')?.dataset.navGroup;
      begin(event, { type, id }, holder);
    });
    root.addEventListener('dragover', (event) => {
      const found = target(event);
      clearMarks();
      if (!found) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      found.element.classList.add(found.mark);
    });
    root.addEventListener('dragleave', (event) => {
      if (!root.contains(event.relatedTarget)) clearMarks();
    });
    root.addEventListener('drop', (event) => {
      const found = target(event);
      if (!found) return;
      event.preventDefault();
      drop(found, actions);
      finish();
    });
    root.addEventListener('dragend', finish);
    return { onEnd: (listener) => endListeners.push(listener) };
  }

  window.DragDrop = { create };
})();
