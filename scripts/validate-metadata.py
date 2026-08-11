#!/usr/bin/env python3
"""Validate the subset of uv's Python download catalog used by this project."""

from __future__ import annotations

import json
import pathlib
import sys
from urllib.parse import urlparse


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} CATALOG.json", file=sys.stderr)
        return 2

    path = pathlib.Path(sys.argv[1])
    try:
        catalog = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid catalog {path}: {exc}", file=sys.stderr)
        return 1

    if not isinstance(catalog, dict) or not catalog:
        print("catalog must be a non-empty JSON object", file=sys.stderr)
        return 1

    versions: set[tuple[int, int, int]] = set()
    for key, entry in catalog.items():
        required = {"name", "arch", "os", "libc", "major", "minor", "patch", "url"}
        missing = required - entry.keys()
        if missing:
            print(f"{key}: missing {', '.join(sorted(missing))}", file=sys.stderr)
            return 1
        if entry["name"] != "cpython":
            print(f"{key}: only CPython entries are supported", file=sys.stderr)
            return 1
        if entry["os"] != "linux" or entry["libc"] != "none":
            print(f"{key}: expected uv's Linux/none compatibility platform", file=sys.stderr)
            return 1
        if entry["arch"].get("family") != "aarch64" or entry["arch"].get("variant") is not None:
            print(f"{key}: expected aarch64 without a CPU variant", file=sys.stderr)
            return 1
        version = (entry["major"], entry["minor"], entry["patch"])
        versions.add(version)
        parsed = urlparse(entry["url"])
        if parsed.scheme != "https" or not parsed.netloc:
            print(f"{key}: URL must be HTTPS", file=sys.stderr)
            return 1
        digest = entry.get("sha256")
        if digest is not None and (len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest)):
            print(f"{key}: sha256 must be a 64-character hexadecimal digest", file=sys.stderr)
            return 1

    if len(versions) != 2:
        print(f"expected exactly two Python versions, found {sorted(versions)}", file=sys.stderr)
        return 1
    print(f"validated {len(catalog)} Android/aarch64 Python downloads: {sorted(versions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
