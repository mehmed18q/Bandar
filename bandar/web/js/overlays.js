/* Shared overlays: anchored menus, toasts, a confirmation dialog and modal sheets. */
(() => {
  'use strict';
  const { h, icon, $ } = U;
  const t = (key, params) => I18n.t(key, params);

  // ------------------------------------------------------------------ menu
  const Menu = (() => {
    const element = $('#menu');
    let actions = [];
    let restoreFocus = null;

    function render(items) {
      actions = [];
      return items.map((item) => {
        if (item === '-') return h`<hr />`;
        if (item.heading) return h`<div class="menu-label">${item.heading}</div>`;
        if (item.note) return h`<div class="menu-note">${item.note}</div>`;
        const index = actions.push(item) - 1;
        const swatch = item.color ? h`<span class="swatch" data-color="${item.color}"></span>` : '';
        return h`<button role="menuitem" data-index="${index}" class="${item.danger ? 'danger' : ''}"
          ${item.disabled ? h`disabled` : ''} ${item.checked ? h`aria-checked="true"` : ''}>
          ${item.icon ? icon(item.icon) : h`<svg aria-hidden="true"></svg>`}${swatch}<span>${item.label}</span>
          ${item.sub ? h`<span class="menu-sub" dir="ltr">${item.sub}</span>` : ''}
          ${item.shortcut ? h`<span class="shortcut" dir="ltr">${item.shortcut}</span>` : ''}</button>`;
      });
    }

    function open(anchor, items) {
      restoreFocus = document.activeElement;
      element.innerHTML = h`${render(items)}`;
      element.hidden = false;
      const box = element.getBoundingClientRect();
      const rect = anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { left: anchor.x, right: anchor.x, top: anchor.y, bottom: anchor.y };
      const rtl = document.documentElement.dir === 'rtl';
      let left = rtl ? rect.left : rect.right - box.width;
      let top = rect.bottom + 4;
      if (top + box.height > innerHeight - 8) top = Math.max(8, rect.top - box.height - 4);
      left = Math.min(Math.max(8, left), innerWidth - box.width - 8);
      element.style.left = `${left}px`;
      element.style.top = `${top}px`;
      element.querySelector('button:not(:disabled)')?.focus();
    }

    function close(focusBack = false) {
      if (element.hidden) return;
      element.hidden = true;
      if (focusBack) restoreFocus?.focus?.();
    }

    element.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-index]');
      if (!button) return;
      const item = actions[Number(button.dataset.index)];
      close();
      item?.run?.();
    });
    element.addEventListener('keydown', (event) => {
      const buttons = [...element.querySelectorAll('button:not(:disabled)')];
      const index = buttons.indexOf(document.activeElement);
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const step = event.key === 'ArrowDown' ? 1 : -1;
        buttons[(index + step + buttons.length) % buttons.length]?.focus();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        close(true);
      } else if (event.key === 'Tab') {
        close();
      }
    });
    document.addEventListener('pointerdown', (event) => {
      if (!element.contains(event.target)) close();
    });
    addEventListener('resize', () => close());
    addEventListener('blur', () => close());
    return { open, close, get isOpen() { return !element.hidden; } };
  })();

  // ------------------------------------------------------------------ toasts
  const Toast = (() => {
    const container = $('#toasts');
    const ICONS = { ok: 'check', info: 'info', warn: 'alert', err: 'alert' };

    function dismiss(element) {
      if (!element.isConnected) return;
      element.classList.add('leaving');
      setTimeout(() => element.remove(), 200);
    }

    function show({ tone = 'info', title, body = '', actions = [], key = '', timeout }) {
      if (key) container.querySelector(`[data-key="${CSS.escape(key)}"]`)?.remove();
      const element = document.createElement('div');
      element.className = `toast tone-${tone}`;
      element.dataset.key = key;
      element.innerHTML = h`${icon(ICONS[tone] || 'info')}
        <div class="text"><strong>${title}</strong>${body ? h`<small>${body}</small>` : ''}</div>
        <div class="actions">${actions.map((a, i) => h`<button class="link-button" data-action="${i}">${a.label}</button>`)}
        <button class="icon-button small" data-close aria-label="${t('Close')}">${icon('close')}</button></div>`;
      element.addEventListener('click', (event) => {
        const action = event.target.closest('[data-action]');
        if (action) actions[Number(action.dataset.action)]?.run();
        if (action || event.target.closest('[data-close]')) dismiss(element);
      });
      container.append(element);
      while (container.children.length > 4) container.firstElementChild.remove();
      let timer = setTimeout(() => dismiss(element), timeout ?? (tone === 'err' ? 9000 : 4500));
      element.addEventListener('pointerenter', () => clearTimeout(timer));
      element.addEventListener('pointerleave', () => {
        timer = setTimeout(() => dismiss(element), 2500);
      });
      return element;
    }
    return { show };
  })();

  // ------------------------------------------------------------------ sheets
  const Sheet = {
    /** Fill a <dialog> and open it modally. Escape and the close button call onClose. */
    open(dialog, content, { onClose } = {}) {
      dialog.innerHTML = h`${content}`;
      I18n.apply(dialog);
      dialog.onclose = () => onClose?.();
      dialog.oncancel = null;
      dialog.querySelectorAll('[data-dismiss]').forEach((button) => {
        button.onclick = (event) => {
          event.preventDefault();
          dialog.close();
        };
      });
      if (!dialog.open) dialog.showModal();
      Menu.close();
      if (!dialog.dataset.backdrop) {
        dialog.dataset.backdrop = '1';
        // Only a press that starts *and* ends outside counts: selecting text that ends
        // outside the box must not close it.
        const outside = (event) => {
          const box = dialog.getBoundingClientRect();
          return event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom);
        };
        let pressed = false;
        dialog.addEventListener('pointerdown', (event) => (pressed = outside(event)));
        dialog.addEventListener('click', (event) => {
          if (pressed && outside(event)) dialog.close();
          pressed = false;
        });
      }
    },
    head(iconName, title, subtitle = '', danger = false) {
      return h`<header class="sheet-head ${danger ? 'danger' : ''}">
        <span class="sheet-icon">${icon(iconName)}</span>
        <div><h2>${title}</h2>${subtitle ? h`<p>${subtitle}</p>` : ''}</div>
        <button class="icon-button" data-dismiss aria-label="${t('Close')}">${icon('close')}</button>
      </header>`;
    },
  };

  // ------------------------------------------------------------------ confirm
  const Confirm = {
    /** Resolves to false (cancelled) or {checked} when confirmed. */
    ask({ title, message, confirm, danger = true, checkbox = null }) {
      const dialog = $('#confirm-dialog');
      return new Promise((resolve) => {
        let answer = false;
        Sheet.open(
          dialog,
          h`<form method="dialog">
            ${Sheet.head(danger ? 'trash' : 'info', title, '', danger)}
            <div class="sheet-body"><p>${message}</p>
              ${checkbox ? h`<label class="toggle-row"><span>${checkbox.label}</span>
                <span class="switch"><input type="checkbox" id="confirm-check" ${checkbox.checked ? 'checked' : ''} /><span></span></span></label>` : ''}
            </div>
            <footer class="sheet-foot">
              <button class="button" data-dismiss>${t('Cancel')}</button>
              <button class="button ${danger ? 'danger solid' : 'primary'}" id="confirm-ok" value="ok">${confirm}</button>
            </footer></form>`,
          { onClose: () => resolve(answer) }
        );
        dialog.querySelector('#confirm-ok').onclick = (event) => {
          event.preventDefault();
          answer = { checked: !!dialog.querySelector('#confirm-check')?.checked };
          dialog.close();
        };
        dialog.querySelector('#confirm-ok').focus();
      });
    },
  };

  window.Overlays = { Menu, Toast, Sheet, Confirm };
})();
