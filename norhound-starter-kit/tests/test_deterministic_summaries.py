from __future__ import annotations

import unittest
from scripts.build_deterministic_summaries import summarize_row, validate_summary


def _row(**overrides):
    base = {
        "organisation_number": "810034882",
        "profile": {
            "organisation_number": "810034882",
            "name": "SANDNES ELEKTRISKE AS",
            "industry_label": "Elektrisk installasjonsarbeid",
            "employees": 11,
            "latest_submitted_accounts": "2025",
            "evidence": {
                "financials": {"status": "available", "source_url": "https://example.test/regnskap", "retrieved_at": "2026-09-14T00:00:00Z", "value": {"records": [{"year": "2025", "revenue": 5000000, "annual_result": 250000}]}},
                "roles": {"status": "available", "source_url": "https://example.test/roller", "retrieved_at": "2026-09-14T00:00:00Z", "value": {"roles": [{"role": "DAGL", "name": "Ola Nordmann"}]}},
                "locations": {"status": "available", "source_url": "https://example.test/steder", "retrieved_at": "2026-09-14T00:00:00Z", "value": {"locations": [{"name": "Hovedkontor", "address": "Strandgata 21, SANDNES"}]}},
                "website": {"status": "available", "source_url": "https://example.test/", "retrieved_at": "2026-09-14T00:00:00Z", "value": {"identity_assessment": {"publishable": True}, "social_links": [{"platform": "linkedin", "url": "https://linkedin.com/company/x"}]}},
                "external_observations": [
                    {"signal_type": "job_posting", "platform": "job_board", "source_url": "https://example.test/jobb", "evidence_span": "Elektriker søkes", "acquisition_mode": "official_api"},
                ],
            },
        },
    }
    base["profile"].update(overrides.pop("profile", {}))
    base.update(overrides)
    return base


class DeterministicSummariesTests(unittest.TestCase):
    def test_what_it_does_answered_from_industry(self):
        out = summarize_row(_row())
        answers = {a["question"]: a for a in out["answers"]}
        self.assertIn("what_it_does", answers)
        self.assertTrue(answers["what_it_does"]["answerable"])
        self.assertIn("Elektrisk installasjonsarbeid", answers["what_it_does"]["answer"])
        self.assertTrue(answers["what_it_does"]["evidence_ids"])

    def test_hiring_yes_when_job_posting_present(self):
        out = summarize_row(_row())
        answers = {a["question"]: a for a in out["answers"]}
        self.assertTrue(answers["hiring"]["answerable"])
        self.assertIn("yes", answers["hiring"]["answer"].lower())

    def test_missing_data_says_not_available(self):
        row = _row()
        row["profile"]["evidence"] = {}
        row["profile"]["industry_label"] = None
        out = summarize_row(row)
        answers = {a["question"]: a for a in out["answers"]}
        self.assertFalse(answers["what_it_does"]["answerable"])
        self.assertEqual(answers["what_it_does"]["answer"], "not available")

    def test_same_envelope_gives_identical_summary(self):
        row = _row()
        first = summarize_row(row)
        second = summarize_row(_row())
        self.assertEqual(first, second)

    def test_answers_carry_confirmed_or_inferred_status(self):
        out = summarize_row(_row())
        answers = {a["question"]: a for a in out["answers"]}
        self.assertEqual(answers["what_it_does"]["status"], "confirmed")
        self.assertGreaterEqual(answers["what_it_does"]["confidence"], 0.9)
        self.assertIn(answers["hiring"]["status"], ("confirmed", "inferred"))

    def test_empty_checked_source_is_inferred_not_confirmed(self):
        row = _row()
        row["profile"]["evidence"]["external_observations"] = []
        out = summarize_row(row)
        answers = {a["question"]: a for a in out["answers"]}
        self.assertEqual(answers["hiring"]["status"], "inferred")

    def test_validator_passes_honest_summary(self):
        row = _row()
        self.assertEqual(validate_summary(row, summarize_row(row)), [])

    def test_validator_rejects_dangling_evidence(self):
        row = _row()
        summary = summarize_row(row)
        summary["answers"][0]["evidence_ids"] = ["https://fabricated.test/nowhere"]
        violations = validate_summary(row, summary)
        self.assertTrue(violations)
        self.assertIn("fabricated", violations[0])

    def test_money_uses_human_scale(self):
        out = summarize_row(_row())
        answers = {a["question"]: a for a in out["answers"]}
        self.assertIn("NOK 5.0m", answers["financial_health"]["answer"])
        self.assertIn("NOK 250.0k", answers["financial_health"]["answer"])

    def test_legal_form_expanded_for_readers(self):
        out = summarize_row(_row(profile={"legal_form": "AS"}))
        answers = {a["question"]: a for a in out["answers"]}
        self.assertIn("private limited company", answers["what_it_does"]["answer"])
        self.assertIn("Elektrisk installasjonsarbeid", answers["what_it_does"]["answer"])

    def test_unknowns_listed_with_reasons(self):
        row = _row()
        row["profile"]["evidence"] = {}
        row["profile"]["industry_label"] = None
        row["profile"]["employees"] = None
        out = summarize_row(row)
        fields = {u["field"] for u in out["unknowns"]}
        self.assertIn("official_website", fields)
        self.assertIn("employees", fields)
        self.assertTrue(all(u["reason"] for u in out["unknowns"]))


if __name__ == "__main__":
    unittest.main()
