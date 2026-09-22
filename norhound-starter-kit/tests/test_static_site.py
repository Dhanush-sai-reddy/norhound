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


if __name__ == "__main__":
    unittest.main()
