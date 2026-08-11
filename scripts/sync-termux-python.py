#!/usr/bin/env python3
"""Update a supported stream from a pinned Termux Python recipe checkout."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


VERSION_RE = re.compile(r"^TERMUX_PKG_VERSION\s*=\s*[\"']?([0-9]+\.[0-9]+\.[0-9]+)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=pathlib.Path)
    parser.add_argument("--recipe-ref", required=True)
    parser.add_argument("--recipe-file", type=pathlib.Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    recipe_text = args.recipe_file.read_text()
    match = next(
        (
            candidate
            for line in recipe_text.splitlines()
            if (candidate := VERSION_RE.match(line.strip())) is not None
        ),
        None,
    )
    if match is None:
        print("could not find TERMUX_PKG_VERSION in the Termux recipe", file=sys.stderr)
        return 1
    recipe_version = match.group(1)
    stream_name = ".".join(recipe_version.split(".")[:2])
    stream = next(
        (item for item in manifest["streams"] if item["python"] == stream_name),
        None,
    )
    if stream is None:
        print(
            f"Termux offers {recipe_version}, but stream {stream_name} is not enabled; "
            "leaving the allowlist unchanged",
        )
        return 0

    if tuple(map(int, recipe_version.split("."))) < tuple(map(int, stream["version"].split("."))):
        print(f"Termux recipe {recipe_version} is older than pinned {stream['version']}; unchanged")
        return 0

    changed = stream["version"] != recipe_version or stream["termux_recipe_ref"] != args.recipe_ref
    if not changed:
        print(f"{stream_name} is already current at {recipe_version} ({args.recipe_ref})")
        return 0

    stream["version"] = recipe_version
    stream["termux_recipe_ref"] = args.recipe_ref
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"updated {stream_name} to {recipe_version} ({args.recipe_ref})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
