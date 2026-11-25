/* Interface localization. English strings are the keys; catalogs translate them.
 * Static markup opts in with data-t (text), data-t-title, data-t-placeholder and
 * data-t-aria. User data (names, contexts, commands) is never translated. */
(() => {
  'use strict';
  const catalogs = { fa: window.BandarPersian || {}, ar: window.BandarArabic || {} };
  const numberFormats = { fa: new Intl.NumberFormat('fa-IR'), ar: new Intl.NumberFormat('ar-EG') };
  const RTL = new Set(['fa', 'ar']);
  let language = 'en';

  function t(key, params) {
    let text = catalogs[language]?.[key] ?? key;
    if (params) text = text.replace(/\{(\w+)\}/g, (_, name) => (name in params ? params[name] : ''));
    return text;
  }

  /** Counts and durations follow the language; ports and identifiers stay Latin. */
  const num = (value) => (numberFormats[language] ? numberFormats[language].format(value) : String(value));

  function duration(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const d = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const pad = (n) => (language === 'en' ? String(n).padStart(2, '0') : num(n));
    const unit = (value, key) => `${typeof value === 'string' ? value : num(value)}${t(key)}`;
    if (d) return `${unit(d, 'd')} ${unit(pad(hours), 'h')}`;
    if (hours) return `${unit(hours, 'h')} ${unit(pad(m), 'm')}`;
    if (m) return `${unit(m, 'm')} ${unit(pad(s), 's')}`;
    return unit(s, 's');
  }

  function ago(ms) {
    const seconds = Math.max(0, Math.round((Date.now() - ms) / 1000));
    if (seconds < 5) return t('just now');
    if (seconds < 60) return t('{n}s ago', { n: num(seconds) });
    if (seconds < 3600) return t('{n}m ago', { n: num(Math.floor(seconds / 60)) });
    if (seconds < 86400) return t('{n}h ago', { n: num(Math.floor(seconds / 3600)) });
    return t('{n}d ago', { n: num(Math.floor(seconds / 86400)) });
  }

  const clock = (ms) => new Date(ms).toLocaleTimeString('en-GB', { hour12: false });

  function apply(root = document) {
    root.querySelectorAll('[data-t]').forEach((element) => {
      element.dataset.key ??= element.textContent.trim();
      element.textContent = t(element.dataset.key);
    });
    for (const [data, attribute] of [
      ['tTitle', 'title'],
      ['tPlaceholder', 'placeholder'],
      ['tAria', 'aria-label'],
    ]) {
      const selector = `[data-${data.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase())}]`;
      root.querySelectorAll(selector).forEach((element) => {
        element.setAttribute(attribute, t(element.dataset[data]));
      });
    }
  }

  function setLanguage(next) {
    language = catalogs[next] ? next : 'en';
    document.documentElement.lang = language;
    document.documentElement.dir = RTL.has(language) ? 'rtl' : 'ltr';
    apply();
  }

  window.I18n = {
    t,
    num,
    duration,
    ago,
    clock,
    apply,
    setLanguage,
    get language() {
      return language;
    },
  };
})();
