#!/usr/bin/env python3
"""Validate the Termux Python stream manifest."""

from __future__ import annotations

import json
import pathlib
import re
import sys


HEX40 = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST = re.compile(r"^ghcr\.io/[^@]+@sha256:[0-9a-f]{64}$")
VERSION = re.compile(r"^(\d+)\.(\d+)$")
FULL_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} VERSIONS.json", file=sys.stderr)
        return 2

    path = pathlib.Path(sys.argv[1])
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid manifest {path}: {exc}", file=sys.stderr)
        return 1

    if manifest.get("schema") != 1:
        print("manifest schema must be 1", file=sys.stderr)
        return 1
    target = manifest.get("target")
    if target != {
        "arch": "aarch64",
        "android_api": 24,
        "uv_os": "linux",
        "uv_libc": "none",
        "termux_builder_image": "ghcr.io/termux/package-builder@sha256:4471cc862c570b15c3a0440668e80b37c9c1750d94fa88a0a4885d959ccf832e",
    }:
        print("manifest target must describe Android aarch64/API24 and uv linux/none", file=sys.stderr)
        return 1
    if not IMAGE_DIGEST.fullmatch(target["termux_builder_image"]):
        print("termux_builder_image must be pinned by a sha256 digest", file=sys.stderr)
        return 1

    streams = manifest.get("streams")
    if not isinstance(streams, list) or not streams:
        print("manifest streams must be a non-empty list", file=sys.stderr)
        return 1

    seen_python: set[str] = set()
    seen_versions: set[str] = set()
    for stream in streams:
        required = {
            "python",
            "version",
            "termux_builder_ref",
            "termux_recipe_ref",
            "status",
        }
        missing = required - stream.keys()
        if missing:
            print(f"stream missing: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1
        python = stream["python"]
        version = stream["version"]
        if not isinstance(python, str) or not VERSION.fullmatch(python):
            print(f"invalid Python stream: {python!r}", file=sys.stderr)
            return 1
        if not isinstance(version, str) or not FULL_VERSION.fullmatch(version):
            print(f"invalid CPython version: {version!r}", file=sys.stderr)
            return 1
        if not version.startswith(f"{python}."):
            print(f"{version} does not belong to stream {python}", file=sys.stderr)
            return 1
        if python in seen_python or version in seen_versions:
            print(f"duplicate stream/version: {python} / {version}", file=sys.stderr)
            return 1
        if stream["status"] not in {"supported", "disabled"}:
            print(f"invalid status for {python}: {stream['status']!r}", file=sys.stderr)
            return 1
        for field in ("termux_builder_ref", "termux_recipe_ref"):
            value = stream[field]
            if not isinstance(value, str) or not HEX40.fullmatch(value):
                print(f"{python}: {field} must be a 40-character commit", file=sys.stderr)
                return 1
        seen_python.add(python)
        seen_versions.add(version)

    print(f"validated {len(streams)} Termux Python streams: {sorted(seen_versions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
