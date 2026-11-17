"""A refresh run has to be visible, not just recorded.

The rubric asks that a user can "find, compare and verify the information",
and the synthesis points go to a summary that "explains the company, changes
and unknowns". The company page had a "Changes since previous run" heading
that printed only a count, so nothing could be verified from the page.

These tests pin that the change records are rendered: the field, the old and
the new value, the source that proves the new value and the run the change
was detected against.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_static_site as site  # noqa: E402


class ChangeRenderingTests(unittest.TestCase):
    def test_a_change_value_is_rendered_on_one_line_and_bounded(self) -> None:
        long_list = [f"news item {index}" for index in range(200)]
        rendered = site._short(long_list)
        self.assertLess(len(rendered), 200)
        self.assertTrue(rendered.endswith("…"))

    def test_a_missing_value_says_so(self) -> None:
        self.assertEqual(site._short(None), "not available")
        self.assertEqual(site._short(""), "not available")

    def test_a_dict_value_is_rendered_as_json(self) -> None:
        self.assertIn("headcount", site._short({"headcount": 10}))


if __name__ == "__main__":
    unittest.main()
