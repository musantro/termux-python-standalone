#!/usr/bin/env python3
"""Render the supported manifest streams as a GitHub Actions matrix."""

from __future__ import annotations

import json
import pathlib
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} VERSIONS.json", file=sys.stderr)
        return 2
    manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
    builder_image = manifest["target"]["termux_builder_image"]
    include = [
        {
            "python": stream["python"],
            "version": stream["version"],
            "termux_builder_ref": stream["termux_builder_ref"],
            "termux_recipe_ref": stream["termux_recipe_ref"],
            "termux_builder_image": builder_image,
        }
        for stream in manifest["streams"]
        if stream["status"] == "supported"
    ]
    if not include:
        print("manifest has no supported streams", file=sys.stderr)
        return 1
    print(json.dumps({"include": include}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
