/* Load the browser modules into a sandbox with just enough of `window` and
 * `document` for their pure parts: templates, i18n, messages and the view model. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const WEB = path.join(__dirname, '..', '..', 'bandar', 'web', 'js');
const MODULES = ['fa.js', 'ar.js', 'i18n.js', 'util.js', 'messages.js', 'store.js', 'view-model.js'];

function load() {
  const element = () => ({ setAttribute() {}, querySelectorAll: () => [], dataset: {} });
  const document = {
    documentElement: { lang: 'en', dir: 'ltr' },
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: element,
  };
  const sandbox = { console, Intl, Date, Math, JSON, Set, Map, RegExp, queueMicrotask, setTimeout, document };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  for (const name of MODULES) vm.runInContext(fs.readFileSync(path.join(WEB, name), 'utf8'), sandbox, { filename: name });
  return sandbox;
}

function service(overrides = {}) {
  return {
    id: 's_1',
    name: 'db',
    group: '',
    context: '',
    namespace: '',
    kind: 'service',
    target: 'db',
    localPort: 5432,
    remotePort: 5432,
    address: '127.0.0.1',
    extraArgs: [],
    autoStart: false,
    note: '',
    ...overrides,
  };
}

module.exports = { load, service };
