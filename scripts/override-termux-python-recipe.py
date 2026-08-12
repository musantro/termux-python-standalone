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
VERSION_RE_FULL = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


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
	TERMUX_PKG_SRCDIR="$TERMUX_PKG_SRCDIR" python3 - <<'PY'
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


def parse_version(version: str) -> tuple[int, int, int]:
    match = VERSION_RE_FULL.fullmatch(version)
    if not match:
        raise ValueError(f"invalid Python version: {version}")
    return tuple(int(part) for part in match.groups())


def legacy_patch_exceptions(version: str) -> tuple[str, ...]:
    """Return patches that cannot match the specified historical source."""
    parsed = parse_version(version)
    # Python 3.11.4 regenerated configure with a different Autoconf layout,
    # so the hard-link patch has no target. The equivalent cache variable is
    # injected by apply_legacy_recipe_compatibility below.
    if parsed == (3, 11, 4):
        return ("0008-do-not-use-link.patch",)
    return ()


def adapt_xattr_patch(patch: pathlib.Path, version: str) -> None:
    """Adapt Termux's xattr patch to CPython's historical source guards."""
    parsed = parse_version(version)
    if not ((3, 11, 0) <= parsed <= (3, 11, 4)):
        return
    text = patch.read_text()
    if parsed <= (3, 11, 3):
        old = "#if defined(HAVE_SYS_XATTR_H) && defined(__GLIBC__) && !defined(__FreeBSD_kernel__) && !defined(__GNU__)"
    else:
        old = "#if defined(HAVE_SYS_XATTR_H) && defined(__linux__) && !defined(__FreeBSD_kernel__) && !defined(__GNU__)"
    new = f"{old} && !defined(__ANDROID__)"
    current = "#if defined(HAVE_SYS_XATTR_H) && defined(HAVE_LINUX_LIMITS_H) && !defined(__FreeBSD_kernel__) && !defined(__GNU__)"
    if f"-{old}\n+{new}" in text:
        return
    hunk = f"-{current}\n+{current} && !defined(__ANDROID__)"
    if hunk not in text:
        raise ValueError(f"{patch}: unknown CPython xattr guard for Python {version}")
    patch.write_text(text.replace(hunk, f"-{old}\n+{new}", 1))


def ensure_legacy_prefix_include(recipe: pathlib.Path, version: str) -> None:
    """Expose Termux dependency headers to CPython 3.10/3.11 extensions.

    The old ``setup.py`` extension builder does not carry the recipe's
    ``CPPFLAGS`` into its per-module compiler commands.  The modern CPython
    build system does, which is why the same Termux dependency set works for
    3.12 and newer.  Put the Termux prefix include directory in ``CFLAGS``
    for the two historical streams so optional modules such as ``_bz2`` and
    ``_ssl`` see the headers extracted by the builder.  Their old extension
    linker also omits ``libm`` from modules that call ``log``.  Keep the
    library while ``--as-needed`` is active because the old linker command
    places its environment-provided libraries before the object files.
    """
    parsed = parse_version(version)
    if parsed[:2] not in {(3, 10), (3, 11)}:
        return
    text = recipe.read_text()
    marker = '\tCFLAGS="${CFLAGS/-Oz/-O3}"'
    include_flag = 'CFLAGS+=" -I$TERMUX_PREFIX/include"'
    if include_flag in text:
        return
    if marker not in text:
        raise ValueError(f"{recipe}: cannot locate historical CFLAGS hook")
    text = text.replace(
        marker,
        marker
        + "\n\t# CPython <=3.11 does not propagate CPPFLAGS to extension builds.\n"
        + f"\t{include_flag}\n"
        + "\t# Keep math symbols available to extension modules such as _statistics.\n"
        + '\tLDSHARED+=" -Wl,--no-as-needed -lm -Wl,--as-needed"',
        1,
    )
    recipe.write_text(text)


def apply_legacy_recipe_compatibility(recipe: pathlib.Path, version: str) -> None:
    """Adapt historical patches and preserve equivalent configure probes."""
    ensure_legacy_prefix_include(recipe, version)
    xattr_patch = recipe.with_name("0006-do-not-use-xattr.patch")
    if xattr_patch.exists():
        adapt_xattr_patch(xattr_patch, version)
    for filename in legacy_patch_exceptions(version):
        patch = recipe.with_name(filename)
        if patch.exists():
            patch.unlink()
            print(f"Skipping incompatible historical patch {filename} for Python {version}")

    # 0008 disables HAVE_LINK. Its hunk cannot match 3.11.4's regenerated
    # configure, so carry the same result through Autoconf's cache variable.
    if parse_version(version) == (3, 11, 4):
        text = recipe.read_text()
        cache_arg = 'TERMUX_PKG_EXTRA_CONFIGURE_ARGS+=" ac_cv_func_link=no"'
        if cache_arg not in text:
            marker = 'TERMUX_PKG_EXTRA_CONFIGURE_ARGS+=" ac_cv_func_linkat=no"'
            if marker not in text:
                raise ValueError(f"{recipe}: cannot add the link probe override")
            text = text.replace(marker, f"{marker}\n{cache_arg}", 1)
            recipe.write_text(text)


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
    try:
        apply_legacy_recipe_compatibility(path, version)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
