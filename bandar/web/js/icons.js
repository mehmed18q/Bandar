/* Technology icons for services and groups: brand logos (Simple Icons, CC0) plus a
 * few generic glyphs. A service without a chosen icon gets one guessed from its
 * name, resource and ports; "redis-cluster" is Redis with a cluster badge. */
(() => {
  'use strict';
  const { raw, escape } = U;
  const BRANDS = window.BandarBrandIcons || {};

  const GENERIC = {
    database: ['Database', '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'],
    cache: ['Cache', '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>'],
    queue: ['Queue', '<rect x="3" y="4" width="18" height="5" rx="1.5"/><rect x="3" y="11" width="18" height="5" rx="1.5"/><path d="M7 20h10"/>'],
    web: ['Web', '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'],
    api: ['API', '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/>'],
    storage: ['Storage', '<path d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3l-2 13c-.2 1.2-2.8 2-6 2s-5.8-.8-6-2Z"/><path d="M4 6c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'],
    metrics: ['Metrics', '<path d="M4 20V10m6 10V4m6 16v-7m4 7H2"/>'],
    lock: ['Auth', '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>'],
    server: ['Server', '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>'],
    terminal: ['Shell', '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3m5 1h5"/>'],
  };

  const CATEGORIES = [
    ['Databases', ['postgresql', 'mysql', 'mariadb', 'mongodb', 'clickhouse', 'cassandra', 'scylladb', 'cockroachdb', 'timescale', 'influxdb', 'neo4j', 'database']],
    ['Caches and search', ['redis', 'redis-cluster', 'cache', 'elasticsearch', 'opensearch', 'meilisearch']],
    ['Messaging', ['kafka', 'rabbitmq', 'nats', 'pulsar', 'temporal', 'queue']],
    ['Platform', ['docker', 'kubernetes', 'helm', 'nginx', 'traefik', 'etcd', 'consul', 'vault', 'minio', 'argo', 'storage', 'server']],
    ['Tools', ['grafana', 'prometheus', 'jaeger', 'sentry', 'keycloak', 'jenkins', 'gitlab', 'airflow', 'web', 'api', 'metrics', 'lock', 'terminal']],
  ];

  // First match wins; checked against "name target" in lowercase.
  const NAME_RULES = [
    [/redis[\w-]*cluster|cluster[\w-]*redis/, 'redis-cluster'],
    [/redis|sentinel|valkey|keydb/, 'redis'],
    [/timescale/, 'timescale'],
    [/postgres|psql|pgbouncer|pgpool|(^|[-_.])pg([-_.]|$)|patroni/, 'postgresql'],
    [/maria/, 'mariadb'],
    [/mysql|percona|vitess/, 'mysql'],
    [/mongo/, 'mongodb'],
    [/clickhouse/, 'clickhouse'],
    [/scylla/, 'scylladb'],
    [/cassandra/, 'cassandra'],
    [/cockroach/, 'cockroachdb'],
    [/influx/, 'influxdb'],
    [/neo4j/, 'neo4j'],
    [/opensearch/, 'opensearch'],
    [/elastic|(^|[-_.])es([-_.]|$)|kibana/, 'elasticsearch'],
    [/meili/, 'meilisearch'],
    [/kafka|redpanda|zookeeper/, 'kafka'],
    [/rabbit|amqp/, 'rabbitmq'],
    [/nats/, 'nats'],
    [/pulsar/, 'pulsar'],
    [/temporal/, 'temporal'],
    [/minio|(^|[-_.])s3([-_.]|$)/, 'minio'],
    [/grafana/, 'grafana'],
    [/prometheus|thanos|alertmanager|victoria/, 'prometheus'],
    [/jaeger|tempo|otel/, 'jaeger'],
    [/sentry/, 'sentry'],
    [/keycloak/, 'keycloak'],
    [/jenkins/, 'jenkins'],
    [/gitlab/, 'gitlab'],
    [/airflow/, 'airflow'],
    [/vault/, 'vault'],
    [/consul/, 'consul'],
    [/etcd/, 'etcd'],
    [/traefik/, 'traefik'],
    [/nginx|ingress/, 'nginx'],
    [/argo/, 'argo'],
    [/docker|registry|harbor/, 'docker'],
    [/memcache/, 'cache'],
  ];
  const PORTS = {
    5432: 'postgresql', 5433: 'postgresql', 6432: 'postgresql',
    6379: 'redis', 6380: 'redis', 26379: 'redis',
    3306: 'mysql', 27017: 'mongodb', 8123: 'clickhouse', 9042: 'cassandra', 7687: 'neo4j', 8086: 'influxdb',
    9200: 'elasticsearch', 9092: 'kafka', 5672: 'rabbitmq', 15672: 'rabbitmq', 4222: 'nats', 6650: 'pulsar',
    7233: 'temporal', 11211: 'cache', 2379: 'etcd', 8500: 'consul', 8200: 'vault', 9090: 'prometheus',
    16686: 'jaeger', 80: 'web', 443: 'web', 8080: 'web', 8000: 'web', 8443: 'web', 3000: 'web',
  }; // prettier-ignore

  const known = (key) => !!(BRANDS[key] || GENERIC[key] || key === 'redis-cluster');

  /** The icon a service shows: its own choice, else a guess, else a server glyph. */
  function forService(service) {
    if (service.icon && known(service.icon)) return service.icon;
    return guess(service);
  }

  function guess(service) {
    const text = `${service.name} ${service.target}`.toLowerCase();
    for (const [pattern, key] of NAME_RULES) if (pattern.test(text)) return key;
    return PORTS[service.remotePort] || PORTS[service.localPort] || 'server';
  }

  function label(key) {
    if (key === 'redis-cluster') return 'Redis Cluster';
    return BRANDS[key]?.title || (GENERIC[key] ? I18n.t(GENERIC[key][0]) : key);
  }

  /** Perceived brightness of a hex color, to keep near-black logos visible on dark themes. */
  function luma(hex) {
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  function svg(key) {
    const brand = BRANDS[key === 'redis-cluster' ? 'redis' : key];
    if (brand) return `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" stroke="none" d="${brand.path}"/></svg>`;
    return `<svg viewBox="0 0 24 24" aria-hidden="true">${(GENERIC[key] || GENERIC.server)[1]}</svg>`;
  }

  /** A colored tile with the icon; ``badge`` marks a cluster. */
  function tile(key, extra = '') {
    const brand = BRANDS[key === 'redis-cluster' ? 'redis' : key];
    const hex = brand?.hex || '';
    const style = hex ? ` style="--brand:#${hex}"` : '';
    const dim = hex && luma(hex) < 0.18 ? ' data-dark' : '';
    // Three nodes: marks a cluster.
    const badge =
      key === 'redis-cluster'
        ? '<span class="icon-badge" aria-hidden="true"><svg viewBox="0 0 12 12"><circle cx="6" cy="3" r="2"/><circle cx="3" cy="8.5" r="2"/><circle cx="9" cy="8.5" r="2"/></svg></span>'
        : '';
    return raw(
      `<span class="tech-icon ${hex ? 'brand' : 'generic'} ${extra}"${style}${dim} title="${escape(label(key))}">${svg(key)}${badge}</span>`
    );
  }

  window.Icons = { CATEGORIES, forService, guess, label, tile, known };
})();

/* The icon picker used by the service and group editors. */
(() => {
  'use strict';
  const { h } = U;
  const t = (key, params) => I18n.t(key, params);

  function choice(key, value) {
    return h`<button type="button" class="icon-choice" data-icon="${key}" data-label="${Icons.label(key).toLowerCase()} ${key}"
      aria-pressed="${key === value}">${Icons.tile(key)}<span>${Icons.label(key)}</span></button>`;
  }

  /** ``automatic`` is the guessed icon for services; groups pass null and get "None". */
  function markup(value, automatic) {
    const first =
      automatic !== null
        ? h`<button type="button" class="icon-choice" data-icon="" data-label="auto" aria-pressed="${!value}"><span class="auto-glyph">A</span><span>${t('Automatic')}</span></button>`
        : h`<button type="button" class="icon-choice" data-icon="" data-label="none" aria-pressed="${!value}"><span class="auto-glyph">—</span><span>${t('None')}</span></button>`;
    return h`<div class="icon-picker">
      <div class="icon-picker-head"><span class="current" data-icon-current></span>
        <input class="input" type="search" data-icon-filter placeholder="${t('Search icons…')}" hidden />
        <button type="button" class="button" data-icon-toggle>${t('Choose…')}</button></div>
      <div class="icon-grid" data-icon-grid hidden><div class="icon-row">${first}</div>
        ${Icons.CATEGORIES.map(([title, keys]) => h`<div class="icon-category">${t(title)}</div><div class="icon-row">${keys.map((key) => choice(key, value))}</div>`)}
      </div></div>`;
  }

  /** Wire a rendered picker. ``state`` = {value, automatic}; ``onChange(key)``. */
  function bind(root, state, onChange) {
    const current = root.querySelector('[data-icon-current]');
    const grid = root.querySelector('[data-icon-grid]');
    const filter = root.querySelector('[data-icon-filter]');
    function paint() {
      const key = state.value || state.automatic;
      const note = state.value ? '' : state.automatic ? t('Automatic: detected from the name and port') : t('No icon');
      current.innerHTML = h`${key ? Icons.tile(key) : ''}<span>${key ? Icons.label(key) : t('None')}${note ? h`<br /><small>${note}</small>` : ''}</span>`;
      root.querySelectorAll('[data-icon]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.icon === (state.value || ''))));
    }
    root.querySelector('[data-icon-toggle]').onclick = () => {
      grid.hidden = !grid.hidden;
      filter.hidden = grid.hidden;
      if (!grid.hidden) filter.focus();
    };
    grid.addEventListener('click', (event) => {
      const button = event.target.closest('[data-icon]');
      if (!button) return;
      state.value = button.dataset.icon;
      paint();
      onChange(state.value);
    });
    filter.addEventListener('input', () => {
      const query = filter.value.trim().toLowerCase();
      grid.querySelectorAll('.icon-row').forEach((row) => {
        let shown = 0;
        row.querySelectorAll('[data-icon]').forEach((b) => {
          b.hidden = !!query && !b.dataset.label.includes(query);
          shown += b.hidden ? 0 : 1;
        });
        row.hidden = !shown;
        if (row.previousElementSibling?.classList.contains('icon-category')) row.previousElementSibling.hidden = !shown;
      });
    });
    paint();
    return { refresh: paint };
  }

  window.IconPicker = { markup, bind };
})();
