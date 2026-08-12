#!/usr/bin/env python3
"""Set a Termux Python recipe to build a specific CPython source release."""

from __future__ import annotations

import pathlib
import re
import sys


VERSION_RE = re.compile(r"^TERMUX_PKG_VERSION\s*=.*$")
SHA_ASSIGN_RE = re.compile(r"^TERMUX_PKG_SHA256\s*=\s*(.*)$")
SHA_VALUE_RE = re.compile(r"^(\s*)([0-9a-fA-F]{64})(\s*)$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
PRE_CONFIGURE_RE = re.compile(r"^termux_step_pre_configure\(\)\s*\{\s*$")


def ensure_build_python_hook(text: str, path: pathlib.Path) -> str:
    """Ensure cross-build recipes prepare a matching host Python.

    Recent Termux Python recipes call ``termux_setup_build_python`` from their
    pre-configure hook.  Older pinned recipes only pass ``--with-build-python``
    to configure, which leaves that binary missing in the builder container.
    The recipe is copied into a temporary checkout before this script runs, so
    adding the hook here keeps the remote recipe immutable while making the
    behavior consistent across all supported Python streams.
    """
    if re.search(r"^\s*termux_setup_build_python\s*$", text, re.MULTILINE):
        return text

    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if PRE_CONFIGURE_RE.match(line):
            ending = "\n" if line.endswith("\n") else ""
            indent = "\t" if line[:1] != " " else "    "
            lines.insert(
                index + 1,
                f"{indent}# Build the matching host Python before cross-configuring.\n"
                f"{indent}termux_setup_build_python{ending}",
            )
            return "".join(lines)

    raise ValueError(f"{path}: no termux_step_pre_configure function")


def main() -> int:
    if len(sys.argv) != 4:
        print(f"usage: {sys.argv[0]} RECIPE.sh VERSION SOURCE_SHA256", file=sys.stderr)
        return 2
    path = pathlib.Path(sys.argv[1])
    version = sys.argv[2]
    source_sha256 = sys.argv[3]
    if not SHA256_RE.fullmatch(source_sha256):
        print("SOURCE_SHA256 must be a 64-character hexadecimal digest", file=sys.stderr)
        return 1

    lines = path.read_text().splitlines(keepends=True)
    output: list[str] = []
    version_replaced = False
    sha_replaced = False
    sha_array = False
    checksum = source_sha256

    for line in lines:
        if not version_replaced and VERSION_RE.match(line):
            ending = "\n" if line.endswith("\n") else ""
            output.append(f'TERMUX_PKG_VERSION="{version}"{ending}')
            version_replaced = True
            continue

        sha_assignment = SHA_ASSIGN_RE.match(line)
        if sha_assignment and not sha_replaced:
            rhs = sha_assignment.group(1).strip()
            sha_array = rhs == "("
            if sha_array:
                output.append(line)
            else:
                ending = "\n" if line.endswith("\n") else ""
                output.append(f"TERMUX_PKG_SHA256={checksum}{ending}")
                sha_replaced = True
            continue

        if sha_array and not sha_replaced:
            value = SHA_VALUE_RE.match(line)
            if value:
                output.append(f"{value.group(1)}{checksum}{value.group(3)}")
                sha_replaced = True
                continue

        output.append(line)

    if not version_replaced:
        print(f"{path}: no TERMUX_PKG_VERSION assignment", file=sys.stderr)
        return 1
    if not sha_replaced:
        print(f"{path}: no TERMUX_PKG_SHA256 assignment", file=sys.stderr)
        return 1
    try:
        recipe = ensure_build_python_hook("".join(output), path)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    path.write_text(recipe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
