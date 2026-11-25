const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');

test('templates escape interpolations unless marked raw', () => {
  const { U } = load();
  const name = '<img src=x onerror=alert(1)>';
  assert.equal(String(U.h`<b>${name}</b>`), '<b>&lt;img src=x onerror=alert(1)&gt;</b>');
  assert.equal(String(U.h`<i>${U.raw('<em>ok</em>')}</i>`), '<i><em>ok</em></i>');
  assert.equal(String(U.h`${['<a>', U.h`<b>${'&'}</b>`]}`), '&lt;a&gt;<b>&amp;</b>');
  assert.equal(String(U.h`${null}${false}${undefined}${0}`), '0');
});

test('search highlighting escapes before marking', () => {
  const { U } = load();
  assert.equal(U.highlight('<db>-prod', 'prod'), '&lt;db&gt;-<mark>prod</mark>');
  assert.equal(U.highlight('a.b', '.'), 'a<mark>.</mark>b');
});

test('production-like contexts are always red, others are stable', () => {
  const { U } = load();
  assert.equal(U.contextHue('prod'), 2);
  assert.equal(U.contextHue('eu-production-1'), 2);
  assert.equal(U.contextHue('stage'), U.contextHue('stage'));
});
