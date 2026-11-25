# Releasing Bandar

The baseline is **Ubuntu 24.04 amd64**: the bundle is frozen inside an Ubuntu 24.04
container, so it needs no newer GLIBC than 2.39 and runs on 24.04 and later.

## Build locally

```bash
python3 scripts/build_ubuntu24.py        # Docker: builds the image, the .deb, and starts the bundle under Xvfb
sudo apt install ./dist/bandar_1.3.0-1_amd64.deb
```

`scripts/build_deb.py --local` builds a package on the host for that machine only.

## Publish (GitHub Actions)

`.github/workflows/release.yml` builds and tests the package, attaches it to a GitHub
release and deploys the site plus a signed APT repository to GitHub Pages.

One-time setup:

1. **Settings → Pages**: source **GitHub Actions**.
2. **Settings → Environments → github-pages**: allow the `master` branch and a tag rule `v*-*`.
3. Create a dedicated OpenPGP signing key (RSA 3072+ or Ed25519) and keep a backup; the key must
   stay the same so installed systems keep receiving updates. Never commit it.
4. **Actions secrets**: `APT_SIGNING_KEY` (armored private key) and `APT_SIGNING_PASSPHRASE`.
   **Actions variable**: `APT_SIGNING_FINGERPRINT` (full fingerprint).
5. Run the workflow with `publish` unchecked to verify, then push a tag such as `v1.3.0-1`
   (it must match `bandar.VERSION` and `DEBIAN_REVISION`) to publish.

The site source is `site/`; `scripts/create_apt_repository.py` fills in the version and the
install commands. Screenshots come from `scripts/screens.py` with `tests/fixtures/sample-services.txt`.
