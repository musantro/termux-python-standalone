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


class PrepareRecipeTests(unittest.TestCase):
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
            path.write_text("TERMUX_PKG_VERSION=\"3.13.15\"\n")
            with self.assertRaises(ValueError):
                MODULE.prepare(path)


if __name__ == "__main__":
    unittest.main()
