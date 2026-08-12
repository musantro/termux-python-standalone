#!/usr/bin/env python3
"""Regression tests for historical Termux Python recipe compatibility."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/override-termux-python-recipe.py"
SPEC = importlib.util.spec_from_file_location("override_recipe", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LegacyRecipeTests(unittest.TestCase):
    def test_xattr_patch_is_adapted_only_for_old_311(self) -> None:
        self.assertEqual(
            MODULE.legacy_patch_exceptions("3.11.0"),
            (),
        )
        self.assertEqual(MODULE.legacy_patch_exceptions("3.11.4"), ("0008-do-not-use-link.patch",))
        self.assertEqual(MODULE.legacy_patch_exceptions("3.11.5"), ())
        self.assertEqual(MODULE.legacy_patch_exceptions("3.12.0"), ())

    def test_3114_link_probe_replacement_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "build.sh"
            recipe.write_text(
                'TERMUX_PKG_EXTRA_CONFIGURE_ARGS+=" ac_cv_func_linkat=no"\n'
                'termux_step_pre_configure() {\n'
                '\tCFLAGS="${CFLAGS/-Oz/-O3}"\n'
                '}\n'
            )
            (recipe.parent / "0008-do-not-use-link.patch").touch()
            MODULE.apply_legacy_recipe_compatibility(recipe, "3.11.4")
            MODULE.apply_legacy_recipe_compatibility(recipe, "3.11.4")
            text = recipe.read_text()
            self.assertEqual(text.count("ac_cv_func_link=no"), 1)
            self.assertFalse((recipe.parent / "0008-do-not-use-link.patch").exists())

    def test_historical_xattr_patch_gets_matching_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            patch = Path(directory) / "0006-do-not-use-xattr.patch"
            current = (
                "#if defined(HAVE_SYS_XATTR_H) && defined(HAVE_LINUX_LIMITS_H) && "
                "!defined(__FreeBSD_kernel__) && !defined(__GNU__)"
            )
            patch.write_text(f"-{current}\n+{current} && !defined(__ANDROID__)\n")
            MODULE.adapt_xattr_patch(patch, "3.11.0")
            text = patch.read_text()
            self.assertIn("defined(__GLIBC__)", text)
            self.assertIn("!defined(__ANDROID__)", text)
            MODULE.adapt_xattr_patch(patch, "3.11.0")
            self.assertEqual(patch.read_text(), text)

            patch.write_text(f"-{current}\n+{current} && !defined(__ANDROID__)\n")
            MODULE.adapt_xattr_patch(patch, "3.11.4")
            self.assertIn("defined(__linux__)", patch.read_text())

    def test_legacy_recipes_forward_termux_include_path_to_extensions(self) -> None:
        for version in ("3.10.20", "3.11.15"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                recipe = Path(directory) / "build.sh"
                recipe.write_text(
                    'termux_step_pre_configure() {\n'
                    '\tCFLAGS="${CFLAGS/-Oz/-O3}"\n'
                    '}\n'
                )
                MODULE.ensure_legacy_prefix_include(recipe, version)
                MODULE.ensure_legacy_prefix_include(recipe, version)
                text = recipe.read_text()
                self.assertEqual(text.count('CFLAGS+=" -I$TERMUX_PREFIX/include"'), 1)
                self.assertEqual(
                    text.count('LDSHARED+=" -Wl,--no-as-needed -lm -Wl,--as-needed"'),
                    1,
                )

    def test_modern_recipes_keep_their_existing_include_handling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "build.sh"
            recipe.write_text(
                'termux_step_pre_configure() {\n'
                '\tCFLAGS="${CFLAGS/-Oz/-O3}"\n'
                '}\n'
            )
            MODULE.ensure_legacy_prefix_include(recipe, "3.12.13")
            self.assertNotIn("TERMUX_PREFIX/include", recipe.read_text())


if __name__ == "__main__":
    unittest.main()
