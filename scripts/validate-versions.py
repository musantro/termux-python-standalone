#!/usr/bin/env python3
"""Validate the Python release and Termux build-profile manifest."""

from __future__ import annotations

import json
import pathlib
import re
import sys


HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
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

    if manifest.get("schema") != 2:
        print("manifest schema must be 2", file=sys.stderr)
        return 1
    target = manifest.get("target")
    expected_target = {
        "arch": "aarch64",
        "android_api": 24,
        "uv_os": "linux",
        "uv_libc": "none",
    }
    if any(target.get(key) != value for key, value in expected_target.items()):
        print("manifest target must describe Android aarch64/API24 and uv linux/none", file=sys.stderr)
        return 1
    if not IMAGE_DIGEST.fullmatch(target["termux_builder_image"]):
        print("termux_builder_image must be pinned by a sha256 digest", file=sys.stderr)
        return 1

    source = manifest.get("source")
    if not isinstance(source, dict):
        print("manifest source must be an object", file=sys.stderr)
        return 1
    for field in ("release_cycle_url", "ftp_index_url", "release_page_url"):
        if not isinstance(source.get(field), str) or not source[field].startswith("https://"):
            print(f"source.{field} must be an HTTPS URL", file=sys.stderr)
            return 1
    if not isinstance(source.get("statuses"), list) or not source["statuses"]:
        print("source.statuses must be a non-empty list", file=sys.stderr)
        return 1

    streams = manifest.get("streams")
    if not isinstance(streams, list) or not streams:
        print("manifest streams must be a non-empty list", file=sys.stderr)
        return 1

    seen_python: set[str] = set()
    seen_versions: set[str] = set()
    stream_status: dict[str, str] = {}
    for stream in streams:
        required = {
            "python",
            "termux_builder_ref",
            "termux_recipe_ref",
            "status",
        }
        missing = required - stream.keys()
        if missing:
            print(f"stream missing: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1
        python = stream["python"]
        if not isinstance(python, str) or not VERSION.fullmatch(python):
            print(f"invalid Python stream: {python!r}", file=sys.stderr)
            return 1
        if python in seen_python:
            print(f"duplicate stream: {python}", file=sys.stderr)
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
        stream_status[python] = stream["status"]

    releases = manifest.get("releases")
    if not isinstance(releases, list) or not releases:
        print("manifest releases must be a non-empty list", file=sys.stderr)
        return 1
    for release in releases:
        required = {"python", "version", "source_sha256", "status"}
        missing = required - release.keys()
        if missing:
            print(f"release missing: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1
        python = release["python"]
        version = release["version"]
        source_sha256 = release["source_sha256"]
        if not isinstance(python, str) or python not in seen_python:
            print(f"release references unknown stream: {python!r}", file=sys.stderr)
            return 1
        if release["status"] == "supported" and stream_status[python] != "supported":
            print(f"{version}: supported release belongs to a disabled stream", file=sys.stderr)
            return 1
        if not isinstance(version, str) or not FULL_VERSION.fullmatch(version):
            print(f"invalid CPython release: {version!r}", file=sys.stderr)
            return 1
        if not version.startswith(f"{python}."):
            print(f"{version} does not belong to stream {python}", file=sys.stderr)
            return 1
        if version in seen_versions:
            print(f"duplicate release: {version}", file=sys.stderr)
            return 1
        if not isinstance(source_sha256, str) or not HEX64.fullmatch(source_sha256):
            print(f"{version}: source_sha256 must be a 64-character digest", file=sys.stderr)
            return 1
        if release["status"] not in {"supported", "disabled"}:
            print(f"invalid release status for {version}: {release['status']!r}", file=sys.stderr)
            return 1
        seen_versions.add(version)

    print(f"validated {len(streams)} Termux Python streams and {len(releases)} releases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
