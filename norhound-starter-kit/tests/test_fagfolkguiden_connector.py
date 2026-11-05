from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.run_fagfolkguiden_reviews_connector import (  # noqa: E402
    listing_map_from_sitemap,
    main,
    normalize_legal_name,
    rating_to_label,
    run_connector,
    sitemap_urls_from_robots,
)


ORG = "923609016"
ORG_NAME = "Statkraft"
LISTING_URL = "https://www.fagfolkguiden.no/bedrift/statkraft-as-923609016"
ROBOTS_URL = "https://www.fagfolkguiden.no/robots.txt"
SITEMAP_URL = "https://www.fagfolkguiden.no/sitemaps/0.xml"
ROBOTS_NOTE = "Public /bedrift/ pages allowed; /api/ disallowed and not used"

ROBOTS = b"""User-Agent: *
Allow: /
Disallow: /admin/
Disallow: /api/

Sitemap: https://www.fagfolkguiden.no/sitemaps/0.xml
"""

SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.fagfolkguiden.no/bedrift/statkraft-as-923609016</loc><lastmod>2026-11-04T00:00:00Z</lastmod></url>
</urlset>
"""


def page_bytes(
    *,
    org: str = ORG,
    name: str = "STATKRAFT AS",
    rating: bool = True,
    same_as: tuple[str, ...] = ("https://www.statkraft.no",),
    url: str = LISTING_URL,
) -> bytes:
    node = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "@id": url,
        "name": name,
        "url": url,
        "identifier": {"@type": "PropertyValue", "name": "Organisasjonsnummer", "value": org},
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "Hvollsetterveien",
            "addressLocality": "OSLO",
            "postalCode": "0283",
            "addressCountry": "NO",
        },
        "sameAs": list(same_as),
    }
    if rating:
        node["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": 4.6,
            "bestRating": 5,
            "worstRating": 1,
            "ratingCount": 37,
        }
    payload = json.dumps(node, ensure_ascii=False, separators=(",", ":"))
    html = (
        "<!doctype html><html><head>"
        '<script type="application/ld+json">' + payload + "</script>"
        "</head><body><h1>Bedrift</h1></body></html>"
    )
    return html.encode("utf-8")


class FakeSite:
    """Stand-in for the live site: robots.txt, one sitemap and listing pages."""

    def __init__(self, pages=None, robots: bytes = ROBOTS, sitemaps=None):
        self.pages = dict(pages or {})
        self.robots = robots
        self.sitemaps = dict(sitemaps or {SITEMAP_URL: SITEMAP})
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return self.robots, url
        if url in self.sitemaps:
            return self.sitemaps[url], url
        if url in self.pages:
            return self.pages[url], url
        raise HTTPError(url, 404, "Not Found", None, None)


def profiles_for(*orgs: tuple[str, str]) -> dict[str, dict]:
    return {org: {"organisation_number": org, "name": name} for org, name in orgs}


class SitemapDiscoveryTests(unittest.TestCase):
    def test_sitemap_urls_are_read_from_robots_txt(self):
        self.assertEqual(sitemap_urls_from_robots(ROBOTS.decode("utf-8")), [SITEMAP_URL])

    def test_sitemap_body_maps_organisation_number_to_listing_url(self):
        self.assertEqual(listing_map_from_sitemap(SITEMAP.decode("utf-8")), {ORG: LISTING_URL})

    def test_requested_org_is_fetched_at_the_discovered_listing_url(self):
        site = FakeSite({LISTING_URL: page_bytes()})
        with tempfile.TemporaryDirectory() as directory:
            rows, report = run_connector(
                profiles=profiles_for((ORG, ORG_NAME)),
                wanted=[ORG],
                cache_dir=Path(directory),
                offline=False,
                fetcher=site,
                workers=1,
            )
        self.assertIn(LISTING_URL, site.calls)
        self.assertEqual(report["orgs_with_listing"], 1)
        self.assertEqual(report["orgs_accepted"], 1)
        self.assertEqual(rows[0]["source_url"], LISTING_URL)

    def test_canonical_listing_url_is_used_online_and_offline(self):
        """The same listing yields the same source_url and ids in both modes."""
        empty_sitemap = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b"<url><loc>https://www.fagfolkguiden.no/om-oss</loc></url></urlset>"
        )
        fallback = f"https://www.fagfolkguiden.no/bedrift/{ORG}"
        site = FakeSite({fallback: page_bytes()}, sitemaps={SITEMAP_URL: empty_sitemap})
        with tempfile.TemporaryDirectory() as directory:
            online_rows, _online_report = run_connector(
                profiles=profiles_for((ORG, ORG_NAME)),
                wanted=[ORG],
                cache_dir=Path(directory),
                offline=False,
                fetcher=site,
                workers=1,
            )
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            (cache / f"{ORG}.html").write_bytes(page_bytes())
            offline_rows, _offline_report = run_connector(
                profiles=profiles_for((ORG, ORG_NAME)),
                wanted=[ORG],
                cache_dir=cache,
                offline=True,
                workers=1,
            )
        self.assertTrue(online_rows)
        self.assertTrue(offline_rows)
        self.assertEqual({row["source_url"] for row in online_rows}, {LISTING_URL})
        self.assertEqual([row["id"] for row in online_rows], [row["id"] for row in offline_rows])

    def test_unknown_org_falls_back_to_the_bedrift_path(self):
        empty_sitemap = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b"<url><loc>https://www.fagfolkguiden.no/om-oss</loc></url></urlset>"
        )
        fallback = f"https://www.fagfolkguiden.no/bedrift/{ORG}"
        site = FakeSite({fallback: page_bytes()}, sitemaps={SITEMAP_URL: empty_sitemap})
        with tempfile.TemporaryDirectory() as directory:
            rows, report = run_connector(
                profiles=profiles_for((ORG, ORG_NAME)),
                wanted=[ORG],
                cache_dir=Path(directory),
                offline=False,
                fetcher=site,
                workers=1,
            )
        self.assertIn(fallback, site.calls)
        self.assertEqual(report["orgs_accepted"], 1)
        self.assertTrue(rows)


class LegalNameNormalisationTests(unittest.TestCase):
    def test_every_legal_form_suffix_is_stripped(self):
        forms = (
            "AS", "ASA", "A/S", "ANS", "BA", "DA", "ENK", "KF", "SA", "APS",
            "AB", "OY", "OYJ", "GMBH", "AG", "BV", "NV", "SARL", "SPA", "SRL",
            "CO", "CORP", "PLC", "LP", "LLP", "K/S", "I/S", "SP", "UG", "REG",
            "LIMITED", "LTD", "INC", "LLC", "P/S",
        )
        for form in forms:
            with self.subTest(form=form):
                self.assertEqual(normalize_legal_name(f"Nordic Handel {form}"), "nordic handel")

    def test_only_one_trailing_legal_form_is_stripped(self):
        self.assertEqual(normalize_legal_name("Nordic Handel AS ASA"), "nordic handel as")

    def test_nordic_letters_are_transliterated(self):
        self.assertEqual(normalize_legal_name("Blåbærsyltetøy AS"), "blabaersyltetoy")
        self.assertEqual(normalize_legal_name("Blåbærsyltetøy"), normalize_legal_name("BLABÆRSYLTETØY"))

    def test_statkraft_matches_after_normalisation(self):
        self.assertEqual(normalize_legal_name("STATKRAFT AS"), normalize_legal_name("Statkraft"))


class IdentityGateTests(unittest.TestCase):
    def test_organisation_number_mismatch_emits_no_rows(self):
        site = FakeSite({LISTING_URL: page_bytes(org="999888777")})
        with tempfile.TemporaryDirectory() as directory:
            rows, report = run_connector(
                profiles=profiles_for((ORG, ORG_NAME)),
                wanted=[ORG],
                cache_dir=Path(directory),
                offline=False,
                fetcher=site,
                workers=1,
            )
        self.assertEqual(rows, [])
        self.assertEqual(report["rejected_by_reason"].get("org_number_mismatch"), 1)
        self.assertEqual(report["orgs_accepted"], 0)

    def test_legal_name_mismatch_emits_no_rows(self):
        site = FakeSite({LISTING_URL: page_bytes(name="Helt Annet AS")})
        with tempfile.TemporaryDirectory() as directory:
            rows, report = run_connector(
                profiles=profiles_for((ORG, ORG_NAME)),
                wanted=[ORG],
                cache_dir=Path(directory),
                offline=False,
                fetcher=site,
                workers=1,
            )
        self.assertEqual(rows, [])
        self.assertEqual(report["rejected_by_reason"].get("legal_name_mismatch"), 1)

    def test_legal_name_match_after_normalisation_emits_rows(self):
        site = FakeSite({LISTING_URL: page_bytes(name="STATKRAFT AS")})
        with tempfile.TemporaryDirectory() as directory:
            rows, report = run_connector(
                profiles=profiles_for((ORG, ORG_NAME)),
                wanted=[ORG],
                cache_dir=Path(directory),
                offline=False,
                fetcher=site,
                workers=1,
            )
        self.assertEqual(report["rejected_by_reason"].get("legal_name_mismatch"), None)
        self.assertEqual(report["orgs_accepted"], 1)
        self.assertTrue(rows)
        self.assertTrue(all(row["exact_entity"] for row in rows))

    def test_missing_listing_page_is_reported_as_no_listing(self):
        site = FakeSite({})
        with tempfile.TemporaryDirectory() as directory:
            rows, report = run_connector(
                profiles=profiles_for((ORG, ORG_NAME)),
                wanted=[ORG],
                cache_dir=Path(directory),
                offline=False,
                fetcher=site,
                workers=1,
            )
        self.assertEqual(rows, [])
        self.assertEqual(report["rejected_by_reason"].get("no_listing"), 1)


class RowShapeTests(unittest.TestCase):
    def rows_for(self, **kwargs) -> list[dict]:
        site = FakeSite({LISTING_URL: page_bytes(**kwargs)})
        with tempfile.TemporaryDirectory() as directory:
            rows, _report = run_connector(
                profiles=profiles_for((ORG, ORG_NAME)),
                wanted=[ORG],
                cache_dir=Path(directory),
                offline=False,
                fetcher=site,
                workers=1,
            )
        return rows

    def test_rating_page_emits_review_summary_and_sentiment_rows(self):
        rows = self.rows_for()
        by_signal = {row["signal_type"]: row for row in rows}
        self.assertEqual(set(by_signal), {"profile_metrics", "review_summary", "sentiment"})
        review = by_signal["review_summary"]
        self.assertEqual(review["metrics"]["rating"], 4.6)
        self.assertEqual(review["metrics"]["review_count"], 37)
        self.assertEqual(review["metrics"]["scale"], 5)
        self.assertEqual(review["source_class"], "customer_review")
        self.assertEqual(review["strategy"], "directory_rating_reviews")
        sentiment = by_signal["sentiment"]
        self.assertEqual(sentiment["sentiment_label"], "positive")
        self.assertEqual(sentiment["sentiment_model_version"], "rule-based-v1")
        self.assertEqual(sentiment["strategy"], "directory_review_sentiment")
        self.assertEqual(by_signal["profile_metrics"]["source_class"], "company_directory")
        self.assertEqual(by_signal["profile_metrics"]["strategy"], "directory_profile_metrics")

    def test_sentiment_thresholds_are_deterministic(self):
        self.assertEqual(rating_to_label(4.0), "positive")
        self.assertEqual(rating_to_label(3.5), "neutral")
        self.assertEqual(rating_to_label(2.9), "negative")

    def test_page_without_rating_emits_profile_metrics_row_only(self):
        rows = self.rows_for(rating=False)
        self.assertEqual([row["signal_type"] for row in rows], ["profile_metrics"])
        self.assertNotIn("rating", rows[0]["metrics"])
        self.assertNotIn("review_count", rows[0]["metrics"])

    def test_website_domain_comes_from_same_as(self):
        rows = self.rows_for(same_as=("https://www.statkraft.no",))
        self.assertEqual(rows[0]["metrics"]["website_domain"], "statkraft.no")

    def test_evidence_span_is_the_jsonld_rating_snippet(self):
        rows = self.rows_for()
        review = next(row for row in rows if row["signal_type"] == "review_summary")
        self.assertIn('"aggregateRating"', review["evidence_span"])
        self.assertIn('"ratingValue":4.6', review["evidence_span"])

    def test_identity_proof_lists_both_exact_checks(self):
        rows = self.rows_for()
        proof = {entry["type"]: entry for entry in rows[0]["identity_proof"]}
        self.assertEqual(proof["exact_organisation_number_on_directory_page"]["value"], ORG)
        self.assertEqual(proof["exact_legal_name_on_directory_page"]["value"], "STATKRAFT AS")
        self.assertEqual(proof["exact_legal_name_on_directory_page"]["matched_organisation_number"], ORG)

    def test_ids_are_stable_and_unique_per_org_and_signal(self):
        first = self.rows_for()
        second = self.rows_for()
        self.assertEqual([row["id"] for row in first], [row["id"] for row in second])
        self.assertEqual(len({row["id"] for row in first}), len(first))
        digest = hashlib.sha256(LISTING_URL.encode("utf-8")).hexdigest()[:16]
        ids = {row["signal_type"]: row["id"] for row in first}
        self.assertEqual(ids["profile_metrics"], f"fagfolk-profile-{ORG}-{digest}")
        self.assertEqual(ids["review_summary"], f"fagfolk-review-{ORG}-{digest}")
        self.assertEqual(ids["sentiment"], f"fagfolk-sentiment-{ORG}-{digest}")

    def test_rows_carry_the_rights_and_retrieval_fields(self):
        rows = self.rows_for()
        for row in rows:
            self.assertEqual(row["platform"], "company_directory")
            self.assertEqual(row["acquisition_mode"], "permitted_public_page")
            self.assertEqual(row["rights_status"], "approved")
            self.assertEqual(row["exact_entity"], True)
            self.assertEqual(len(row["content_sha256"]), 64)
            self.assertTrue(row["retrieved_at"])
            self.assertTrue(row["source_url"].startswith("https://www.fagfolkguiden.no/bedrift/"))


class OfflineModeTests(unittest.TestCase):
    def write_cache(self, root: Path, *, sitemaps: bool = True, page: bool = True) -> Path:
        cache = root / "cache"
        (cache / "sitemaps").mkdir(parents=True, exist_ok=True)
        (cache / "robots.txt").write_bytes(ROBOTS)
        if sitemaps:
            (cache / "sitemaps" / "sitemaps-0.xml").write_bytes(SITEMAP)
        if page:
            (cache / f"{ORG}.html").write_bytes(page_bytes())
        return cache

    def run_cli(self, cache: Path, root: Path) -> tuple[list[dict], dict]:
        profiles_path = root / "profiles.jsonl"
        profiles_path.write_text(
            json.dumps({"organisation_number": ORG, "name": ORG_NAME}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        orgs_path = root / "orgs.txt"
        orgs_path.write_text(ORG + "\n", encoding="utf-8")
        output_path = root / "out.jsonl"
        report_path = root / "report.json"
        argv = [
            "run_fagfolkguiden_reviews_connector.py",
            "--profiles", str(profiles_path),
            "--organisations", str(orgs_path),
            "--output", str(output_path),
            "--cache", str(cache),
            "--report", str(report_path),
            "--offline",
        ]
        with patch.object(sys, "argv", argv):
            main()
        rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return rows, report

    def test_offline_mode_makes_no_network_call_and_still_emits_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = self.write_cache(root)
            with patch("urllib.request.urlopen", side_effect=AssertionError("network used in offline mode")):
                rows, report = self.run_cli(cache, root)
        self.assertEqual({row["signal_type"] for row in rows}, {"profile_metrics", "review_summary", "sentiment"})
        self.assertTrue(report["offline"])
        self.assertEqual(report["orgs_accepted"], 1)
        self.assertEqual(report["cache_misses"], {"sitemap": 0, "page": 0})

    def test_offline_mode_reports_sitemap_and_page_cache_misses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = self.write_cache(root, sitemaps=False, page=False)
            with patch("urllib.request.urlopen", side_effect=AssertionError("network used in offline mode")):
                rows, report = self.run_cli(cache, root)
        self.assertEqual(rows, [])
        self.assertEqual(report["cache_misses"], {"sitemap": 1, "page": 1})
        self.assertEqual(report["rejected_by_reason"].get("page_cache_miss"), 1)

    def test_offline_retrieved_at_uses_the_cache_file_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = self.write_cache(root)
            page_path = cache / f"{ORG}.html"
            page_path.touch()
            expected = page_path.stat().st_mtime
            expected_iso = datetime.fromtimestamp(expected, tz=timezone.utc).isoformat().replace("+00:00", "Z")
            with patch("urllib.request.urlopen", side_effect=AssertionError("network used in offline mode")):
                rows, _report = self.run_cli(cache, root)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["retrieved_at"], expected_iso)


class ReportTests(unittest.TestCase):
    def test_report_contains_the_required_keys(self):
        site = FakeSite({LISTING_URL: page_bytes()})
        with tempfile.TemporaryDirectory() as directory:
            _rows, report = run_connector(
                profiles=profiles_for((ORG, ORG_NAME)),
                wanted=[ORG],
                cache_dir=Path(directory),
                offline=False,
                fetcher=site,
                workers=1,
            )
        for key in (
            "orgs_requested",
            "orgs_with_listing",
            "orgs_accepted",
            "rejected_by_reason",
            "orgs_with_rating",
            "observations_by_signal_type",
            "cache_misses",
            "robots_note",
        ):
            self.assertIn(key, report)
        self.assertEqual(report["orgs_requested"], 1)
        self.assertEqual(report["orgs_with_rating"], 1)
        self.assertEqual(report["observations_by_signal_type"], {"profile_metrics": 1, "review_summary": 1, "sentiment": 1})
        self.assertEqual(report["robots_note"], ROBOTS_NOTE)
        self.assertEqual(report["cache_misses"], {"sitemap": 0, "page": 0})


if __name__ == "__main__":
    unittest.main()
