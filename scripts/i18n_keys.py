"""List interface strings that a catalog does not translate yet.

.venv/bin/python scripts/i18n_keys.py fa|ar
"""

import json
import re
import subprocess
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "bandar" / "web"


def interface_keys():
    keys = []
    for path in sorted((WEB / "js").glob("*.js")):
        if path.name in {"fa.js", "ar.js"}:
            continue
        text = path.read_text()
        keys += re.findall(r"\bt\(\s*'((?:[^'\\]|\\.)*)'", text)
        if path.name == "messages.js":
            keys += re.findall(r"(?:title|hint): '((?:[^'\\]|\\.)*)'", text)
            keys += re.findall(r"^\s+\w+: '((?:[^'\\]|\\.)*)',$", text, re.M)
        keys += re.findall(r"\[\s*'[\w+,/ .-]*',\s*'([A-Z][^']*)'", text)
        keys += (
            re.findall(r"\b\w+: '([A-Z][A-Za-z ]+)'", text)
            if path.name in {"list.js", "sidebar.js"}
            else []
        )
    html = (WEB / "index.html").read_text()
    keys += [k.strip().replace("&amp;", "&") for k in re.findall(r"data-t>([^<]+)<", html)]
    keys += re.findall(r'data-t-(?:title|placeholder|aria)="([^"]+)"', html)
    keys += ["d", "h", "m", "s"]
    icons = (WEB / "js" / "icons.js").read_text()
    keys += re.findall(r"^\s+\['([A-Z][^']*)', '", icons, re.M)  # emoji categories
    keys += re.findall(r"section\('([^']+)'", icons)
    data = (WEB / "js" / "icon-data.js").read_text()
    payload = json.loads(data[data.index("{") : data.rindex("}") + 1])
    keys += [title for title, _ in payload["brandCategories"]]
    keys += [env["title"] for env in payload["environments"].values()]
    return list(dict.fromkeys(k.replace("\\'", "'") for k in keys if k))


def catalog(language):
    script = (
        f"global.window={{}};require('{WEB}/js/{language}.js');"
        f"console.log(JSON.stringify(window.{'BandarPersian' if language == 'fa' else 'BandarArabic'}))"
    )
    return json.loads(subprocess.check_output(["node", "-e", script], text=True))


if __name__ == "__main__":
    language = sys.argv[1]
    known = catalog(language) if (WEB / "js" / f"{language}.js").exists() else {}
    missing = [key for key in interface_keys() if key not in known]
    print(json.dumps(missing, ensure_ascii=False, indent=1))
    print(f"{len(missing)} missing of {len(interface_keys())}", file=sys.stderr)
