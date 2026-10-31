"""The pool matches dated-news facts by string, so the published timestamp must be
the one the source printed — not a UTC-normalised or date-truncated paraphrase."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.news_datetime import publication_timestamp  # noqa: E402

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


class PublicationTimestampTests(unittest.TestCase):
    def test_local_offset_is_kept_verbatim(self):
        # the organiser's reference value is exactly this shape
        self.assertEqual(publication_timestamp("2025-09-22T20:00:00+02:00", now=NOW), "2025-09-22T20:00:00+02:00")
        self.assertEqual(publication_timestamp("2026-01-15T08:30:00+01:00", now=NOW), "2026-01-15T08:30:00+01:00")

    def test_offset_is_never_moved_to_utc(self):
        self.assertNotEqual(publication_timestamp("2025-09-22T20:00:00+02:00", now=NOW), "2025-09-22T18:00:00+00:00")

    def test_zulu_designator_is_not_rewritten(self):
        self.assertEqual(publication_timestamp("2026-08-14T10:00:00Z", now=NOW), "2026-08-14T10:00:00Z")
        self.assertEqual(publication_timestamp("2026-08-14T10:00:00+00:00", now=NOW), "2026-08-14T10:00:00+00:00")

    def test_rfc822_from_feed_keeps_the_feed_offset(self):
        self.assertEqual(publication_timestamp("Wed, 22 Oct 2025 08:15:00 +0200", now=NOW), "2025-10-22T08:15:00+02:00")

    def test_naive_timestamp_gets_no_invented_offset(self):
        self.assertEqual(publication_timestamp("2026-03-01T09:00:00", now=NOW), "2026-03-01T09:00:00")

    def test_date_only_source_stays_date_only(self):
        # inventing midnight would claim precision the source never offered
        self.assertEqual(publication_timestamp("2026-04-09", now=NOW), "2026-04-09")

    def test_implausible_dates_are_refused(self):
        self.assertIsNone(publication_timestamp("1999-12-31T23:00:00+01:00", now=NOW))
        self.assertIsNone(publication_timestamp("2027-01-01T00:00:00+01:00", now=NOW))
        self.assertIsNone(publication_timestamp("i går", now=NOW))
        self.assertIsNone(publication_timestamp(None, now=NOW))
        self.assertIsNone(publication_timestamp("", now=NOW))

    def test_weird_separators_and_fractional_seconds_parse(self):
        self.assertEqual(publication_timestamp("2026-03-01 09:00:00", now=NOW), "2026-03-01T09:00:00")
        self.assertEqual(publication_timestamp("2026-03-01T09:00:00.500000+01:00", now=NOW), "2026-03-01T09:00:00.500000+01:00")


class ConnectorDelegationTests(unittest.TestCase):
    """Every news connector must go through the one implementation, not its own copy."""

    def test_all_extractors_preserve_the_source_offset(self):
        import importlib.util

        samples = ("2025-09-22T20:00:00+02:00", "Wed, 22 Oct 2025 08:15:00 +0200")
        for name, module_path, function in (
            ("article_dates", ROOT / "scripts" / "extract_company_article_dates.py", "parse_date"),
            ("feed_news", ROOT / "scripts" / "extract_company_feed_news.py", "parse_date"),
            ("norwegian_rss", ROOT / "scripts" / "run_norwegian_news_rss_connector.py", "parse_date"),
            ("norwegian_rss_822", ROOT / "scripts" / "run_norwegian_news_rss_connector.py", "parse_rfc822_date"),
            ("related_sites", ROOT / "scripts" / "extract_related_site_signals.py", "parse_date"),
        ):
            spec = importlib.util.spec_from_file_location(f"norhound_{name}", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for sample in samples:
                with self.subTest(connector=name, sample=sample):
                    value = getattr(module, function)(sample)
                    self.assertIsNotNone(value)
                    self.assertIn("+02:00", value, f"{name} widened the published offset")


if __name__ == "__main__":
    unittest.main()
