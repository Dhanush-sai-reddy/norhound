"""Tests for the NAV job-feed index: parent resolution and the collapse guard.

Two failures are pinned here, both observed in a real run on 16 Nov 2026:

* the feed can list a **legal entity** where the old code assumed a brreg
  sub-unit. Every number then 404s on `/underenheter/`, the resolver returns
  nothing, and the whole index is dropped. A legal entity must resolve to
  itself.
* `resolve_index` used to overwrite the index unconditionally, so that failure
  destroyed a 5,776-posting index that had taken 24 minutes to build. A pass
  that keeps fewer than half the employers must refuse to write and leave the
  raw index in place.

The happy path still has to work: a sub-unit resolves to its `overordnetEnhet`
and the rewritten index is keyed by that parent.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts import run_nav_job_feed_connector as nav  # noqa: E402


def raw_index(employers: list[str]) -> list[dict]:
    return [
        {
            "organisation_number": org,
            "postings": [
                {
                    "posting_id": f"p-{org}",
                    "employer_orgnr": org,
                    "title": "Servitør",
                }
            ],
        }
        for org in employers
    ]


class ParentResolutionTests(unittest.TestCase):
    def test_subunit_resolves_to_its_parent_entity(self) -> None:
        with mock.patch.object(nav, "_brreg_get", side_effect=[{"overordnetEnhet": "811598992"}, None]):
            self.assertEqual(nav._parent_enhet("971686294"), "811598992")

    def test_legal_entity_is_its_own_parent(self) -> None:
        with mock.patch.object(nav, "_brreg_get", side_effect=[None, {"organisasjonsnummer": "974760673"}]):
            self.assertEqual(nav._parent_enhet("974760673"), "974760673")

    def test_unknown_number_resolves_to_nothing(self) -> None:
        with mock.patch.object(nav, "_brreg_get", return_value=None):
            self.assertIsNone(nav._parent_enhet("999999999"))

    def test_non_numeric_number_is_not_queried(self) -> None:
        with mock.patch.object(nav, "_brreg_get") as get:
            self.assertIsNone(nav._parent_enhet("not-a-number"))
        get.assert_not_called()

    def test_transient_errors_are_retried_then_answered(self) -> None:
        """A 429 burst must not be read as "this org number does not exist"."""
        import urllib.error

        calls: list[str] = []

        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        def fake_urlopen(request, timeout=None):  # noqa: ANN001
            calls.append(request.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
            return FakeResponse(json.dumps({"overordnetEnhet": "811598992"}).encode())

        with mock.patch.object(nav.urllib.request, "urlopen", side_effect=fake_urlopen):
            with mock.patch.object(nav.time, "sleep", return_value=None):
                self.assertEqual(nav._brreg_get("https://example.test/underenheter/971686294"), {"overordnetEnhet": "811598992"})
        self.assertEqual(len(calls), 2)


class ResolveIndexGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.index = self.root / "nav-job-index.jsonl"
        self.report = self.root / "nav-index-resolve-report.json"

    def write_raw(self, employers: list[str]) -> bytes:
        payload = "".join(json.dumps(row) + "\n" for row in raw_index(employers)).encode()
        self.index.write_bytes(payload)
        return payload

    def test_collapse_refuses_to_write_and_keeps_the_raw_index(self) -> None:
        original = self.write_raw(["971686294", "998966507"])
        with mock.patch.object(nav, "_parent_enhet", return_value=None):
            with self.assertRaises(SystemExit) as caught:
                nav.resolve_index(self.index, self.report, workers=2)
        self.assertIn("refusing to rewrite", str(caught.exception))
        self.assertEqual(self.index.read_bytes(), original)
        self.assertFalse(self.report.exists())

    def test_successful_resolution_rewrites_index_keyed_by_parent(self) -> None:
        self.write_raw(["971686294", "998966507"])
        parents = {"971686294": "811598992", "998966507": "812160842"}
        with mock.patch.object(nav, "_parent_enhet", side_effect=lambda org: parents.get(org)):
            nav.resolve_index(self.index, self.report, workers=2)
        rows = [json.loads(line) for line in self.index.read_text().splitlines() if line.strip()]
        self.assertEqual([row["organisation_number"] for row in rows], ["811598992", "812160842"])
        posting = rows[0]["postings"][0]
        self.assertEqual(posting["employer_orgnr"], "971686294")
        self.assertEqual(posting["employer_parent_orgnr"], "811598992")
        report = json.loads(self.report.read_text())
        self.assertEqual(report["parent_resolution_succeeded"], 2)
        self.assertEqual(report["postings_dropped_unresolved_parent"], 0)

    def test_partial_collapse_retries_before_refusing(self) -> None:
        """Half the employers failing once is retried, not written off."""
        employers = ["971686294", "998966507"]
        self.write_raw(employers)
        attempts: list[str] = []

        def flaky(org: str):
            attempts.append(org)
            # First pass fails for both; the low-concurrency retry succeeds.
            if attempts.count(org) == 1:
                return None
            return {"971686294": "811598992", "998966507": "812160842"}[org]

        with mock.patch.object(nav, "_parent_enhet", side_effect=flaky):
            nav.resolve_index(self.index, self.report, workers=2)
        rows = [json.loads(line) for line in self.index.read_text().splitlines() if line.strip()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(attempts), sorted(employers * 2))

    def test_empty_index_is_refused(self) -> None:
        self.index.write_text("")
        with self.assertRaises(SystemExit) as caught:
            nav.resolve_index(self.index, self.report, workers=2)
        self.assertIn("empty index", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
