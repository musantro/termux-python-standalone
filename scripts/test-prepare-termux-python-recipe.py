#!/usr/bin/env python3
"""Unit checks for the upstreamed-patch recipe preparation helper."""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).with_name("prepare-termux-python-recipe.py")
SPEC = importlib.util.spec_from_file_location("prepare_recipe", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


RECIPE = """termux_step_post_get_source() {
\ttrue
}

termux_step_pre_configure() {
\ttrue
}
"""

RECIPE_WITHOUT_POST_SOURCE = """termux_step_pre_configure() {
\ttrue
}
"""

RECIPE_WITH_LATE_POST_SOURCE = """termux_step_pre_configure() {
\ttrue
}

termux_step_post_get_source() {
\ttrue
}
"""


class PrepareRecipeTests(unittest.TestCase):
    def test_guard_covers_both_upstreamed_transformations(self) -> None:
        self.assertIn(r'LIBPYTHON="\$(BLDLIBRARY)"', MODULE.GUARD)
        self.assertIn(r'\$(MODULE_LDFLAGS_SHARED)', MODULE.GUARD)
        self.assertIn(r'MODULE_LDFLAGS_SHARED=$(if $(LIBPYTHON),$(BLDLIBRARY))', MODULE.GUARD)
        self.assertIn("termux_python_staged_builder_dir", MODULE.GUARD)
        self.assertIn("cp -a", MODULE.GUARD)

    def test_inserts_guard_in_post_source_hook_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "build.sh"
            path.write_text(RECIPE)

            self.assertTrue(MODULE.prepare(path))
            prepared = path.read_text()
            self.assertIn(MODULE.GUARD_MARKER, prepared)
            self.assertLess(
                prepared.index(MODULE.GUARD_MARKER),
                prepared.index("termux_step_pre_configure()"),
            )
            self.assertFalse(MODULE.prepare(path))
            self.assertEqual(prepared, path.read_text())

    def test_rejects_recipe_without_post_source_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "build.sh"
            path.write_text(RECIPE_WITHOUT_POST_SOURCE)
            self.assertTrue(MODULE.prepare(path))
            prepared = path.read_text()
            self.assertIn("termux_step_post_get_source() {", prepared)
            self.assertIn(MODULE.GUARD_MARKER, prepared)
            self.assertIn("termux_step_pre_configure() {\n\ttrue", prepared)

    def test_uses_late_post_source_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "build.sh"
            path.write_text(RECIPE_WITH_LATE_POST_SOURCE)
            self.assertTrue(MODULE.prepare(path))
            prepared = path.read_text()
            self.assertEqual(prepared.count(MODULE.GUARD_MARKER), 1)
            self.assertLess(
                prepared.index(MODULE.GUARD_MARKER),
                prepared.index("\n\ttrue\n}", prepared.index("termux_step_post_get_source")),
            )

    def test_rejects_recipe_without_configure_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "build.sh"
            path.write_text("TERMUX_PKG_VERSION=\"3.13.15\"\n")
            with self.assertRaises(ValueError):
                MODULE.prepare(path)


if __name__ == "__main__":
    unittest.main()
