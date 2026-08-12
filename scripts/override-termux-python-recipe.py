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


def ensure_legacy_configure_hook(text: str, path: pathlib.Path) -> str:
    """Replace the stale 3.10 configure patch with a version-aware hook.

    The pinned 3.10 Termux recipe carries a patch generated against CPython
    3.6. Its multiarch hunk does not apply to the first 3.10 releases (and
    can apply with fuzz to later ones), while the CCSHARED and HAVE_LINK
    changes are still required on Android. Apply those edits after unpacking
    the source, where stable semantic markers are available.
    """
    configure_patch = path.parent / "configure.patch"
    if not configure_patch.exists():
        return text

    hook = r'''
termux_step_post_get_source() {
	# The historical recipe's configure.patch was generated from CPython 3.6.
	# Apply its Android adjustments by semantic markers so every 3.10 patch
	# release (including 3.10.0) can use the same pinned recipe.
	python3 - <<'PY'
import os
import pathlib
import re

configure = pathlib.Path(os.environ["TERMUX_PKG_SRCDIR"]) / "configure"
text = configure.read_text()

if "Linux-android*) :" not in text and "Linux-android*) CCSHARED" not in text:
	if "checking for multiarch" in text and "case $ac_sys_system in" in text:
		text, count = re.subn(
			r"(?m)^([ \t]*)Darwin\*\) :\n",
			lambda match: (
				f'{match.group(1)}Linux-android*) :\n'
				f'{match.group(1)}  MULTIARCH="" ;; #(\n'
				+ match.group(0)
			),
			text,
			count=1,
		)
		if count != 1:
			raise SystemExit("could not locate CPython multiarch configure case")
	else:
		assignment = "MULTIARCH=$($CC --print-multiarch 2>/dev/null)"
		if assignment not in text:
			raise SystemExit("could not locate CPython multiarch assignment")
		text = text.replace(assignment, 'MULTIARCH=""', 1)

text = text.replace("Linux-android*) ;;", 'Linux-android*) CCSHARED="-fPIC";;', 1)
text = re.sub(r'(?m)^\$as_echo "#define HAVE_LINK 1" >>confdefs\.h\n', "", text, count=1)
configure.write_text(text)
PY
}
'''

    configure_patch.unlink()
    return text.rstrip() + "\n" + hook


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
        recipe = ensure_legacy_configure_hook(recipe, path)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    path.write_text(recipe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
