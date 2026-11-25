"""Generate bandar/web/js/icon-data.js from Simple Icons (CC0-1.0) and Lucide (ISC).

    npm pack simple-icons lucide-static
    mkdir -p /tmp/si /tmp/lucide
    tar -xzf simple-icons-*.tgz -C /tmp/si && tar -xzf lucide-static-*.tgz -C /tmp/lucide
    python scripts/make_icons.py /tmp/si/package /tmp/lucide/package

Only the listed icons are embedded, so the interface works offline. Brand names and
logos remain trademarks of their owners and only identify the technology.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Bandar key → Simple Icons slug, by picker category.
BRANDS = {
    "Databases": {
        "postgresql": "postgresql", "mysql": "mysql", "mariadb": "mariadb", "mongodb": "mongodb",
        "clickhouse": "clickhouse", "cassandra": "apachecassandra", "scylladb": "scylladb",
        "cockroachdb": "cockroachlabs", "timescale": "timescale", "influxdb": "influxdb", "neo4j": "neo4j",
        "couchbase": "couchbase", "arangodb": "arangodb", "sqlite": "sqlite", "snowflake": "snowflake",
        "supabase": "supabase", "firebase": "firebase", "druid": "apachedruid", "duckdb": "duckdb",
        "singlestore": "singlestore", "surrealdb": "surrealdb", "hbase": "apachehbase", "qdrant": "qdrant",
    },
    "Caches and search": {
        "redis": "redis", "elasticsearch": "elasticsearch", "opensearch": "opensearch",
        "meilisearch": "meilisearch", "solr": "apachesolr", "algolia": "algolia",
    },
    "Messaging": {
        "kafka": "apachekafka", "rabbitmq": "rabbitmq", "nats": "natsdotio", "pulsar": "apachepulsar",
        "temporal": "temporal", "celery": "celery", "mqtt": "mqtt", "mosquitto": "eclipsemosquitto",
        "rocketmq": "apacherocketmq",
    },
    "Infrastructure": {
        "docker": "docker", "kubernetes": "kubernetes", "helm": "helm", "podman": "podman", "k3s": "k3s",
        "rancher": "rancher", "openshift": "redhatopenshift", "nginx": "nginx", "traefik": "traefikproxy",
        "envoy": "envoyproxy", "istio": "istio", "haproxy": "haproxy", "caddy": "caddy", "apache": "apache",
        "kong": "kong", "etcd": "etcd", "consul": "consul", "vault": "vault", "nomad": "nomad",
        "minio": "minio", "ceph": "ceph", "argo": "argo", "flux": "flux", "terraform": "terraform",
        "ansible": "ansible", "pulumi": "pulumi", "portainer": "portainer", "harbor": "harbor",
        "proxmox": "proxmox", "vmware": "vmware", "openstack": "openstack",
    },
    "Cloud and systems": {
        "cloudflare": "cloudflare", "googlecloud": "googlecloud", "digitalocean": "digitalocean",
        "hetzner": "hetzner", "ovh": "ovh", "vercel": "vercel", "netlify": "netlify", "linux": "linux",
        "ubuntu": "ubuntu", "debian": "debian", "redhat": "redhat", "alpine": "alpinelinux",
        "centos": "centos", "rocky": "rockylinux", "almalinux": "almalinux",
    },
    "Observability": {
        "grafana": "grafana", "prometheus": "prometheus", "jaeger": "jaeger", "sentry": "sentry",
        "opentelemetry": "opentelemetry", "datadog": "datadog", "newrelic": "newrelic", "elastic": "elastic",
        "kibana": "kibana", "logstash": "logstash", "fluentd": "fluentd", "fluentbit": "fluentbit",
        "victoriametrics": "victoriametrics", "thanos": "thanos", "splunk": "splunk",
        "uptimekuma": "uptimekuma", "pagerduty": "pagerduty",
    },
    "Languages and frameworks": {
        "go": "go", "python": "python", "nodejs": "nodedotjs", "deno": "deno", "bun": "bun", "php": "php",
        "laravel": "laravel", "symfony": "symfony", "django": "django", "fastapi": "fastapi", "flask": "flask",
        "rails": "rubyonrails", "ruby": "ruby", "rust": "rust", "java": "openjdk", "spring": "spring",
        "springboot": "springboot", "kotlin": "kotlin", "dotnet": "dotnet", "swift": "swift", "dart": "dart",
        "flutter": "flutter", "react": "react", "vue": "vuedotjs", "angular": "angular", "nextjs": "nextdotjs",
        "nuxt": "nuxt", "svelte": "svelte", "graphql": "graphql", "typescript": "typescript",
        "javascript": "javascript", "express": "express", "nestjs": "nestjs",
    },
    "Developer tools": {
        "git": "git", "github": "github", "gitlab": "gitlab", "bitbucket": "bitbucket", "gitea": "gitea",
        "jenkins": "jenkins", "githubactions": "githubactions", "circleci": "circleci", "jira": "jira",
        "confluence": "confluence", "jfrog": "jfrog", "nexus": "sonatype", "npm": "npm", "pypi": "pypi",
        "swagger": "swagger", "openapi": "openapiinitiative", "postman": "postman", "insomnia": "insomnia",
        "airflow": "apacheairflow", "spark": "apachespark", "flink": "apacheflink", "hadoop": "apachehadoop",
        "superset": "apachesuperset", "metabase": "metabase", "n8n": "n8n", "airbyte": "airbyte",
        "jupyter": "jupyter", "keycloak": "keycloak", "auth0": "auth0", "okta": "okta", "ollama": "ollama",
        "huggingface": "huggingface", "anthropic": "anthropic",
    },
    "Apps and payments": {
        "telegram": "telegram", "whatsapp": "whatsapp", "discord": "discord", "mattermost": "mattermost",
        "rocketchat": "rocketdotchat", "zoom": "zoom", "gmail": "gmail", "stripe": "stripe",
        "paypal": "paypal", "visa": "visa", "mastercard": "mastercard", "bitcoin": "bitcoin",
        "ethereum": "ethereum", "tether": "tether", "binance": "binance", "shopify": "shopify",
        "woocommerce": "woocommerce", "wordpress": "wordpress", "odoo": "odoo", "zapier": "zapier",
    },
}  # fmt: skip

# Lucide glyphs offered as general icons (searchable by name and Lucide's tags).
GLYPHS = [
    "message-circle",
    "messages-square",
    "message-square",
    "mail",
    "send",
    "bell",
    "phone",
    "video",
    "headphones",
    "megaphone",
    "coins",
    "gem",
    "bitcoin",
    "wallet",
    "credit-card",
    "landmark",
    "piggy-bank",
    "banknote",
    "receipt",
    "badge-dollar-sign",
    "circle-dollar-sign",
    "trending-up",
    "chart-line",
    "chart-bar",
    "chart-pie",
    "gauge",
    "activity",
    "shopping-cart",
    "shopping-bag",
    "store",
    "package",
    "truck",
    "warehouse",
    "tag",
    "ticket",
    "gift",
    "box",
    "boxes",
    "users",
    "user",
    "shield",
    "shield-check",
    "lock",
    "key-round",
    "fingerprint-pattern",
    "id-card",
    "globe",
    "cloud",
    "server",
    "database",
    "hard-drive",
    "cpu",
    "memory-stick",
    "network",
    "wifi",
    "radio-tower",
    "satellite",
    "router",
    "plug",
    "cable",
    "webhook",
    "code-xml",
    "terminal",
    "git-branch",
    "git-merge",
    "bug",
    "flask-conical",
    "test-tube-diagonal",
    "laptop",
    "monitor",
    "smartphone",
    "tablet",
    "container",
    "layers",
    "workflow",
    "cog",
    "settings",
    "wrench",
    "hammer",
    "puzzle",
    "blocks",
    "zap",
    "search",
    "file-text",
    "folder",
    "archive",
    "image",
    "film",
    "eighth-notes",
    "camera",
    "book-open",
    "newspaper",
    "notebook-pen",
    "calendar",
    "clock",
    "timer",
    "hourglass",
    "map-pin",
    "map",
    "compass",
    "navigation",
    "house",
    "building",
    "factory",
    "hospital",
    "school",
    "graduation-cap",
    "briefcase",
    "car",
    "plane",
    "ship",
    "train-front",
    "bike",
    "anchor",
    "rocket",
    "star",
    "heart",
    "flame",
    "sparkles",
    "trophy",
    "medal",
    "crown",
    "award",
    "target",
    "flag",
    "leaf",
    "sun",
    "moon",
    "snowflake",
    "tree-pine",
    "mountain",
    "droplet",
    "coffee",
    "pizza",
    "utensils",
    "gamepad-2",
    "bot",
    "brain",
    "palette",
    "brush",
    "pen-tool",
    "lightbulb",
    "inbox",
    "download",
    "upload",
    "refresh-cw",
    "repeat",
    "link",
    "qr-code",
    "printer",
    "scale",
    "stethoscope",
    "pill",
    "dumbbell",
    "paw-print",
    "circle-check",
    "circle-exclamation-point",
    "info",
]

# Environment icons: a glyph plus the environment's badge color.
ENVIRONMENTS = {
    "production": ("Production", "factory", "e5484d"),
    "staging": ("Staging", "flask-conical", "d9900b"),
    "testing": ("Testing", "test-tube-diagonal", "8b5cf6"),
    "development": ("Development", "code-xml", "22a55a"),
    "local": ("Local", "laptop", "0ea5e9"),
    "legacy": ("Legacy", "archive", "7c8794"),
}

ALLOWED_TAGS = {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse"}
SAFE_VALUE = re.compile(r"^[A-Za-z0-9 .,\-#]*$")


def brand(package, slug, colors):
    svg = (package / "icons" / f"{slug}.svg").read_text()
    title = re.search(r"<title>(.*?)</title>", svg).group(1).replace("&amp;", "&")
    path = re.search(r'<path d="([^"]+)"', svg).group(1)
    if not re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9.,\s-]+", path):
        raise ValueError(f"Unexpected path data in {slug}")
    return {"title": title, "hex": colors.get(slug, "6B7280"), "path": path}


def glyph(nodes, name):
    """Lucide's node list → inner SVG markup, allowing only plain shape elements."""
    parts = []
    for tag, attributes in nodes[name]:
        if tag not in ALLOWED_TAGS:
            raise ValueError(f"Unexpected element {tag} in {name}")
        pairs = []
        for key, value in attributes.items():
            if key == "key":
                continue
            if not re.fullmatch(r"[a-z][a-z0-9-]*", key) or not SAFE_VALUE.match(str(value)):
                raise ValueError(f"Unexpected attribute {key} in {name}")
            pairs.append(f'{key}="{value}"')
        parts.append(f"<{tag} {' '.join(pairs)}/>")
    return "".join(parts)


def main():
    simple, lucide = Path(sys.argv[1]), Path(sys.argv[2])
    data = json.loads((simple / "data" / "simple-icons.json").read_text())
    entries = data if isinstance(data, list) else data.get("icons", [])
    colors = {
        (e.get("slug") or re.sub(r"[^a-z0-9]", "", e["title"].lower())): e["hex"] for e in entries
    }
    brands, brand_categories = {}, []
    for category, members in BRANDS.items():
        keys = []
        for key, slug in members.items():
            if (simple / "icons" / f"{slug}.svg").exists():
                brands[key] = brand(simple, slug, colors)
                keys.append(key)
            else:
                print(f"skipped missing logo: {slug}")
        brand_categories.append([category, keys])
    nodes = json.loads((lucide / "icon-nodes.json").read_text())
    tags = json.loads((lucide / "tags.json").read_text())
    glyphs = {}
    for name in dict.fromkeys(GLYPHS + [g for _, g, _ in ENVIRONMENTS.values()]):
        glyphs[name] = {"body": glyph(nodes, name), "tags": " ".join(tags.get(name, []))[:160]}
    payload = {
        "brands": brands,
        "brandCategories": brand_categories,
        "glyphs": glyphs,
        "glyphNames": list(dict.fromkeys(GLYPHS)),
        "environments": {
            k: {"title": t, "glyph": g, "hex": h} for k, (t, g, h) in ENVIRONMENTS.items()
        },
    }
    versions = {
        name: json.loads((package / "package.json").read_text())["version"]
        for name, package in (("simple-icons", simple), ("lucide-static", lucide))
    }
    output = ROOT / "bandar" / "web" / "js" / "icon-data.js"
    output.write_text(
        "/* Generated by scripts/make_icons.py — do not edit.\n"
        f" * Logos: Simple Icons {versions['simple-icons']} (CC0-1.0); trademarks of their owners.\n"
        f" * Glyphs: Lucide {versions['lucide-static']} (ISC, see ICONS-LICENSE.txt). */\n"
        f"window.BandarIconData = {json.dumps(payload, separators=(',', ':'))};\n",
        encoding="utf-8",
    )
    notice = (lucide / "LICENSE").read_text()
    (ROOT / "bandar" / "web" / "js" / "ICONS-LICENSE.txt").write_text(
        "Glyph icons: Lucide (https://lucide.dev)\n\n" + notice + "\n\n"
        "Brand logos: Simple Icons (https://simpleicons.org), CC0-1.0. Logos are trademarks of\n"
        "their respective owners and are used only to identify the technology.\n",
        encoding="utf-8",
    )
    print(f"{len(brands)} logos, {len(glyphs)} glyphs → {output}")


if __name__ == "__main__":
    main()
