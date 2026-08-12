#!/usr/bin/env python3
"""Add safe handling for CPython fixes already present in upstream sources.

Termux keeps a downstream patch for the Android ``python3.pc`` LIBPYTHON
value.  New CPython patch releases can include that change upstream, so the
normal Termux patch loop would otherwise try to apply it twice.  This helper
adds a small source-aware guard to the recipe's post-source hook.
"""

from __future__ import annotations

import pathlib
import sys


GUARD_MARKER = "# termux-python-standalone: skip upstreamed CPython patches"
HOOK_MARKER = "\n}\n\ntermux_step_pre_configure() {"

GUARD = r'''
	# termux-python-standalone: skip upstreamed CPython patches
	# CPython may include a Termux downstream fix in a later patch release.  Only
	# remove a patch when both generated and source configure files contain the
	# exact replacement and neither still contains the old form.  A partial or
	# unrelated change is deliberately left for the normal patch step to report.
	for termux_python_patch in "$TERMUX_PKG_BUILDER_DIR"/*.patch; do
		[[ -f "$termux_python_patch" ]] || continue
		if grep -Fq 'LIBPYTHON="\$(BLDLIBRARY)"' "$termux_python_patch" &&
			grep -Fq 'LIBPYTHON="-lpython${VERSION}${ABIFLAGS}"' "$termux_python_patch" &&
			grep -Fq 'LIBPYTHON="-lpython${VERSION}${ABIFLAGS}"' "$TERMUX_PKG_SRCDIR/configure" &&
			grep -Fq 'LIBPYTHON="-lpython${VERSION}${ABIFLAGS}"' "$TERMUX_PKG_SRCDIR/configure.ac" &&
			! grep -Fq 'LIBPYTHON="\$(BLDLIBRARY)"' "$TERMUX_PKG_SRCDIR/configure" &&
			! grep -Fq 'LIBPYTHON="\$(BLDLIBRARY)"' "$TERMUX_PKG_SRCDIR/configure.ac"; then
			echo "Skipping already upstreamed CPython patch: $(basename "$termux_python_patch")"
			rm -f "$termux_python_patch"
		fi
	done
'''


def prepare(path: pathlib.Path) -> bool:
    text = path.read_text()
    if GUARD_MARKER in text:
        return False
    if HOOK_MARKER not in text:
        raise ValueError(f"{path}: termux_step_post_get_source hook not found")
    # Keep the guard inside termux_step_post_get_source.  It must run after
    # CPython has been extracted, but before termux_step_patch_package applies
    # the recipe's patches.
    text = text.replace(HOOK_MARKER, "\n" + GUARD + HOOK_MARKER, 1)
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
