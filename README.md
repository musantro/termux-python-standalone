# termux-python-standalone

Standalone CPython builds for Termux/Android, consumable by `uv`.

The project targets the `aarch64-linux-android` ABI used by modern 64-bit
Termux installations. GitHub Actions builds the Termux Python package for
CPython 3.13.13 and 3.14.6, repackages it as a `uv` managed installation, and
publishes both archives together with a signed-by-hash download catalog.

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
uv python install 3.13
uv python install 3.14
```

The release catalog is versioned so that an existing environment does not
silently change when a later build is published.

## Validate an installation on Termux

Pass the managed interpreter to the smoke test:

```sh
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
./scripts/validate-metadata.py metadata/python-downloads.example.json
```

The build workflow runs on `ubuntu-24.04`, uses the Android NDK through the
official Termux package build system, and publishes a release when a `v*` tag
is pushed.

## License

The repository scripts are MIT licensed. CPython and Termux package contents
retain their upstream licenses; see the release notes and the included license
files for attribution.
