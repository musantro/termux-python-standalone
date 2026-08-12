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

After a release, point `uv` at the catalog published with that release:

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

On the target Termux device, the repository includes a helper that checks the
device ABI/API and exports the catalog variables in the current shell:

```sh
source ./scripts/setup-uv-termux.sh
uv python list --only-downloads --show-urls
uv python install 3.14
```

If you only want to configure an existing Termux installation, run this
one-liner. It downloads the interactive installer from this repository:

```sh
curl -fsSL https://raw.githubusercontent.com/musantro/termux-python-standalone/main/scripts/install-uv-termux.sh | bash
```

The installer shows the catalog URL, the startup file it selected, and the
exact managed block before asking for authorization. It only edits that block;
it does not install packages or Python. At the end it reports whether a file
was created, updated, or left unchanged. Open a new shell afterwards, or run
the `source` command printed by the installer, then check the catalog with
`uv python list --only-downloads --show-urls`.

The helper uses the mutable `latest` release pointer by default. To keep an
environment reproducible, source it with an immutable release tag instead:

```sh
source ./scripts/setup-uv-termux.sh termux-python-20260811.1
```

The only required setting is `UV_PYTHON_DOWNLOADS_JSON_URL`; the helper also
sets `UV_PYTHON_DOWNLOADS=automatic` so a previous `never` setting does not
silently disable downloads. Add the `source` command to the shell startup file
if it should be applied to every new Termux session.

The release catalog is versioned so that an existing environment does not
silently change when a later build is published. The `latest` release pointer
is convenient but mutable; immutable release URLs are recommended when exact
reproducibility matters.

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

`versions.json` is the single source of truth. It has two layers:

- `streams` defines the Android adaptation profile for each supported minor
  branch and pins the Termux builder/recipe commits;
- `releases` contains every final Python Foundation patch release selected for
  those branches, including its official source SHA-256.

The current set follows Python's active stable branches: 3.10, 3.11, 3.12,
3.13 and 3.14. Python 3.15 is left out while it is a pre-release, and 3.9 is
end-of-life. The release workflow renders its build matrix and catalog directly
from this manifest; no version list is duplicated in a workflow.
The Termux builder image is pinned by digest in the same target block.

The scheduled `Sync Python Foundation releases` workflow reads Python's release
cycle metadata and the official source archive index. It adds newly published
final patch releases, computes a SHA-256 when the historical release page does
not provide one, and opens or updates a PR. Existing releases are never removed,
so old immutable catalog entries remain reproducible. Termux does not need to
publish a package for each patch: its recipe is used as the Android patch
profile, while the pinned builder compiles the requested Python Foundation
source version directly.

After that PR is merged, the release workflow runs automatically, creates a
date-based immutable tag such as `termux-python-20260811.1`, builds all
supported streams in parallel, creates a draft release, verifies uploaded
checksums and catalog entries, and only then publishes it. A `vX.Y.Z` tag or a
manual workflow dispatch can also be used for a manually named release.

The build uses Docker and the digest-pinned official Termux package-builder
image for a reproducible packaging environment. For each source release the
workflow overrides only the recipe's Python version and source checksum; the
Android patches and build infrastructure remain pinned. The release workflow also
uses the `termux/termux-docker:aarch64` image plus QEMU to run every supported
interpreter and `uv` in a Termux-like container. This catches most runtime
regressions;
the real device smoke test remains useful because the container does not expose
every Android system component.

## License

The repository scripts are MIT licensed. CPython and Termux package contents
retain their upstream licenses; see the release notes and the included license
files for attribution.
