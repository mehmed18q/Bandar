const test = require('node:test');
const assert = require('node:assert/strict');
const { load, service } = require('./harness.cjs');

function setup() {
  const sandbox = load();
  const { Store } = sandbox;
  Store.replace({
    config: {
      settings: { sortKey: '', sortDir: 'asc' },
      groups: [
        { id: 'g_prod', name: 'orders', color: 'blue', environment: 'production', collapsed: false },
        { id: 'g_stage', name: 'orders-stage', color: 'amber', environment: 'staging', collapsed: false },
        { id: 'g_empty', name: 'empty', color: 'slate', environment: '', collapsed: false },
      ],
      services: [
        service({ id: 's_a', name: 'b-db', group: 'g_prod', localPort: 5432 }),
        service({ id: 's_b', name: 'a-cache', group: 'g_prod', localPort: 6379, context: 'prod' }),
        service({ id: 's_c', name: 'stage-db', group: 'g_stage', localPort: 5433, namespace: 'orders' }),
        service({ id: 's_d', name: 'loose', localPort: 7000 }),
      ],
      session: { running: [] },
    },
    runtime: {
      s_a: { state: 'healthy', healthySince: 1, restarts: 0 },
      s_b: { state: 'retrying', restarts: 2 },
      s_c: { state: 'error', restarts: 0 },
    },
    meta: { kube: { current: 'main', contexts: [{ name: 'main', namespace: 'orders-api' }] } },
  });
  return sandbox;
}

// Values from the sandbox realm have other prototypes; compare plain copies.
const names = (sections) => JSON.parse(JSON.stringify(sections.map((s) => [s.key, s.items.map((i) => i.service.name)])));

test('sections keep configured order and show empty groups only when unfiltered', () => {
  const { ViewModel, Store } = setup();
  assert.deepEqual(names(ViewModel.sections(Store.state)), [
    ['g_prod', ['b-db', 'a-cache']],
    ['g_stage', ['stage-db']],
    ['g_empty', []],
    ['__ungrouped__', ['loose']],
  ]);
  Store.state.ui.view = 'problems';
  assert.deepEqual(names(ViewModel.sections(Store.state)), [
    ['g_prod', ['a-cache']],
    ['g_stage', ['stage-db']],
  ]);
});

test('counts and inherited context/namespace resolution', () => {
  const { ViewModel, Store } = setup();
  const counts = ViewModel.counts(Store.state);
  assert.equal(counts.all, 4);
  assert.equal(counts.running, 2);
  assert.equal(counts.problems, 2);
  assert.equal(counts.errors, 1);
  assert.equal(counts.stopped, 1);
  const loose = ViewModel.describe(Store.state, Store.service('s_d'));
  assert.deepEqual({ ...loose.context }, { name: 'main', inherited: true });
  assert.deepEqual({ ...loose.namespace }, { name: 'orders-api', inherited: true });
  const pinned = ViewModel.describe(Store.state, Store.service('s_c'));
  assert.deepEqual({ ...pinned.namespace }, { name: 'orders', inherited: false });
});

test('search, environment filter and column sorting', () => {
  const { ViewModel, Store } = setup();
  Store.state.ui.search = 'cache prod';
  assert.deepEqual(names(ViewModel.sections(Store.state)), [['g_prod', ['a-cache']]]);
  Store.state.ui.search = '';
  Store.state.ui.env = 'staging';
  assert.deepEqual(names(ViewModel.sections(Store.state)), [['g_stage', ['stage-db']]]);
  Store.state.ui.env = null;
  Store.state.config.settings.sortKey = 'name';
  assert.deepEqual(names(ViewModel.sections(Store.state))[0], ['g_prod', ['a-cache', 'b-db']]);
  Store.state.config.settings.sortKey = 'restarts';
  Store.state.config.settings.sortDir = 'desc';
  assert.deepEqual(names(ViewModel.sections(Store.state))[0], ['g_prod', ['a-cache', 'b-db']]);
});

test('problems carry wording and the actions that fit them', () => {
  const { Messages } = setup();
  const busy = Messages.problem(
    { code: 'port_in_use', owner: { pid: 42, name: 'kubectl', ours: true } },
    service({ localPort: 5432 })
  );
  assert.equal(busy.title, 'Local port 5432 is already in use');
  assert.match(busy.hint, /leftover kubectl port-forward \(PID 42\)/);
  assert.equal(busy.actions[0], 'free');
  const unknown = Messages.problem({ code: 'something-new', detail: 'x' }, service());
  assert.equal(unknown.title, 'kubectl reported an error');
  assert.equal(Messages.field({ code: 'port_taken', service: 'db' }), 'Port is assigned to “db”. Each service needs its own local port.');
});
