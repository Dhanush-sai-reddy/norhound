"""Regression tests for the contract envelope emitter.

The emitter turns frozen profiles plus gated observations into the official
claims/evidence envelope.  These tests pin the behaviour that decides score:
pool-key normalisation, the dated-news requirement, role-title trust, claim
de-duplication, and the invariant that no available claim is cited without
evidence.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("emit_contract_envelope",
                                              ROOT / "scripts" / "emit_contract_envelope.py")
emit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(emit)


def profile_with(evidence: dict) -> dict:
    return {"organisation_number": "912345678", "name": "TEST AS", "evidence": evidence}


def registry_profile() -> dict:
    return profile_with({
        "registry": {
            "status": "available",
            "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/912345678",
            "source_class": "official_registry",
            "content_sha256": "a" * 64,
            "retrieved_at": "2026-10-01T00:00:00Z",
            "value": {"organisasjonsnummer": "912345678", "navn": "TEST AS",
                      "hjemmeside": "https://www.Test.No/",
                      "forretningsadresse": {"adresse": ["GATA 1"], "postnummer": "0150",
                                             "poststed": ["OSLO"]}},
        },
        "roles": {"status": "available", "source_url": "https://data.brreg.no/roles",
                  "content_sha256": "b" * 64,
                  "value": {"roles": [{"name": "OLA NORDMANN", "role": "Daglig leder",
                                       "group": "N1"},
                                      {"name": "KARI SVART", "role": "Styremedlem",
                                       "group": "A"}]}},
        "financials": {"status": "not_found", "note": "no accounts filed"},
    })


def obs(**kw) -> dict:
    base = {"id": kw.get("id", "o1"), "organisation_number": "912345678",
            "exact_entity": True, "source_url": "https://test.no/x",
            "source_class": "company_site", "platform": "company_site",
            "strategy": "permitted_public_page", "retrieved_at": "2026-10-01T00:00:00Z",
            "content_sha256": "c" * 64, "evidence_span": "span text"}
    base.update(kw)
    return base


class PoolKeyNormalisationTests(unittest.TestCase):
    def test_url_key_matches_the_shape_the_pool_uses(self):
        for raw in ("https://www.Test.No/Jobb/?utm=1", "test.no/jobb/", "TEST.NO"):
            self.assertEqual(emit.url_key(raw).split("?")[0].rstrip("/"),
                             emit.url_key(raw), msg=raw)
        self.assertEqual(emit.url_key("https://WWW.Test.no/jobb/"), "test.no/jobb")

    def test_domain_key_drops_scheme_and_www(self):
        self.assertEqual(emit.domain_key("https://www.elprint.no/"), "elprint.no")
        self.assertEqual(emit.domain_key("elprint.no"), "elprint.no")

    def test_text_key_collapses_whitespace_and_unescapes_entities(self):
        self.assertEqual(emit.text_key("  Ny   plattform &#8211; for&nbsp;deg  "),
                         "Ny plattform – for deg")

    def test_html_entities_never_survive_into_a_claim(self):
        self.assertNotIn("&#", emit.text_key("A &#8211; B"))


class EvidenceBookTests(unittest.TestCase):
    def test_identical_sources_are_deduplicated_to_one_record(self):
        book = emit.EvidenceBook()
        ids = {book.add(source_url="https://test.no/a", source_class="company_site",
                        content_sha256="x", claim_span="same", retrieved_at="t")
               for _ in range(4)}
        self.assertEqual(len(ids), 1)
        self.assertEqual(len(book.records), 1)

    def test_ids_are_unique_across_differing_evidence(self):
        book = emit.EvidenceBook()
        for i in range(50):
            book.add(source_url=f"https://test.no/{i}", source_class="company_site",
                     content_sha256=f"digest-{i}", claim_span="s", retrieved_at="t")
        ids = [r["id"] for r in book.records]
        self.assertEqual(len(ids), len(set(ids)))


class DatedNewsTests(unittest.TestCase):
    def test_undated_mention_is_not_published_as_dated_news(self):
        claims = emit.external_claims(
            [obs(signal_type="public_post", metrics={"title": "Nyhetsinnlegg"})],
            emit.EvidenceBook())
        fields = {c["field"] for c in claims}
        self.assertIn("public_mention", fields)
        self.assertNotIn("dated_news", fields)

    def test_offset_is_preserved_verbatim_in_the_pool_value(self):
        claims = emit.external_claims(
            [obs(signal_type="public_post",
                 metrics={"title": "Bedre sosial funksjon",
                          "published_at": "2025-09-22T20:00:00+02:00",
                          "claim_value": "Bedre sosial funksjon (2025-09-22T20:00:00+02:00)"})],
            emit.EvidenceBook())
        news = [c for c in claims if c["field"] == "dated_news"]
        self.assertEqual(len(news), 1)
        self.assertEqual(news[0]["value"], "Bedre sosial funksjon (2025-09-22T20:00:00+02:00)")
        self.assertEqual(news[0]["family"], "news")
        self.assertNotIn("T00:00:00", news[0]["value"])

    def test_date_only_source_is_not_widened_to_midnight(self):
        claims = emit.external_claims(
            [obs(signal_type="public_post", metrics={"title": "Lansering",
                                                     "published_at": "2026-10-13"})],
            emit.EvidenceBook())
        news = [c for c in claims if c["field"] == "dated_news"]
        self.assertEqual(news[0]["value"], "Lansering (2026-10-13)")

    def test_dated_news_is_capped_per_company(self):
        rows = [obs(id=f"n{i}", signal_type="public_post",
                    source_url=f"https://test.no/news/{i}", content_sha256=f"{i}",
                    metrics={"title": f"Nyhet {i}", "published_at": "2026-01-01"})
                for i in range(60)]
        claims = emit.external_claims(rows, emit.EvidenceBook())
        self.assertEqual(sum(1 for c in claims if c["field"] == "dated_news"), 20)


class HiringTrustTests(unittest.TestCase):
    def test_role_titles_come_only_from_job_sources(self):
        nav_junk = obs(id="j1", signal_type="job_posting", strategy="site_nav_scan",
                       source_url="https://elprint.no/kontakt-oss",
                       metrics={"job_title": "Digitalt testament"})
        fields = {c["field"] for c in emit.external_claims([nav_junk], emit.EvidenceBook())}
        self.assertNotIn("job_postings", fields)
        self.assertNotIn("job_title", fields)

    def test_official_feed_publishes_role_and_attributes(self):
        row = obs(id="j2", signal_type="job_posting", strategy="official_nav_job_feed_orgnr_match",
                  source_class="official_api", platform="nav",
                  source_url="https://nav.no/job/c/123",
                  signal={"title": "Snekker", "employer_name": "TEST AS",
                          "city_municipal": "OSLO", "engagement_type": "FAST",
                          "published": "2026-09-30T08:00:00+02:00"})
        claims = emit.external_claims([row], emit.EvidenceBook())
        by_field = {c["field"]: c for c in claims}
        self.assertIn("Snekker", by_field["job_title"]["value"])
        self.assertEqual(by_field["job_postings"]["value"], "nav.no/job/c/123")
        self.assertEqual(by_field["job_employer"]["value"], "TEST AS")
        self.assertEqual(by_field["job_location"]["value"], "OSLO")

    def test_navigation_labels_are_rejected_as_roles(self):
        for junk in ("Logg inn", "Les mer", "Personvern", "Alle ledige", ""):
            self.assertFalse(emit._plausible_role(junk), msg=junk)
        self.assertTrue(emit._plausible_role("Sanitærmontør"))

    def test_careers_page_url_is_itself_a_hiring_fact(self):
        row = obs(id="c1", signal_type="careers_page",
                  source_url="https://test.no/jobb", metrics={"careers_url": "https://test.no/jobb"})
        claims = emit.external_claims([row], emit.EvidenceBook())
        by_field = {c["field"]: c for c in claims}
        self.assertEqual(by_field["hiring_signal"]["value"], "test.no/jobb")
        self.assertEqual(by_field["hiring_signal"]["family"], "hiring")
        self.assertEqual(by_field["careers_page"]["value"], "https://test.no/jobb")

    def test_careers_like_job_url_earns_hiring_signal_without_a_role(self):
        row = obs(id="c2", signal_type="job_posting", strategy="site_nav_scan",
                  source_url="https://test.no/ledige-stillinger",
                  metrics={"job_title": "Om oss"})
        claims = emit.external_claims([row], emit.EvidenceBook())
        fields = {c["field"] for c in claims}
        self.assertIn("hiring_signal", fields)
        self.assertNotIn("job_title", fields)


class SocialTests(unittest.TestCase):
    def test_profile_handle_becomes_a_host_plus_path_social_fact(self):
        row = obs(id="s1", signal_type="profile_handle", platform="linkedin",
                  source_url="https://test.no",
                  metrics={"handle": "https://www.LinkedIn.com/Company/Test-AS/",
                           "url": "https://www.LinkedIn.com/Company/Test-AS/"})
        claims = emit.external_claims([row], emit.EvidenceBook())
        social = [c for c in claims if c["field"] == "social_profiles"]
        self.assertEqual(social[0]["value"], "linkedin.com/company/test-as")
        self.assertEqual(social[0]["family"], "social")


class EnvelopeIntegrityTests(unittest.TestCase):
    def build(self, observations=None, **kw):
        return emit.build_envelope(registry_profile(), observations or [], started_at="t", **kw)

    def test_every_available_claim_cites_existing_evidence(self):
        envelope = self.build([obs(signal_type="public_post",
                                   metrics={"title": "Nyhet", "published_at": "2026-01-02"})])
        evidence_ids = {e["id"] for e in envelope["evidence"]}
        self.assertTrue(evidence_ids)
        for claim in envelope["claims"]:
            if claim["availability"] == "available":
                self.assertTrue(claim["evidence_ids"], msg=claim["field"])
                self.assertTrue(set(claim["evidence_ids"]) <= evidence_ids, msg=claim["field"])

    def test_duplicate_identical_claims_are_collapsed(self):
        rows = [obs(id=f"r{i}", signal_type="review_summary",
                    source_url=f"https://fagfolkguiden.no/{i}", content_sha256=str(i),
                    metrics={"rating": 1.0, "review_count": 3}) for i in range(4)]
        envelope = self.build(rows)
        ratings = [c for c in envelope["claims"] if c["field"] == "average_rating"]
        self.assertEqual(len(ratings), 1)

    def test_non_available_availability_states_are_the_contracted_ones(self):
        allowed = {"available", "not_available", "blocked", "not_applicable", "ambiguous", "failed"}
        envelope = self.build()
        for claim in envelope["claims"]:
            self.assertIn(claim["availability"], allowed)
        self.assertIn("registry_financials", {c["field"] for c in envelope["claims"]})

    def test_registry_scalars_flags_and_roles_are_emitted(self):
        envelope = self.build()
        by_field = {c["field"]: c for c in envelope["claims"]}
        self.assertEqual(by_field["official_website"]["value"], "test.no")
        self.assertEqual(by_field["legal_name"]["value"], "TEST AS")
        holders = [c["value"] for c in envelope["claims"] if c["field"] == "role_holder"]
        self.assertEqual(sorted(holders), ["KARI SVART", "OLA NORDMANN"])
        self.assertEqual(by_field["role_count"]["value"], 2)
        self.assertEqual(len(envelope["claims"]), len({(c["field"], json.dumps(c["value"], sort_keys=True))
                                                      for c in envelope["claims"]}))

    def test_wrong_entity_observations_are_never_claimed(self):
        rows = [obs(signal_type="public_post", exact_entity=False,
                    metrics={"title": "Nyhet", "published_at": "2026-01-02"})]
        envelope = self.build(rows)
        self.assertFalse([c for c in envelope["claims"] if c["field"] in ("dated_news", "public_mention")])

    def test_envelope_carries_required_top_level_sections(self):
        envelope = self.build()
        for key in ("organisation_number", "run", "claims", "evidence", "changes", "errors", "operations"):
            self.assertIn(key, envelope)
        self.assertEqual(envelope["run"]["terminal_status"], "completed")
        self.assertEqual(envelope["operations"]["claims"], len(envelope["claims"]))


class SnapshotTests(unittest.TestCase):
    def test_snapshots_are_only_written_when_bytes_were_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = obs(signal_type="public_post", metrics={"title": "Nyhet",
                                                          "published_at": "2026-01-02"})
            envelope = emit.build_envelope(registry_profile(), [row], started_at="t",
                                           snapshot_root=root)
            self.assertEqual([e for e in envelope["evidence"] if "snapshot_path" in e], [])
            self.assertFalse(list(root.rglob("*.gz")))

    def test_retained_body_is_gzipped_and_digest_matches_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = obs(signal_type="website_description",
                      metrics={"description": "Vi leverer", "body_excerpt": "Vi leverer kraft."})
            envelope = emit.build_envelope(registry_profile(), [row], started_at="t",
                                           snapshot_root=root)
            staged = [e for e in envelope["evidence"] if "snapshot_path" in e]
            self.assertTrue(staged)
            for evidence in staged:
                path = root / evidence["snapshot_path"]
                self.assertTrue(path.is_file())
                self.assertEqual(evidence["content_sha256"],
                                 hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest())
                self.assertIn("Vi leverer kraft.", gzip.decompress(path.read_bytes()).decode())

    def test_span_fallback_is_off_by_default_and_honest_when_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = obs(signal_type="public_post", metrics={"title": "Nyhet",
                                                          "published_at": "2026-01-02"})
            off = emit.build_envelope(registry_profile(), [row], started_at="t", snapshot_root=root)
            self.assertFalse([e for e in off["evidence"] if "snapshot_path" in e])

            on = emit.build_envelope(registry_profile(), [row], started_at="t",
                                     snapshot_root=root, span_fallback=True)
            staged = [e for e in on["evidence"] if "snapshot_path" in e]
            self.assertTrue(staged)
            for evidence in staged:
                raw = gzip.decompress((root / evidence["snapshot_path"]).read_bytes())
                self.assertEqual(evidence["content_sha256"], hashlib.sha256(raw).hexdigest())


class CliTests(unittest.TestCase):
    def test_end_to_end_write_is_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / "profiles.jsonl"
            observations = Path(tmp) / "external.jsonl"
            output = Path(tmp) / "contract.jsonl"
            profiles.write_text(json.dumps(registry_profile()) + "\n", encoding="utf-8")
            observations.write_text(json.dumps(obs(
                signal_type="public_post",
                metrics={"title": "Nyhet", "published_at": "2026-01-02",
                         "claim_value": "Nyhet (2026-01-02)"})) + "\n", encoding="utf-8")
            import subprocess
            import sys
            subprocess.run([sys.executable, str(ROOT / "scripts" / "emit_contract_envelope.py"),
                            "--profiles", str(profiles), "--observations", str(observations),
                            "--output", str(output)], check=True, capture_output=True)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual(len(rows), 1)
            fields = {c["field"] for c in rows[0]["claims"]}
            self.assertIn("dated_news", fields)


if __name__ == "__main__":
    unittest.main()
