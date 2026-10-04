from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_static_site import build


def _envelope(org="810034882", name="SANDNES ELEKTRISKE AS", industry="Elektrisk installasjonsarbeid"):
    return {
        "organisation_number": org,
        "state": "complete",
        "profile": {
            "organisation_number": org,
            "name": name,
            "industry_label": industry,
            "employees": 11,
            "latest_submitted_accounts": "2025",
            "evidence": {
                "financials": {"status": "available", "source_url": "https://example.test/regnskap", "retrieved_at": "2026-09-14T00:00:00Z", "value": {"records": [{"year": "2025", "revenue": 5000000}]}},
                "website": {"status": "available", "source_url": "https://example.test/", "retrieved_at": "2026-09-14T00:00:00Z", "value": {"identity_assessment": {"publishable": True}, "social_links": []}},
            },
        },
        "changes": [],
        "errors": [],
    }


def _summary(org="810034882"):
    return {
        "organisation_number": org,
        "company_name": "SANDNES ELEKTRISKE AS",
        "synthesis_state": "available",
        "summary": "SANDNES ELEKTRISKE AS operates in Elektrisk installasjonsarbeid.",
        "answers": [{"question": "what_it_does", "answer": "SANDNES ELEKTRISKE AS operates in Elektrisk installasjonsarbeid.", "answerable": True, "evidence_ids": ["https://example.test/"]}],
    }


def _run_tmp(envelopes, summaries=None):
    tmp = Path(tempfile.mkdtemp())
    env_path = tmp / "envelopes.jsonl"
    env_path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in envelopes), encoding="utf-8")
    sum_path = None
    if summaries is not None:
        sum_path = tmp / "summaries.jsonl"
        sum_path.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in summaries), encoding="utf-8")
    out = tmp / "site"
    return build(env_path, sum_path, out), out


class StaticSiteTests(unittest.TestCase):
    def test_index_lists_all_companies(self):
        _, out = _run_tmp([_envelope("810034882"), _envelope("812702432", "RASTAVEGEN 1 AS", "Utleie av fast eiendom")])
        index = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn("810034882", index)
        self.assertIn("812702432", index)
        self.assertIn("SANDNES ELEKTRISKE", index)

    def test_company_page_links_evidence(self):
        _, out = _run_tmp([_envelope()], [_summary()])
        page = (out / "c" / "810034882.html").read_text(encoding="utf-8")
        self.assertIn('href="https://example.test/regnskap"', page)
        self.assertIn("SANDNES ELEKTRISKE AS operates in", page)

    def test_html_is_escaped(self):
        _, out = _run_tmp([_envelope(name="<script>alert(1)</script> AS")])
        page = (out / "c" / "810034882.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_missing_data_renders_not_available(self):
        env = _envelope()
        env["profile"]["evidence"] = {}
        env["profile"]["industry_label"] = None
        _, out = _run_tmp([env])
        page = (out / "c" / "810034882.html").read_text(encoding="utf-8")
        self.assertIn("not available", page)


def _obs(oid="obs-1", signal="contact_email", observed="2026-09-29"):
    return {
        "id": oid,
        "organisation_number": "810034882",
        "platform": "brreg",
        "signal_type": signal,
        "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/810034882",
        "retrieved_at": "2026-09-29T12:00:00Z",
        "observed_at": observed,
        "evidence_span": "post@sandneselektriske.no",
    }


def _envelope_with_obs():
    env = _envelope()
    env["profile"]["evidence"]["external_observations"] = [_obs()]
    return env


class StaticSiteObservationTests(unittest.TestCase):
    def test_observations_render_with_source_and_dates(self):
        _, out = _run_tmp([_envelope_with_obs()])
        page = (out / "c" / "810034882.html").read_text(encoding="utf-8")
        self.assertIn("contact_email", page)
        self.assertIn('href="https://data.brreg.no/enhetsregisteret/api/enheter/810034882"', page)
        self.assertIn("observed 2026-09-29", page)
        self.assertIn("retrieved 2026-09-29", page)

    def test_index_offers_sort_search_platform_filter_and_compare(self):
        _, out = _run_tmp([_envelope_with_obs()])
        index = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn('class=sortable', index)
        self.assertIn('id=q', index)
        self.assertIn('id=pl', index)
        self.assertIn("Compare selected", index)
        self.assertIn('<span class="badge">brreg</span>', index)

    def test_compare_page_is_written(self):
        _, out = _run_tmp([_envelope_with_obs(), _envelope("812702432", "RASTAVEGEN 1 AS", "Utleie av fast eiendom")])
        compare = (out / "compare.html").read_text(encoding="utf-8")
        self.assertIn("Compare companies", compare)
        self.assertIn("810034882", compare)

    def test_labels_prune_unconfirmed_observations(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "envelopes.jsonl").write_text(json.dumps(_envelope_with_obs(), ensure_ascii=False) + "\n", encoding="utf-8")
        (tmp / "labels.jsonl").write_text(json.dumps({"id": "obs-1", "exact_entity": 0}) + "\n", encoding="utf-8")
        out = tmp / "site"
        build(tmp / "envelopes.jsonl", None, out, tmp / "labels.jsonl")
        page = (out / "c" / "810034882.html").read_text(encoding="utf-8")
        self.assertNotIn("contact_email", page)
        self.assertIn("not available", page)

    def test_labels_keep_confirmed_observations(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "envelopes.jsonl").write_text(json.dumps(_envelope_with_obs(), ensure_ascii=False) + "\n", encoding="utf-8")
        (tmp / "labels.jsonl").write_text(json.dumps({"id": "obs-1", "exact_entity": 1}) + "\n", encoding="utf-8")
        out = tmp / "site"
        build(tmp / "envelopes.jsonl", None, out, tmp / "labels.jsonl")
        page = (out / "c" / "810034882.html").read_text(encoding="utf-8")
        self.assertIn("contact_email", page)

    def test_stale_pages_from_an_earlier_batch_are_removed(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "envelopes.jsonl").write_text(json.dumps(_envelope(), ensure_ascii=False) + "\n", encoding="utf-8")
        out = tmp / "site"
        (out / "c").mkdir(parents=True, exist_ok=True)
        (out / "c" / "999999999.html").write_text("stale", encoding="utf-8")
        build(tmp / "envelopes.jsonl", None, out)
        self.assertFalse((out / "c" / "999999999.html").exists())
        self.assertTrue((out / "c" / "810034882.html").exists())

    def test_index_renders_readably_on_a_narrow_screen(self):
        _, out = _run_tmp([_envelope_with_obs()])
        index = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn("overflow-wrap:break-word", index)
        self.assertNotIn("overflow-wrap:anywhere", index)
        self.assertIn("@media (max-width:640px){.tblwrap thead{display:none}", index)
        self.assertIn(".tblwrap td:before{content:attr(data-l);", index)
        self.assertIn(".tblwrap td.pickcell:before{content:none}", index)
        for label in ("Name", "Org. number", "Industry", "Employees", "Revenue", "Hiring", "Platforms"):
            self.assertIn(f'data-l="{label}"', index)
        self.assertIn('rel="icon"', index)


if __name__ == "__main__":
    unittest.main()
