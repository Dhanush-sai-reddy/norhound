"""Tests for the source-rights host policy.

Some hosts cannot be used as evidence: ``proff.no`` now answers every request
with a CloudFront 403, so neither its robots.txt nor its pages can be
re-checked, and the collected rows carried third-party financial values that
are not copied from an official register. Such hosts are excluded from
publication by default; other hosts are unaffected.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.source_rights import (  # noqa: E402
    DEFAULT_EXCLUDED_HOSTS,
    excluded_host_for,
    is_excluded_host,
)


class SourceRightsTests(unittest.TestCase):
    def test_proff_is_excluded_by_default(self) -> None:
        self.assertIn("proff.no", DEFAULT_EXCLUDED_HOSTS)
        self.assertTrue(is_excluded_host("https://www.proff.no/bedrift/996493660"))
        self.assertTrue(is_excluded_host("https://proff.no/bedrift/996493660"))

    def test_other_hosts_are_not_excluded(self) -> None:
        self.assertFalse(is_excluded_host("https://purehelp.no/company/NO/996493660"))
        self.assertFalse(is_excluded_host("https://www.fagfolkguiden.no/bedrift/996493660"))
        self.assertFalse(is_excluded_host("https://data.brreg.no/enhetsregisteret/api/enheter"))

    def test_lookalike_hosts_are_not_excluded(self) -> None:
        self.assertFalse(is_excluded_host("https://proff.no.example.com/bedrift/1"))
        self.assertFalse(is_excluded_host("https://notproff.no/bedrift/1"))
        self.assertFalse(is_excluded_host(""))

    def test_excluded_host_is_reported_for_the_report(self) -> None:
        self.assertEqual(excluded_host_for("https://www.proff.no/x"), "proff.no")
        self.assertEqual(excluded_host_for("https://purehelp.no/x"), "")


if __name__ == "__main__":
    unittest.main()
