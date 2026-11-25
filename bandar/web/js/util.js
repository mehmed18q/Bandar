/* Small helpers shared by every module: safe HTML templates, timing and formatting. */
(() => {
  'use strict';

  class Raw {
    constructor(text) {
      this.text = text;
    }
    toString() {
      return this.text;
    }
  }
  const ENTITIES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ENTITIES[c]);
  const raw = (text) => new Raw(String(text));

  function piece(value) {
    if (value instanceof Raw) return value.text;
    if (Array.isArray(value)) return value.map(piece).join('');
    if (value === false || value === null || value === undefined) return '';
    return escape(value);
  }

  /** Tagged template: interpolations are escaped unless wrapped in raw() or h``. */
  function h(strings, ...values) {
    let out = strings[0];
    values.forEach((value, index) => {
      out += piece(value) + strings[index + 1];
    });
    return new Raw(out);
  }

  const icon = (name, cls = '') => raw(`<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`);
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  /** Delegated event listener: fn(event, matchedElement). */
  function on(root, type, selector, fn, options) {
    root.addEventListener(
      type,
      (event) => {
        const target = event.target.closest?.(selector);
        if (target && root.contains(target)) fn(event, target);
      },
      options
    );
  }

  function debounce(fn, wait) {
    let timer = 0;
    const wrapped = (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
    wrapped.cancel = () => clearTimeout(timer);
    return wrapped;
  }

  /** Deterministic hue for a context name; production-like names are always red. */
  function contextHue(name) {
    if (/prod/i.test(name)) return 2;
    let hash = 0;
    for (const char of name) hash = (hash * 31 + char.codePointAt(0)) | 0;
    const hues = [205, 160, 265, 32, 300, 185, 120, 230, 45];
    return hues[Math.abs(hash) % hues.length];
  }

  function highlight(text, query) {
    const value = String(text ?? '');
    const terms = (query || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return escape(value);
    const pattern = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
    return value
      .split(pattern)
      .map((part, i) => (i % 2 ? `<mark>${escape(part)}</mark>` : escape(part)))
      .join('');
  }

  const sameSet = (a, b) => a.size === b.size && [...a].every((item) => b.has(item));

  window.U = { h, raw, escape, icon, $, $$, on, debounce, contextHue, highlight, sameSet };
})();
