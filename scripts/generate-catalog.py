#!/usr/bin/env python3
"""Generate uv's download catalog from the manifest and built archives."""

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
    if len(sys.argv) != 4:
        print(
            f"usage: {sys.argv[0]} VERSIONS.json RELEASE_TAG DIST_DIR",
            file=sys.stderr,
        )
        return 2

    manifest_path = pathlib.Path(sys.argv[1])
    tag = sys.argv[2]
    dist = pathlib.Path(sys.argv[3])
    manifest = json.loads(manifest_path.read_text())
    target = manifest["target"]
    catalog: dict[str, dict[str, object]] = {}

    for stream in manifest["streams"]:
        if stream["status"] != "supported":
            continue
        version = stream["version"]
        major, minor, patch = (int(part) for part in version.split("."))
        archive = dist / f"cpython-{version}-android-{target['arch']}.tar.gz"
        if not archive.is_file():
            print(f"missing artifact for {stream['python']}: {archive}", file=sys.stderr)
            return 1
        key = f"cpython-{version}-{target['uv_os']}-{target['arch']}-{target['uv_libc']}"
        catalog[key] = {
            "name": "cpython",
            "arch": {"family": target["arch"], "variant": None},
            # uv currently represents the Termux host as Linux/no-libc.
            "os": target["uv_os"],
            "libc": target["uv_libc"],
            "major": major,
            "minor": minor,
            "patch": patch,
            "build": f"termux-{stream['termux_recipe_ref'][:12]}",
            "url": (
                "https://github.com/musantro/termux-python-standalone/releases/"
                f"download/{tag}/{archive.name}"
            ),
            "sha256": sha256(archive),
        }

    output = dist / "python-downloads.json"
    output.write_text(json.dumps(dict(sorted(catalog.items())), indent=2) + "\n")
    print(f"generated {len(catalog)} downloads in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
