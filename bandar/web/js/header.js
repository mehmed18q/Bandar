/* Header popovers, as in Khana: the "Theme & colors" panel next to the theme toggle
 * and a flag-labelled language picker. Both only report choices through actions. */
(() => {
  'use strict';
  const { $ } = U;
  const t = (key, params) => I18n.t(key, params);
  const LANGUAGES = [
    ['en', 'English'],
    ['fa', 'فارسی'],
    ['ar', 'العربية'],
  ];

  function flag(language) {
    const shapes =
      language === 'fa'
        ? '<path fill="#239f40" d="M0 0h30v6H0z"/><path fill="#fff" d="M0 6h30v6H0z"/><path fill="#da0000" d="M0 12h30v6H0z"/><text x="15" y="11.5" text-anchor="middle" fill="#da0000" font-size="8">☫</text>'
        : language === 'ar'
          ? '<path fill="#006c35" d="M0 0h30v18H0z"/><text x="15" y="8.5" text-anchor="middle" fill="#fff" font-size="3.4" font-family="Persian">لا إله إلا الله محمد رسول الله</text><path fill="none" stroke="#fff" stroke-width=".9" d="M7 12.5h16m-1.5 0v2H20"/>'
          : '<path fill="#fff" d="M0 0h30v18H0z"/><path stroke="#b22234" stroke-width="1.4" d="M0 .7h30M0 3.5h30M0 6.3h30M0 9.1h30M0 11.9h30M0 14.7h30M0 17.5h30"/><path fill="#3c3b6e" d="M0 0h13v10H0z"/><path stroke="#fff" stroke-width="1" stroke-dasharray="1 2" d="M2 2h10M2 4h10M2 6h10M2 8h10"/>';
    return `<svg class="language-flag" viewBox="0 0 30 18" aria-hidden="true">${shapes}</svg>`;
  }

  function create({ actions, systemDark }) {
    // ---------------------------------------------------------- theme & colors
    const panel = $('#theme-panel');
    const trigger = $('#theme-settings-button');

    function closePanel(focus = false) {
      if (panel.hidden) return;
      panel.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
      if (focus) trigger.focus();
    }

    trigger.onclick = () => {
      if (!panel.hidden) return closePanel();
      panel.hidden = false;
      trigger.setAttribute('aria-expanded', 'true');
      panel.querySelector('[data-theme-choice][aria-pressed="true"]')?.focus();
    };
    $('#theme-close').onclick = () => closePanel(true);
    panel.addEventListener('click', (event) => {
      const theme = event.target.closest('[data-theme-choice]')?.dataset.themeChoice;
      const palette = event.target.closest('[data-palette-choice]')?.dataset.paletteChoice;
      const density = event.target.closest('[data-density-choice]')?.dataset.densityChoice;
      if (theme) actions.settings({ theme });
      if (palette) actions.settings({ palette });
      if (density) actions.settings({ density });
    });
    panel.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      closePanel(true);
    });
    document.addEventListener('pointerdown', (event) => {
      if (!event.target.closest('.theme-anchor')) closePanel();
    });

    // ---------------------------------------------------------- language
    const button = $('#language-button');
    const menu = document.createElement('div');
    menu.id = 'language-menu';
    menu.className = 'picker-menu';
    menu.popover = 'auto';
    menu.setAttribute('role', 'listbox');
    document.body.append(menu);
    const items = LANGUAGES.map(([code, label]) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.setAttribute('role', 'option');
      item.dataset.value = code;
      item.tabIndex = -1;
      item.lang = code;
      item.innerHTML = flag(code);
      const text = document.createElement('span');
      text.textContent = label;
      item.append(text);
      item.onclick = () => {
        actions.settings({ language: code });
        menu.hidePopover();
        button.focus({ preventScroll: true });
      };
      menu.append(item);
      return item;
    });

    function openLanguages() {
      menu.showPopover();
      const rect = button.getBoundingClientRect();
      const rtl = document.documentElement.dir === 'rtl';
      const left = rtl ? rect.left : rect.right - menu.offsetWidth;
      menu.style.left = `${Math.max(8, Math.min(innerWidth - menu.offsetWidth - 8, left))}px`;
      menu.style.top = `${Math.min(innerHeight - menu.offsetHeight - 8, rect.bottom + 6)}px`;
      (items.find((item) => item.getAttribute('aria-selected') === 'true') || items[0]).focus();
    }

    button.onclick = () => (menu.matches(':popover-open') ? menu.hidePopover() : openLanguages());
    menu.addEventListener('toggle', (event) => button.setAttribute('aria-expanded', String(event.newState === 'open')));
    menu.addEventListener('keydown', (event) => {
      const index = items.indexOf(document.activeElement);
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus();
      }
    });

    // ---------------------------------------------------------- state → markup
    function render(settings, dark) {
      document.querySelectorAll('[data-theme-choice]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.themeChoice === settings.theme)));
      document.querySelectorAll('[data-palette-choice]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.paletteChoice === settings.palette)));
      document.querySelectorAll('[data-density-choice]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.densityChoice === settings.density)));
      $('#theme-system-status').textContent = t('System appearance: {mode}', { mode: systemDark() ? t('Dark') : t('Light') });
      const theme = $('#theme-button');
      theme.innerHTML = `<svg aria-hidden="true"><use href="#i-${dark ? 'sun' : 'moon'}"/></svg>`;
      theme.title = dark ? t('Switch to light theme') : t('Switch to dark theme');
      items.forEach((item) => item.setAttribute('aria-selected', String(item.dataset.value === settings.language)));
      menu.setAttribute('aria-label', t('Application language'));
    }

    return {
      render,
      close() {
        closePanel();
        if (menu.matches(':popover-open')) menu.hidePopover();
      },
    };
  }

  window.Header = { create, LANGUAGES };
})();
