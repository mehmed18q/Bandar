/* Icons for services and groups.
 *
 * An icon value is one of:
 *   "postgresql"        a brand logo (Simple Icons), drawn on its brand color
 *   "redis-cluster"     Redis with a cluster badge
 *   "i:message-circle"  a Lucide glyph, drawn on the group's color
 *   "env:production"    an environment glyph on the environment's color
 *   "emoji:💬"          any emoji (or up to two characters)
 * A service without a chosen icon gets one guessed from its name and ports. */
(() => {
  'use strict';
  const { raw, escape } = U;
  const t = (key, params) => I18n.t(key, params);
  const DATA = window.BandarIconData || { brands: {}, glyphs: {}, brandCategories: [], glyphNames: [], environments: {} };
  const { brands: BRANDS, glyphs: GLYPHS, environments: ENVS } = DATA;

  // Values saved before glyphs came from Lucide.
  const ALIASES = {
    database: 'i:database',
    cache: 'i:zap',
    queue: 'i:layers',
    web: 'i:globe',
    api: 'i:webhook',
    storage: 'i:hard-drive',
    metrics: 'i:chart-bar',
    lock: 'i:lock',
    server: 'i:server',
    terminal: 'i:terminal',
  };

  /* Curated emoji with search words. Any other emoji can be pasted in the picker. */
  const EMOJI = [
    ['Money and business', '💬 chat message|🪙 coin gold|💰 money bag gold|💎 gem diamond|🥇 gold medal first|🏆 trophy gold|💵 dollar money cash|💶 euro|💸 payment money|💳 card payment|🏦 bank|🧾 receipt invoice|📈 growth chart|📉 decline chart|📊 stats chart|🛒 cart shop|🛍️ shopping bag|🏪 store shop|📦 package order|🚚 delivery truck|🏷️ tag price|🎁 gift|🎫 ticket|💼 business briefcase|🧮 accounting'],
    ['Communication', '🗨️ chat bubble|💭 thought|📨 message inbox|📧 email mail|📮 mailbox|📞 phone call|📱 mobile app|🔔 notification bell|📣 announcement|📡 signal|🛰️ satellite|🌐 web globe|👤 user|👥 users team|🧑‍💻 developer|🤝 partner'],
    ['Tech', '💻 laptop|🖥️ desktop|🗄️ database archive|💾 storage disk|🔐 secure lock|🔑 key auth|🛡️ shield security|⚙️ settings|🛠️ tools|🔧 wrench|🧰 toolbox|🧪 test lab|🚀 deploy rocket|🐞 bug|🧩 plugin|🤖 bot ai|🧠 brain ai|🔍 search|📝 notes|📋 clipboard|📁 folder|🗂️ files|📅 calendar|⏱️ timer|🔌 plug|🔋 battery|🐳 docker whale|🐘 postgres elephant|🐍 python|🦀 rust|🐹 go gopher|🐧 linux|☕ java coffee'],
    ['Places and things', '🏠 home local|🏭 factory production|🏢 office|🏥 health|🎓 education|📚 books|📰 news|🎮 game|🎵 music|🎬 video film|📷 photo|🎨 design|🍔 food|🍕 pizza|🚗 car|🛵 scooter delivery|✈️ travel|🚢 ship|⚓ anchor port|🗺️ map|📍 location'],
    ['Symbols and colors', '⭐ star|❤️ heart|🔥 fire hot|⚡ fast|✨ new|🎯 target|🚧 work in progress|✅ done|⚠️ warning|❌ error|🔴 red|🟠 orange|🟡 yellow gold|🟢 green|🔵 blue|🟣 purple|⚫ black|⚪ white|🟥 red square|🟧 orange square|🟨 yellow square|🟩 green square|🟦 blue square|🟪 purple square'],
  ].map(([title, list]) => [title, list.split('|').map((entry) => {
    const [emoji, ...words] = entry.split(' ');
    return [emoji, words.join(' ')];
  })]); // prettier-ignore

  // First match wins; checked against "name target" in lowercase.
  const NAME_RULES = [
    [/redis[\w-]*cluster|cluster[\w-]*redis/, 'redis-cluster'],
    [/redis|sentinel|valkey|keydb|dragonfly/, 'redis'],
    [/timescale/, 'timescale'],
    [/postgres|psql|pgbouncer|pgpool|(^|[-_.])pg([-_.]|$)|patroni/, 'postgresql'],
    [/maria/, 'mariadb'],
    [/mysql|percona|vitess/, 'mysql'],
    [/mongo/, 'mongodb'],
    [/clickhouse/, 'clickhouse'],
    [/scylla/, 'scylladb'],
    [/cassandra/, 'cassandra'],
    [/cockroach/, 'cockroachdb'],
    [/couchbase/, 'couchbase'],
    [/arango/, 'arangodb'],
    [/influx/, 'influxdb'],
    [/neo4j/, 'neo4j'],
    [/qdrant/, 'qdrant'],
    [/druid/, 'druid'],
    [/opensearch/, 'opensearch'],
    [/kibana/, 'kibana'],
    [/elastic|(^|[-_.])es([-_.]|$)/, 'elasticsearch'],
    [/meili/, 'meilisearch'],
    [/solr/, 'solr'],
    [/kafka|redpanda|zookeeper/, 'kafka'],
    [/rabbit|amqp/, 'rabbitmq'],
    [/mosquitto|mqtt|emqx/, 'mqtt'],
    [/nats/, 'nats'],
    [/pulsar/, 'pulsar'],
    [/temporal/, 'temporal'],
    [/celery|flower/, 'celery'],
    [/minio|(^|[-_.])s3([-_.]|$)/, 'minio'],
    [/ceph|rook/, 'ceph'],
    [/grafana|loki|tempo/, 'grafana'],
    [/prometheus|alertmanager/, 'prometheus'],
    [/thanos/, 'thanos'],
    [/victoria/, 'victoriametrics'],
    [/jaeger/, 'jaeger'],
    [/otel|opentelemetry/, 'opentelemetry'],
    [/sentry/, 'sentry'],
    [/logstash/, 'logstash'],
    [/fluent-?bit/, 'fluentbit'],
    [/fluent/, 'fluentd'],
    [/uptime-?kuma/, 'uptimekuma'],
    [/keycloak/, 'keycloak'],
    [/jenkins/, 'jenkins'],
    [/gitlab/, 'gitlab'],
    [/gitea/, 'gitea'],
    [/airflow/, 'airflow'],
    [/superset/, 'superset'],
    [/metabase/, 'metabase'],
    [/jupyter/, 'jupyter'],
    [/(^|[-_.])n8n/, 'n8n'],
    [/airbyte/, 'airbyte'],
    [/spark/, 'spark'],
    [/flink/, 'flink'],
    [/ollama/, 'ollama'],
    [/vault/, 'vault'],
    [/consul/, 'consul'],
    [/etcd/, 'etcd'],
    [/traefik/, 'traefik'],
    [/envoy/, 'envoy'],
    [/istio/, 'istio'],
    [/haproxy/, 'haproxy'],
    [/kong/, 'kong'],
    [/nginx|ingress/, 'nginx'],
    [/argo/, 'argo'],
    [/harbor/, 'harbor'],
    [/portainer/, 'portainer'],
    [/rancher/, 'rancher'],
    [/nexus/, 'nexus'],
    [/docker|registry/, 'docker'],
    [/memcache/, 'i:zap'],
    [/chat|messag/, 'i:message-circle'],
    [/(^|[-_.])(mail|smtp)/, 'i:mail'],
    [/notif/, 'i:bell'],
    [/pay|wallet|billing/, 'i:wallet'],
    [/gold|coin/, 'i:coins'],
    [/shop|store|cart|order/, 'i:shopping-cart'],
    [/(^|[-_.])(auth|sso|iam)([-_.]|$)/, 'i:shield-check'],
    [/search/, 'i:search'],
    [/(^|[-_.])api([-_.]|$)|gateway/, 'i:webhook'],
  ];
  const PORTS = {
    5432: 'postgresql', 5433: 'postgresql', 6432: 'postgresql',
    6379: 'redis', 6380: 'redis', 26379: 'redis',
    3306: 'mysql', 27017: 'mongodb', 8123: 'clickhouse', 9042: 'cassandra', 7687: 'neo4j', 8086: 'influxdb',
    9200: 'elasticsearch', 9092: 'kafka', 5672: 'rabbitmq', 15672: 'rabbitmq', 1883: 'mqtt', 4222: 'nats',
    6650: 'pulsar', 7233: 'temporal', 11211: 'i:zap', 2379: 'etcd', 8500: 'consul', 8200: 'vault',
    9090: 'prometheus', 16686: 'jaeger', 6333: 'qdrant', 7700: 'meilisearch', 8983: 'solr',
    80: 'i:globe', 443: 'i:globe', 8080: 'i:globe', 8000: 'i:globe', 8443: 'i:globe', 3000: 'i:globe',
  }; // prettier-ignore

  const normalize = (key) => ALIASES[key] || key || '';

  /** Search words for curated emoji, and our own extra words for some glyphs. */
  const EMOJI_WORDS = new Map(EMOJI.flatMap(([, list]) => list));
  const GLYPH_WORDS = {
    coins: 'gold coin money', gem: 'gold diamond jewel', 'message-circle': 'chat', 'messages-square': 'chat',
    'message-square': 'chat comment', landmark: 'bank finance', wallet: 'payment money', trophy: 'gold winner',
    medal: 'gold award', crown: 'gold king vip', 'shopping-cart': 'shop store order', store: 'shop',
    factory: 'production', 'flask-conical': 'staging lab', 'test-tube-diagonal': 'testing', laptop: 'local',
  }; // prettier-ignore

  function known(key) {
    key = normalize(key);
    if (key.startsWith('emoji:')) return key.length > 6;
    if (key.startsWith('env:')) return !!ENVS[key.slice(4)];
    if (key.startsWith('i:')) return !!GLYPHS[key.slice(2)];
    return key === 'redis-cluster' || !!BRANDS[key];
  }

  function guess(service) {
    const text = `${service.name || ''} ${service.target || ''}`.toLowerCase();
    for (const [pattern, key] of NAME_RULES) if (pattern.test(text)) return key;
    return PORTS[service.remotePort] || PORTS[service.localPort] || 'i:server';
  }

  /** The icon a service shows: its own choice, else a guess. */
  const forService = (service) => (known(service.icon) ? normalize(service.icon) : guess(service));

  const humanize = (name) => name.replace(/-/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

  function label(key) {
    key = normalize(key);
    if (key.startsWith('emoji:')) return EMOJI_WORDS.get(key.slice(6))?.split(' ')[0] || key.slice(6);
    if (key.startsWith('env:')) return t(ENVS[key.slice(4)]?.title || key);
    if (key.startsWith('i:')) return humanize(key.slice(2));
    if (key === 'redis-cluster') return 'Redis Cluster';
    return BRANDS[key]?.title || key;
  }

  /** Perceived brightness of a hex color: light brands get a dark glyph. */
  function luma(hex) {
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  const glyphSvg = (name) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${GLYPHS[name]?.body || GLYPHS.server?.body || ''}</svg>`;
  const brandSvg = (key) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" stroke="none" d="${BRANDS[key].path}"/></svg>`;
  const CLUSTER_BADGE =
    '<span class="icon-badge" aria-hidden="true"><svg viewBox="0 0 12 12"><circle cx="6" cy="3" r="2"/><circle cx="3" cy="8.5" r="2"/><circle cx="9" cy="8.5" r="2"/></svg></span>';

  /** A rounded tile showing ``key``. ``tint`` (a group color name) colors icons without a brand. */
  function tile(key, options = {}) {
    const { size = '', tint = '' } = typeof options === 'string' ? { size: options } : options;
    key = normalize(key);
    let kind = 'glyph';
    let inner = '';
    let bg = tint ? `var(--c-${tint})` : 'var(--solid)';
    let fg = '#fff';
    const brandKey = key === 'redis-cluster' ? 'redis' : key;
    if (key.startsWith('emoji:')) {
      kind = 'emoji';
      inner = escape(key.slice(6));
    } else if (key.startsWith('env:') && ENVS[key.slice(4)]) {
      kind = 'env';
      bg = `#${ENVS[key.slice(4)].hex}`;
      inner = glyphSvg(ENVS[key.slice(4)].glyph);
    } else if (BRANDS[brandKey]) {
      kind = 'brand';
      bg = `#${BRANDS[brandKey].hex}`;
      fg = luma(BRANDS[brandKey].hex) > 0.62 ? '#1b1f24' : '#fff';
      inner = brandSvg(brandKey) + (key === 'redis-cluster' ? CLUSTER_BADGE : '');
    } else {
      inner = glyphSvg(key.startsWith('i:') ? key.slice(2) : 'server');
    }
    return raw(
      `<span class="tech-icon is-${kind} ${size}" style="--bg:${bg};--fg:${fg}" title="${escape(label(key))}">${inner}</span>`
    );
  }

  window.Icons = { BRANDS, GLYPHS, ENVS, EMOJI, DATA, GLYPH_WORDS, normalize, known, guess, forService, label, tile };
})();

/* The icon picker used by the service and group editors. */
(() => {
  'use strict';
  const { h } = U;
  const t = (key, params) => I18n.t(key, params);
  const SUGGESTED_LOGOS = ['postgresql', 'mysql', 'mongodb', 'redis', 'redis-cluster', 'kafka', 'rabbitmq', 'elasticsearch', 'clickhouse', 'docker', 'kubernetes', 'nginx', 'grafana', 'prometheus', 'minio', 'vault'];
  const SUGGESTED_OTHER = ['i:message-circle', 'i:coins', 'i:gem', 'i:shopping-cart', 'i:landmark', 'i:users', 'i:globe', 'i:server', 'emoji:💬', 'emoji:🪙', 'emoji:💰', 'emoji:🥇']; // prettier-ignore
  const TABS = [
    ['suggested', 'Suggested'],
    ['logos', 'Logos'],
    ['icons', 'Icons'],
    ['emoji', 'Emoji'],
  ];
  const RESULT_LIMIT = 150;

  function create({ root, state, tint, onChange }) {
    let tab = 'suggested';
    const current = root.querySelector('[data-icon-current]');
    const panel = root.querySelector('[data-icon-panel]');
    const grid = root.querySelector('[data-icon-grid]');
    const filter = root.querySelector('[data-icon-filter]');

    const choice = (key, text = Icons.label(key)) =>
      h`<button type="button" class="icon-choice" data-icon="${key}" aria-pressed="${key === state.value}" title="${text}">
        ${Icons.tile(key, { tint: tint() })}<span>${text}</span></button>`;
    const section = (title, keys) =>
      keys.length ? h`<div class="icon-category">${t(title)}</div><div class="icon-row">${keys.map((key) => choice(key))}</div>` : '';
    const none = () =>
      state.automatic !== null
        ? h`<button type="button" class="icon-choice" data-icon="" aria-pressed="${!state.value}"><span class="auto-glyph">A</span><span>${t('Automatic')}</span></button>`
        : h`<button type="button" class="icon-choice" data-icon="" aria-pressed="${!state.value}"><span class="auto-glyph">—</span><span>${t('None')}</span></button>`;
    const environments = () => Object.keys(Icons.ENVS).map((key) => `env:${key}`);

    function search(query) {
      const words = query.toLowerCase().split(/\s+/).filter(Boolean);
      const hit = (text) => words.every((word) => text.toLowerCase().includes(word));
      const results = [];
      for (const [key, env] of Object.entries(Icons.ENVS)) if (hit(`${key} ${env.title} ${t(env.title)} environment`)) results.push(`env:${key}`);
      for (const [key, brand] of Object.entries(Icons.BRANDS)) if (hit(`${key} ${brand.title}`)) results.push(key);
      if (hit('redis cluster')) results.push('redis-cluster');
      for (const name of Icons.DATA.glyphNames) {
        if (hit(`${name} ${Icons.GLYPH_WORDS[name] || ''} ${Icons.GLYPHS[name]?.tags || ''}`)) results.push(`i:${name}`);
      }
      for (const [, list] of Icons.EMOJI) for (const [emoji, keywords] of list) if (hit(keywords)) results.push(`emoji:${emoji}`);
      return [...new Set(results)].slice(0, RESULT_LIMIT);
    }

    function renderGrid() {
      const query = filter.value.trim();
      root.querySelectorAll('[data-icon-tab]').forEach((b) => b.setAttribute('aria-pressed', String(!query && b.dataset.iconTab === tab)));
      if (query) {
        const results = search(query);
        grid.innerHTML = results.length
          ? h`<div class="icon-row">${results.map((key) => choice(key))}</div>`
          : h`<div class="icon-empty">${t('No icon matches “{query}”. In the Emoji tab you can paste any emoji.', { query })}</div>`;
      } else if (tab === 'suggested') {
        grid.innerHTML = h`<div class="icon-row">${none()}</div>${section('Environments', environments())}
          ${section('Popular logos', SUGGESTED_LOGOS)}${section('Popular icons', SUGGESTED_OTHER)}`;
      } else if (tab === 'logos') {
        grid.innerHTML = h`${Icons.DATA.brandCategories.map(([title, keys]) =>
          section(title, title === 'Caches and search' ? ['redis', 'redis-cluster', ...keys.filter((k) => k !== 'redis')] : keys)
        )}`;
      } else if (tab === 'icons') {
        grid.innerHTML = h`${section('Environments', environments())}${section('Icons', Icons.DATA.glyphNames.map((n) => `i:${n}`))}`;
      } else {
        grid.innerHTML = h`<div class="icon-custom">
            <input class="input" data-icon-custom maxlength="16" placeholder="${t('Paste any emoji, e.g. 🪙')}" />
            <button type="button" class="button" data-icon-use>${t('Use')}</button></div>
          ${Icons.EMOJI.map(([title, list]) => h`<div class="icon-category">${t(title)}</div>
            <div class="icon-row emoji-row">${list.map(([emoji]) => choice(`emoji:${emoji}`))}</div>`)}`;
      }
    }

    function paint() {
      const key = state.value || state.automatic;
      const note = state.value ? '' : state.automatic ? t('Automatic: detected from the name and port') : t('No icon');
      current.innerHTML = h`${key ? Icons.tile(key, { tint: tint() }) : h`<span class="auto-glyph">—</span>`}
        <span>${key ? Icons.label(key) : t('None')}${note ? h`<br /><small>${note}</small>` : ''}</span>`;
      grid.querySelectorAll('[data-icon]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.icon === (state.value || ''))));
    }

    function choose(value) {
      state.value = value;
      paint();
      onChange?.(value);
    }

    /** One emoji, or up to two characters, from free text. */
    function customValue(text) {
      const graphemes = [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(text.trim())].map((s) => s.segment);
      const value = graphemes.filter((g) => g.trim()).slice(0, 2).join('');
      return value ? `emoji:${value}` : '';
    }

    root.querySelector('[data-icon-toggle]').onclick = () => {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) {
        renderGrid();
        paint();
        filter.focus();
      }
    };
    root.addEventListener('click', (event) => {
      const tabButton = event.target.closest('[data-icon-tab]');
      if (tabButton) {
        tab = tabButton.dataset.iconTab;
        filter.value = '';
        renderGrid();
        paint();
      } else if (event.target.closest('[data-icon-use]')) {
        const value = customValue(root.querySelector('[data-icon-custom]').value);
        if (value) choose(value);
      } else {
        const button = event.target.closest('[data-icon]');
        if (button && grid.contains(button)) choose(button.dataset.icon);
      }
    });
    root.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && event.target.matches('[data-icon-custom]')) {
        event.preventDefault();
        const value = customValue(event.target.value);
        if (value) choose(value);
      }
    });
    filter.addEventListener('input', () => {
      renderGrid();
      paint();
    });
    paint();
    return {
      /** Repaint after the guess or the tint changed. */
      refresh() {
        if (!panel.hidden) renderGrid();
        paint();
      },
    };
  }

  function markup() {
    return h`<div class="icon-picker">
      <div class="icon-picker-head"><span class="current" data-icon-current></span>
        <button type="button" class="button" data-icon-toggle>${t('Choose…')}</button></div>
      <div class="icon-panel" data-icon-panel hidden>
        <div class="icon-panel-bar"><div class="segmented">${TABS.map(([key, text]) => h`<button type="button" data-icon-tab="${key}">${t(text)}</button>`)}</div>
          <input class="input" type="search" data-icon-filter placeholder="${t('Search logos, icons and emoji…')}" /></div>
        <div class="icon-grid" data-icon-grid></div>
      </div></div>`;
  }

  window.IconPicker = {
    markup,
    /** Wire a rendered picker. ``state`` = {value, automatic}; ``tint()`` names the group color. */
    bind: (root, state, onChange, tint = () => '') => create({ root, state, tint, onChange }),
  };
})();
