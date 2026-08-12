#!/usr/bin/env python3
"""Add safe handling for CPython fixes already present in upstream sources.

Termux keeps a downstream patch for the Android ``python3.pc`` LIBPYTHON
value. New CPython patch releases can include that change upstream, so the
normal Termux patch loop would otherwise try to apply it twice. This helper
adds a source-aware guard to the recipe's post-source hook, creating that
hook for older recipes that do not define one.
"""

from __future__ import annotations

import pathlib
import re
import sys


GUARD_MARKER = "# termux-python-standalone: skip upstreamed CPython patches"
PRE_CONFIGURE_MARKER = "termux_step_pre_configure() {"
POST_SOURCE_OPEN_RE = re.compile(r"termux_step_post_get_source\(\) \{\n")

GUARD = r'''
	# termux-python-standalone: skip upstreamed CPython patches
	# CPython may include a Termux downstream fix in a later patch release. Only
	# remove a patch when both generated and source configure files contain the
	# exact replacement and neither still contains the old form. A partial or
	# unrelated change is deliberately left for the normal patch step to report.
	for termux_python_patch in "$TERMUX_PKG_BUILDER_DIR"/*.patch; do
		[[ -f "$termux_python_patch" ]] || continue
		if grep -Fq 'LIBPYTHON="$(BLDLIBRARY)"' "$termux_python_patch" &&
			grep -Fq 'LIBPYTHON="-lpython${VERSION}${ABIFLAGS}"' "$termux_python_patch" &&
			grep -Fq 'LIBPYTHON="-lpython${VERSION}${ABIFLAGS}"' "$TERMUX_PKG_SRCDIR/configure" &&
			grep -Fq 'LIBPYTHON="-lpython${VERSION}${ABIFLAGS}"' "$TERMUX_PKG_SRCDIR/configure.ac" &&
			! grep -Fq 'LIBPYTHON="$(BLDLIBRARY)"' "$TERMUX_PKG_SRCDIR/configure" &&
			! grep -Fq 'LIBPYTHON="$(BLDLIBRARY)"' "$TERMUX_PKG_SRCDIR/configure.ac"; then
			echo "Skipping already upstreamed CPython patch: $(basename "$termux_python_patch")"
			rm -f "$termux_python_patch"
		fi
	done
'''


def prepare(path: pathlib.Path) -> bool:
	text = path.read_text()
	if GUARD_MARKER in text:
		return False
	if POST_SOURCE_OPEN_RE.search(text):
		# Keep the guard inside the existing post-source hook. It runs after
		# CPython has been extracted, but before recipe patches are applied.
		text = POST_SOURCE_OPEN_RE.sub(
			lambda match: match.group(0) + GUARD,
			text,
			count=1,
		)
	elif PRE_CONFIGURE_MARKER in text:
		# Older recipes have no post-source hook. Create one before the
		# configure hook, preserving the latter unchanged.
		new_hook = "\ntermux_step_post_get_source() {\n" + GUARD + "\n}\n"
		text = text.replace(PRE_CONFIGURE_MARKER, new_hook + PRE_CONFIGURE_MARKER, 1)
	else:
		raise ValueError(f"{path}: termux_step_pre_configure hook not found")
	path.write_text(text)
	return True


def main() -> int:
	if len(sys.argv) != 2:
		print(f"usage: {sys.argv[0]} RECIPE.sh", file=sys.stderr)
		return 2
	try:
		changed = prepare(pathlib.Path(sys.argv[1]))
	except (OSError, ValueError) as error:
		print(error, file=sys.stderr)
		return 1
	print("Added upstreamed-patch guard" if changed else "Upstreamed-patch guard already present")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
