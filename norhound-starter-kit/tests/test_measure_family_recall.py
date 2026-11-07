"""Family recall must be measured against the official opportunity counts.

The challenge scores Recall/50 as company recall per fact family, measured
against the union of every participant's and Builderr's discoveries. A family
with 577 opportunities is one where 577 of the 1,000 companies have a match
somewhere in that union; our score for the family is the share of those
companies for which we publish at least one fact of that family.

Two things follow, and both are what these tests pin:

* The unit is the published contract envelope, because the envelope is the
  publication surface and its claims carry the family they belong to. The
  same measurement must therefore run on the baseline corpus and on the new
  corpus, or the comparison means nothing.
* The denominators are the official opportunity counts, not the number of
  companies we happened to publish. Measuring against our own coverage turns
  a recall score into a restatement of what we already did.

The baseline for this metric is the clean baseline corpus
(`resume-20261104-final.contract-superset.jsonl` in the dirty main checkout);
the comparison is only valid when both sides are measured by this script.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts import measure_family_recall as fam  # noqa: E402


def _envelope(org: str, families: list[str]) -> dict:
    return {
        "organisation_number": org,
        "claims": [
            {"family": family, "field": f"{family}_field", "value": "x"}
            for family in families
        ],
    }


class OpportunityTests(unittest.TestCase):
    def test_the_official_counts_are_used_for_a_full_batch(self) -> None:
        opportunities = fam.scale_opportunities(1000)
        self.assertEqual(opportunities["website"], 577)
        self.assertEqual(opportunities["hiring"], 84)
        self.assertEqual(opportunities["social"], 177)

    def test_the_counts_scale_to_a_smaller_batch(self) -> None:
        opportunities = fam.scale_opportunities(30)
        self.assertEqual(opportunities["website"], 17)  # round(577 * 30 / 1000)
        self.assertEqual(opportunities["identity"], 30)

    def test_every_family_gets_at_least_one_opportunity(self) -> None:
        for family, count in fam.scale_opportunities(1).items():
            self.assertGreaterEqual(count, 1, family)


class FamilyRecallTests(unittest.TestCase):
    def test_a_company_counts_once_per_family(self) -> None:
        envelopes = [_envelope("111111111", ["website", "website", "website"])]
        covered = fam.covered_companies(envelopes)
        self.assertEqual(covered["website"], {"111111111"})

    def test_a_family_with_nothing_published_scores_zero(self) -> None:
        envelopes = [_envelope("111111111", ["identity"])]
        covered = fam.covered_companies(envelopes)
        self.assertEqual(covered["hiring"], set())

    def test_the_recall_of_a_family_is_covered_over_opportunities(self) -> None:
        opportunities = {"website": 577}
        covered = {"website": {"a" * 1, "b" * 1}}
        report = fam.family_recall(covered, opportunities)
        self.assertAlmostEqual(report["website"]["recall"], 2 / 577)

    def test_reviews_are_reported_but_left_out_of_the_headline(self) -> None:
        self.assertIn("reviews", fam.OFFICIAL_FAMILY_OPPORTUNITIES)
        self.assertNotIn("reviews", fam.SCORED_FAMILIES)

    def test_the_headline_weights_families_by_their_opportunities(self) -> None:
        recalls = {"identity": 1.0, "hiring": 0.0}
        opportunities = {"identity": 1000, "hiring": 84}
        score = fam.opportunity_weighted_mean(recalls, opportunities, ("identity", "hiring"))
        self.assertAlmostEqual(score, 1000 / 1084)

    def test_the_six_groups_cover_every_scored_family(self) -> None:
        grouped = tuple(f for members in fam.SCORED_FAMILY_GROUPS.values() for f in members)
        self.assertEqual(sorted(grouped), sorted(fam.SCORED_FAMILIES))


class ExternalProvenanceTests(unittest.TestCase):
    """Registry facts and external facts must not be counted as the same thing.

    The official opportunity counts are dominated by families every company
    has from the register alone (identity, accounts, people, other, and the
    registry announcements that make up the news floor). Counting those as
    external recall would turn the score into a restatement of what the
    registry already gives us, so every family is measured twice: once over
    all published claims, and once over the claims whose evidence comes from
    a source outside the register.
    """

    def _envelope(self, org: str, claims: list[dict], evidence: list[dict]) -> dict:
        return {"organisation_number": org, "claims": claims, "evidence": evidence}

    def test_a_register_source_is_not_external(self) -> None:
        self.assertTrue(fam.is_registry_source("https://data.brreg.no/enhetsregisteret/api/enheter"))
        self.assertTrue(fam.is_registry_source("https://w2.brreg.no/enhetsregisteret/api/kunngjoringer"))
        self.assertFalse(fam.is_registry_source("https://www.kongsberg.com/"))

    def test_a_company_site_source_is_external(self) -> None:
        envelope = self._envelope(
            "111111111",
            [{"family": "website", "field": "business_description", "value": "x", "evidence_ids": ["ev-1"]}],
            [{"id": "ev-1", "source_url": "https://www.kongsberg.com/"}],
        )
        covered = fam.covered_companies_external([envelope])
        self.assertEqual(covered["website"], {"111111111"})

    def test_a_register_only_claim_is_not_external(self) -> None:
        envelope = self._envelope(
            "111111111",
            [{"family": "identity", "field": "legal_name_live", "value": "x", "evidence_ids": ["ev-1"]}],
            [{"id": "ev-1", "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv"}],
        )
        covered = fam.covered_companies_external([envelope])
        self.assertEqual(covered["identity"], set())

    def test_a_claim_with_both_kinds_of_evidence_counts_as_external(self) -> None:
        envelope = self._envelope(
            "111111111",
            [{"family": "other", "field": "x", "value": "y", "evidence_ids": ["ev-1", "ev-2"]}],
            [
                {"id": "ev-1", "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter"},
                {"id": "ev-2", "source_url": "https://www.fagfolkguiden.no/bedrift/123"},
            ],
        )
        covered = fam.covered_companies_external([envelope])
        self.assertEqual(covered["other"], {"111111111"})

    def test_a_claim_without_evidence_is_not_external(self) -> None:
        envelope = self._envelope(
            "111111111",
            [{"family": "website", "field": "business_description", "value": "x", "evidence_ids": ["ev-missing"]}],
            [],
        )
        covered = fam.covered_companies_external([envelope])
        self.assertEqual(covered["website"], set())

    def test_the_report_separates_external_from_all_claims(self) -> None:
        envelope = self._envelope(
            "111111111",
            [
                {"family": "identity", "field": "legal_name_live", "value": "x", "evidence_ids": ["ev-1"]},
                {"family": "website", "field": "business_description", "value": "x", "evidence_ids": ["ev-2"]},
            ],
            [
                {"id": "ev-1", "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter"},
                {"id": "ev-2", "source_url": "https://www.kongsberg.com/"},
            ],
        )
        report = fam.build_report([envelope], batch_size=1000)
        self.assertEqual(report["family_company_recall"]["identity"]["covered"], 1)
        self.assertEqual(report["external_family_company_recall"]["identity"]["covered"], 0)
        self.assertEqual(report["external_family_company_recall"]["website"]["covered"], 1)
        self.assertIn("scored_external_family_recall_proxy_50", report)
        self.assertIn("scored_external_group_recall_proxy_50", report)


class ReportTests(unittest.TestCase):
    def _report(self, envelopes: list[dict]) -> dict:
        return fam.build_report(envelopes, batch_size=1000)

    def test_the_report_counts_companies_and_families(self) -> None:
        report = self._report([_envelope("111111111", ["identity", "website"])])
        self.assertEqual(report["companies"], 1)
        self.assertEqual(report["batch_size"], 1000)
        self.assertEqual(report["family_company_recall"]["website"]["covered"], 1)
        self.assertEqual(report["family_company_recall"]["website"]["opportunities"], 577)

    def test_the_headline_proxy_is_points_out_of_fifty(self) -> None:
        report = self._report([_envelope("111111111", ["identity"])])
        self.assertGreaterEqual(report["scored_family_recall_proxy_50"], 0.0)
        self.assertLessEqual(report["scored_family_recall_proxy_50"], 50.0)

    def test_the_report_is_byte_identical_for_the_same_input(self) -> None:
        envelopes = [_envelope("111111111", ["identity", "website"])]
        first = json.dumps(self._report(envelopes), ensure_ascii=False, sort_keys=True)
        second = json.dumps(self._report(envelopes), ensure_ascii=False, sort_keys=True)
        self.assertEqual(first, second)

    def test_every_metric_carries_a_definition(self) -> None:
        report = self._report([_envelope("111111111", ["identity"])])
        definitions = report["metric_definitions"]
        for key in (
            "family_company_recall",
            "scored_family_recall_proxy_50",
            "scored_group_recall",
            "opportunities",
        ):
            self.assertIn(key, definitions)

    def test_claims_without_a_family_are_counted_not_published(self) -> None:
        envelopes = [{"organisation_number": "111111111", "claims": [{"field": "x", "value": "y"}]}]
        report = self._report(envelopes)
        self.assertEqual(report["claims_without_family"], 1)
        self.assertEqual(report["family_company_recall"]["identity"]["covered"], 0)

    def test_the_cli_writes_a_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            envelopes_path = Path(tmp) / "envelopes.jsonl"
            output_path = Path(tmp) / "report.json"
            envelopes_path.write_text(
                json.dumps(_envelope("111111111", ["identity", "website"])) + "\n",
                encoding="utf-8",
            )
            fam.main(
                [
                    "--envelopes",
                    str(envelopes_path),
                    "--output",
                    str(output_path),
                ]
            )
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["companies"], 1)


if __name__ == "__main__":
    unittest.main()
