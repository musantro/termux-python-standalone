# termux-python-standalone

Standalone CPython builds for Termux/Android, consumable by `uv`.

The project targets the `aarch64-linux-android` ABI used by modern 64-bit
Termux installations. GitHub Actions builds the supported CPython streams,
repackages them as `uv` managed installations, and publishes the archives
together with a checksum-verified download catalog.

## Current target

This first MVP targets:

- `aarch64` / `arm64-v8a`;
- Android API 24 or newer (the current device is API 36);
- the official `com.termux` prefix and its runtime libraries.

The archives are Termux-compatible builds. They are not glibc Linux builds and
must not be used on a regular Linux distribution.

## Use a published release

After the first release, point `uv` at the catalog published with that release:

```sh
export UV_PYTHON_DOWNLOADS_JSON_URL=\
  https://github.com/musantro/termux-python-standalone/releases/download/v0.1.0/python-downloads.json

uv python list --only-downloads --show-urls
uv python install 3.10
uv python install 3.11
uv python install 3.12
uv python install 3.13
uv python install 3.14
```

The release catalog is versioned so that an existing environment does not
silently change when a later build is published. The `latest-release` pointer
is reserved for a future convenience URL; immutable release URLs are the
recommended interface for now.

## Validate an installation on Termux

Pass the managed interpreter to the smoke test:

```sh
./scripts/smoke-test.sh "$(uv python find 3.10)"
./scripts/smoke-test.sh "$(uv python find 3.11)"
./scripts/smoke-test.sh "$(uv python find 3.12)"
./scripts/smoke-test.sh "$(uv python find 3.13)"
./scripts/smoke-test.sh "$(uv python find 3.14)"
```

The test checks the interpreter version, Android platform tag, `sqlite3`,
OpenSSL, `ctypes`, and a basic virtual environment.

## Build locally

The GitHub workflow is the canonical build because it uses a clean Ubuntu
builder and the pinned Termux package recipes. Local development only needs a
POSIX shell and Python for metadata validation:

```sh
./scripts/validate-versions.py versions.json
./scripts/validate-metadata.py metadata/python-downloads.example.json
```

## Maintaining supported versions

`versions.json` is the single source of truth. It contains the supported
minor streams, their exact Termux recipe commits, and the pinned builder
commit. The current set follows Python's active stable branches: 3.10, 3.11,
3.12, 3.13 and 3.14. Python 3.15 is intentionally left out while it is a
pre-release, and 3.9 is end-of-life. The release workflow renders its matrix,
catalog and runtime smoke-test loop directly from this manifest; no version
list should be duplicated in a workflow.
The Termux builder image is pinned by digest in the same target block.

The scheduled `Sync Termux Python recipes` workflow checks the current
`termux/termux-packages` recipe and opens or updates a PR when an enabled stream
changes. Termux currently maintains one `python` package (the current 3.14
stream), so the older active streams use their last reproducible Termux recipe
commit until Termux publishes a newer recipe for them. New minor streams are
intentionally not enabled automatically.

After that PR is merged, the release workflow runs automatically, creates a
date-based immutable tag such as `termux-python-20260811.1`, builds all
supported streams in parallel, creates a draft release, verifies uploaded
checksums and catalog entries, and only then publishes it. A `vX.Y.Z` tag or a
manual workflow dispatch can also be used for a manually named release.

The build uses Docker and the digest-pinned official Termux package-builder
image for a reproducible packaging environment. The release workflow also
uses the `termux/termux-docker:aarch64` image plus QEMU to run every supported
interpreter and `uv` in a Termux-like container. This catches most runtime
regressions;
the real device smoke test remains useful because the container does not expose
every Android system component.

## License

The repository scripts are MIT licensed. CPython and Termux package contents
retain their upstream licenses; see the release notes and the included license
files for attribution.
