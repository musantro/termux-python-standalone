#!/usr/bin/env python3
"""Generate uv's download catalog from release artifacts and checksums."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} VERSION RELEASE_TAG", file=sys.stderr)
        return 2
    version = sys.argv[1]
    tag = sys.argv[2]
    major, minor, patch = (int(part) for part in version.split("."))
    root = pathlib.Path.cwd()
    archive = root / "dist" / f"cpython-{version}-android-aarch64.tar.gz"
    if not archive.is_file():
        print(f"missing artifact: {archive}", file=sys.stderr)
        return 1
    entry = {
        "name": "cpython",
        "arch": {"family": "aarch64", "variant": None},
        # The binary target is aarch64-linux-android. uv 0.11 currently detects
        # the Termux host as Linux with no libc, so `none` is the compatibility
        # value needed for the managed-download selector.
        "os": "linux",
        "libc": "none",
        "major": major,
        "minor": minor,
        "patch": patch,
        "url": f"https://github.com/musantro/termux-python-standalone/releases/download/{tag}/{archive.name}",
        "sha256": sha256(archive),
    }
    key = f"cpython-{version}-linux-aarch64-none"
    catalog_path = root / "dist" / "python-downloads.json"
    existing = json.loads(catalog_path.read_text()) if catalog_path.exists() else {}
    existing[key] = entry
    catalog_path.write_text(json.dumps(dict(sorted(existing.items())), indent=2) + "\n")
    print(f"added {key} to {catalog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
