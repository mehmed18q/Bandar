const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');

test('every catalog translates the same strings with the same placeholders', () => {
  const { BandarPersian: fa, BandarArabic: ar } = load();
  assert.deepEqual(Object.keys(ar).sort(), Object.keys(fa).sort());
  const placeholders = (text) => (text.match(/\{\w+\}/g) || []).sort().join(',');
  for (const [key, value] of Object.entries(fa)) {
    assert.equal(placeholders(value), placeholders(key), `fa: ${key}`);
    assert.equal(placeholders(ar[key]), placeholders(key), `ar: ${key}`);
  }
});

test('translation, interpolation and right-to-left direction', () => {
  const sandbox = load();
  const { I18n, document } = sandbox;
  assert.equal(I18n.t('{n} services', { n: 3 }), '3 services');
  I18n.setLanguage('fa');
  assert.equal(document.documentElement.dir, 'rtl');
  assert.equal(I18n.t('{n} services', { n: I18n.num(3) }), '۳ سرویس');
  I18n.setLanguage('ar');
  assert.equal(document.documentElement.dir, 'rtl');
  assert.equal(I18n.t('Start'), 'تشغيل');
  I18n.setLanguage('xx');
  assert.equal(I18n.language, 'en');
  assert.equal(document.documentElement.dir, 'ltr');
  assert.equal(I18n.t('Unknown string stays'), 'Unknown string stays');
});

test('durations are compact and localized', () => {
  const { I18n } = load();
  assert.equal(I18n.duration(5_000), '5s');
  assert.equal(I18n.duration(640_000), '10m 40s');
  assert.equal(I18n.duration(3_725_000), '1h 02m');
  assert.equal(I18n.duration(90_000_000), '1d 01h');
  I18n.setLanguage('fa');
  assert.equal(I18n.duration(640_000), '۱۰د ۴۰ث');
});
