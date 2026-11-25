"""Create the GitHub Pages site: landing page plus a signed APT repository.

    python scripts/create_apt_repository.py dist/*.deb --url https://USER.github.io/bandar \
        --key FINGERPRINT [--gnupghome DIR] [--passphrase-file FILE]
"""

import argparse
import gzip
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bandar import REPOSITORY, VERSION  # noqa: E402


def check_url(base_url):
    url = urlsplit(base_url)
    unsafe = any(c.isspace() for c in base_url) or any(c in base_url for c in "'\"`\\<>")
    if (
        url.scheme != "https"
        or not url.netloc
        or url.username
        or url.query
        or url.fragment
        or unsafe
    ):
        raise ValueError("Provide a public HTTPS base URL without credentials, query or fragment")


def install_commands(base_url, key):
    return f"""sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSLo /tmp/bandar-archive-keyring.gpg '{base_url}/bandar-archive-keyring.gpg'
gpg --show-keys --with-fingerprint /tmp/bandar-archive-keyring.gpg
# Expected fingerprint: {key.upper()}
sudo install -m 0644 /tmp/bandar-archive-keyring.gpg /etc/apt/keyrings/bandar-archive-keyring.gpg
curl -fsSLo /tmp/bandar.sources '{base_url}/bandar.sources'
sudo install -m 0644 /tmp/bandar.sources /etc/apt/sources.list.d/bandar.sources
curl -fsSLo /tmp/bandar.pref '{base_url}/bandar.pref'
sudo install -m 0644 /tmp/bandar.pref /etc/apt/preferences.d/bandar
sudo apt update
sudo apt install bandar
"""


def render_site(output, base_url, commands):
    """Copy site/ and fill the landing page's placeholders."""
    shutil.copytree(ROOT / "site", output, dirs_exist_ok=True)
    page = (output / "index.html").read_text(encoding="utf-8")
    for name, value in {
        "VERSION": html.escape(VERSION),
        "REPOSITORY": html.escape(REPOSITORY),
        "BASE_URL": html.escape(base_url),
        "INSTALL_COMMANDS": html.escape(commands),
    }.items():
        page = page.replace("{{" + name + "}}", value)
    if "{{" in page:
        raise ValueError("Unfilled placeholder in site/index.html")
    (output / "index.html").write_text(page, encoding="utf-8")


def create(packages, output, base_url, key, gnupghome=None, passphrase_file=None):
    check_url(base_url)
    if not re.fullmatch(r"(?:[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})", key):
        raise ValueError("Use the full signing-key fingerprint")
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("The output must be empty; each build is deployed whole")
    if not packages:
        raise ValueError("At least one .deb package is required")
    pool = output / "pool/main/b/bandar"
    pool.mkdir(parents=True)
    for package in map(Path, packages):
        fields = subprocess.check_output(["dpkg-deb", "--field", str(package)], text=True)
        fields = dict(
            line.split(": ", 1)
            for line in fields.splitlines()
            if ": " in line and not line.startswith(" ")
        )
        if fields.get("Package") != "bandar" or fields.get("Architecture") != "amd64":
            raise ValueError(f"Expected a Bandar amd64 package: {package}")
        version = fields["Version"]
        if not re.fullmatch(r"[0-9][A-Za-z0-9.+~:-]*", version):
            raise ValueError("Invalid package version")
        shutil.copy2(package, pool / f"bandar_{version}_amd64.deb")
    index = output / "dists/stable/main/binary-amd64"
    index.mkdir(parents=True)
    data = subprocess.check_output(
        ["dpkg-scanpackages", "--multiversion", "pool", "/dev/null"], cwd=output
    )
    (index / "Packages").write_bytes(data)
    (index / "Packages.gz").write_bytes(gzip.compress(data, mtime=0))
    options = []
    for name, value in (
        ("Origin", "Bandar"),
        ("Label", "Bandar"),
        ("Suite", "stable"),
        ("Codename", "stable"),
        ("Architectures", "amd64"),
        ("Components", "main"),
    ):
        options += ["-o", f"APT::FTPArchive::Release::{name}={value}"]
    release = output / "dists/stable/Release"
    release.write_bytes(
        subprocess.check_output(["apt-ftparchive", *options, "release", "dists/stable"], cwd=output)
    )
    gpg = ["gpg", "--batch", "--yes"] + (
        ["--homedir", str(Path(gnupghome).resolve())] if gnupghome else []
    )
    signing = [*gpg, "--local-user", key, "--digest-algo", "SHA256"]
    if passphrase_file:
        signing += ["--pinentry-mode", "loopback", "--passphrase-file", str(passphrase_file)]
    subprocess.run(
        [*signing, "--output", str(release.with_name("InRelease")), "--clearsign", str(release)],
        check=True,
    )
    subprocess.run(
        [
            *signing,
            "--armor",
            "--output",
            str(release.with_name("Release.gpg")),
            "--detach-sign",
            str(release),
        ],
        check=True,
    )
    public_key = subprocess.check_output([*gpg, "--export", key])
    if not public_key:
        raise ValueError("The signing key has no exportable public certificate")
    (output / "bandar-archive-keyring.gpg").write_bytes(public_key)
    base_url = base_url.rstrip("/")
    (output / "bandar.sources").write_text(
        f"Types: deb\nURIs: {base_url}\nSuites: stable\nComponents: main\nArchitectures: amd64\n"
        "Signed-By: /etc/apt/keyrings/bandar-archive-keyring.gpg\n"
    )
    # A scoped pin keeps this repository from supplying any package but Bandar.
    (output / "bandar.pref").write_text(
        "Package: *\nPin: release o=Bandar\nPin-Priority: 1\n\n"
        "Package: bandar\nPin: release o=Bandar\nPin-Priority: 500\n"
    )
    commands = install_commands(base_url, key)
    (output / "INSTALL.txt").write_text("Bandar — Ubuntu 24.04+ amd64\n\n" + commands)
    render_site(output, base_url, commands)
    (output / ".nojekyll").touch()
    for path in [output, *output.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    digest = hashlib.sha256((output / "dists/stable/Release").read_bytes()).hexdigest()
    print(f"Repository ready in {output} (Release sha256 {digest[:16]}…)")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("dist/apt"))
    parser.add_argument("--url", required=True)
    parser.add_argument("--key", required=True, help="full OpenPGP fingerprint")
    parser.add_argument("--gnupghome", default=os.environ.get("GNUPGHOME"))
    parser.add_argument("--passphrase-file", type=Path)
    args = parser.parse_args()
    create(args.packages, args.output, args.url, args.key, args.gnupghome, args.passphrase_file)


if __name__ == "__main__":
    main()
