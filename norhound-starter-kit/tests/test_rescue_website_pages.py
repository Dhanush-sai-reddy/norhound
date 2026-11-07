"""Tests for the Playwright website rescue connector.

The connector recovers company homepages that the plain urllib crawl could not
read (`source_error`) or could only read as an empty shell
(`js_fallback_candidate`). Every test in this file runs WITHOUT network access:
the browser interaction is behind one injectable seam (`render_page`) and the
public-URL / robots guards are patched out.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any, Awaitable, Callable
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.rescue_website_pages import (  # noqa: E402
    _run_with_browser,
    rescue_selected,
    select_rescue_targets,
)

ORG = "123456789"
TARGET_URL = "https://example.no/"


def _website_evidence(
    status: str = "source_error",
    extraction_state: str | None = None,
    source_url: str = TARGET_URL,
) -> dict[str, Any]:
    value = None
    if extraction_state is not None:
        value = {
            "final_url": source_url,
            "registered_domain": "example.no",
            "title": "",
            "main_text_excerpt": "",
            "extraction_state": extraction_state,
        }
    return {
        "field": "website",
        "status": status,
        "source_type": "registry_linked_company_website",
        "source_class": "registry_linked_company_website",
        "source_url": source_url,
        "retrieved_at": "2026-11-01T00:00:00Z",
        "value": value,
        "as_of": None,
        "note": None,
        "content_sha256": None,
        "source_row_key": None,
        "effective_at": None,
    }


def _profile(
    organisation_number: str = ORG,
    name: str = "Example AS",
    status: str = "source_error",
    extraction_state: str | None = None,
    website: str | None = "example.no",
) -> dict[str, Any]:
    return {
        "organisation_number": organisation_number,
        "name": name,
        "website": website,
        "evidence": {
            "website": _website_evidence(status, extraction_state),
            "registry": {
                "status": "available",
                "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter",
                "retrieved_at": "2026-11-01T00:00:00Z",
                "value": {"navn": name},
            },
            "jobs": {"status": "not_found", "source_url": "https://example.org", "value": None},
        },
    }


def _renderer(
    pages: dict[str, dict[str, Any] | None],
) -> Callable[[str, float], Awaitable[dict[str, Any] | None]]:
    async def render(url: str, timeout: float) -> dict[str, Any] | None:
        return pages.get(url)

    return render


def _rendered(
    html: str,
    *,
    final_url: str = TARGET_URL,
    title: str = "Example AS",
    description: str = "Example description",
    visible_text: str = "Example AS. Org.nr 123456789. " + ("Filler text. " * 20),
) -> dict[str, Any]:
    return {
        "rendered_html": html,
        "final_url": final_url,
        "title": title,
        "description": description,
        "visible_text": visible_text,
    }


def _run(
    profiles: list[dict[str, Any]],
    renderer: Callable[[str, float], Awaitable[dict[str, Any] | None]] | None = None,
    **kwargs: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the rescue with the network guards patched out."""
    with mock.patch("scripts.rescue_website_pages.assert_public_url", return_value=None), mock.patch(
        "scripts.rescue_website_pages._robots_allowed", return_value=True
    ):
        return asyncio.run(
            rescue_selected(profiles, renderer=renderer or _renderer({}), **kwargs)
        )


class SelectorTests(unittest.TestCase):
    def test_selector_picks_source_error_and_js_fallback_candidates(self) -> None:
        profiles = [
            _profile("111", status="source_error"),
            _profile("222", status="available", extraction_state="js_fallback_candidate"),
            _profile("333", status="available", extraction_state="static_complete"),
            _profile("444", status="blocked"),
            _profile("555", status="not_found"),
            _profile("666", status="available"),
        ]
        self.assertEqual(select_rescue_targets(profiles), [0, 1])

    def test_selector_is_empty_for_a_clean_corpus(self) -> None:
        profiles = [
            _profile("111", status="available", extraction_state="static_complete"),
            _profile("222", status="blocked"),
        ]
        self.assertEqual(select_rescue_targets(profiles), [])


class SuccessfulRescueTests(unittest.TestCase):
    def test_success_replaces_website_and_keeps_every_other_evidence_key(self) -> None:
        profile = _profile()
        original_website = copy.deepcopy(profile["evidence"]["website"])
        html = "<html><head><title>Example AS</title></head><body>Org.nr 123456789</body></html>"

        rows, report = _run([profile], renderer=_renderer({TARGET_URL: _rendered(html)}))

        row = rows[0]
        self.assertEqual(row["organisation_number"], ORG)
        self.assertEqual(row["name"], "Example AS")
        self.assertNotEqual(row["evidence"]["website"], original_website)
        self.assertEqual(row["evidence"]["website"]["status"], "available")
        # every other evidence key is untouched
        for key, value in profile["evidence"].items():
            if key == "website":
                continue
            self.assertEqual(row["evidence"][key], value, key)
        self.assertEqual(report["rescued"], 1)
        self.assertEqual(report["failed"], 0)

    def test_success_appends_the_original_website_to_website_attempts(self) -> None:
        profile = _profile()
        original_website = copy.deepcopy(profile["evidence"]["website"])
        html = "<html><body>Org.nr 123456789</body></html>"

        rows, _report = _run([profile], renderer=_renderer({TARGET_URL: _rendered(html)}))

        attempts = rows[0]["evidence"]["website_attempts"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0], original_website)
        self.assertEqual(attempts[0]["status"], "source_error")
        rescue = rows[0]["evidence"]["website_rescue"]
        self.assertEqual(rescue["renderer"], "playwright-chromium")
        self.assertEqual(rescue["original_status"], "source_error")
        self.assertIsNone(rescue["original_extraction_state"])
        self.assertTrue(rescue["retrieved_at"].endswith("Z"))

    def test_success_keeps_the_fetch_website_record_shape(self) -> None:
        profile = _profile()
        html = "<html><body>Org.nr 123456789</body></html>"

        rows, _report = _run([profile], renderer=_renderer({TARGET_URL: _rendered(html)}))

        website = rows[0]["evidence"]["website"]
        value = website["value"]
        for key in (
            "requested_url",
            "final_url",
            "registered_domain",
            "title",
            "description",
            "main_text_excerpt",
            "social_links",
            "structured_organisations",
            "content_sha256",
            "extraction_state",
            "pages",
            "crawl_errors",
        ):
            self.assertIn(key, value)
        self.assertEqual(value["requested_url"], TARGET_URL)
        self.assertEqual(value["registered_domain"], "example.no")
        self.assertEqual(value["extraction_state"], "static_complete")
        self.assertEqual(len(value["pages"]), 1)
        self.assertEqual(value["pages"][0]["url"], TARGET_URL)
        self.assertEqual(website["source_type"], "registry_linked_company_website")

    def test_content_sha256_is_the_digest_of_the_rendered_html(self) -> None:
        profile = _profile()
        html = "<html><body><h1>Rendered by chromium</h1></body></html>"

        rows, _report = _run([profile], renderer=_renderer({TARGET_URL: _rendered(html)}))

        digest = rows[0]["evidence"]["website"]["value"]["content_sha256"]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(digest, hashlib.sha256(html.encode("utf-8")).hexdigest())
        self.assertEqual(rows[0]["evidence"]["website"]["content_sha256"], digest)

    def test_short_rendered_text_stays_a_js_fallback_candidate(self) -> None:
        profile = _profile(status="available", extraction_state="js_fallback_candidate")
        html = "<html><body>tiny</body></html>"

        rows, _report = _run(
            [profile],
            renderer=_renderer({TARGET_URL: _rendered(html, visible_text="tiny")}),
        )

        self.assertEqual(rows[0]["evidence"]["website"]["value"]["extraction_state"], "js_fallback_candidate")


class IdentityGateTests(unittest.TestCase):
    def test_rendered_page_with_the_organisation_number_is_publishable(self) -> None:
        profile = _profile(name="Example AS")
        html = "<html><body>Org.nr 123456789</body></html>"

        rows, report = _run([profile], renderer=_renderer({TARGET_URL: _rendered(html)}))

        assessment = rows[0]["evidence"]["website"]["value"]["identity_assessment"]
        self.assertTrue(assessment["publishable"])
        self.assertEqual(assessment["status"], "exact")
        self.assertEqual(report["identity_statuses"], {"exact": 1})

    def test_rendered_page_without_identity_signal_is_not_publishable(self) -> None:
        profile = _profile(name="Zephyr Labs AS")
        html = "<html><body>Welcome to our site.</body></html>"

        rows, report = _run(
            [profile],
            renderer=_renderer(
                {
                    TARGET_URL: _rendered(
                        html,
                        title="Welcome",
                        description="Welcome",
                        visible_text="Welcome to our site. We sell things to people.",
                    )
                }
            ),
        )

        assessment = rows[0]["evidence"]["website"]["value"]["identity_assessment"]
        self.assertFalse(assessment["publishable"])
        self.assertEqual(assessment["status"], "related_or_uncertain")
        self.assertEqual(report["identity_statuses"], {"related_or_uncertain": 1})


class FailedRescueTests(unittest.TestCase):
    def test_failed_rescue_leaves_the_website_evidence_byte_identical(self) -> None:
        profile = _profile()
        original_website = copy.deepcopy(profile["evidence"]["website"])

        rows, report = _run([profile], renderer=_renderer({}))

        self.assertEqual(
            json.dumps(rows[0]["evidence"]["website"], sort_keys=True, ensure_ascii=False),
            json.dumps(original_website, sort_keys=True, ensure_ascii=False),
        )
        self.assertNotIn("website_attempts", rows[0]["evidence"])
        self.assertNotIn("website_rescue", rows[0]["evidence"])

    def test_failed_rescue_records_a_skip_reason_in_the_report(self) -> None:
        profile = _profile()

        _rows, report = _run([profile], renderer=_renderer({}))

        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["rescued"], 0)
        self.assertTrue(report["skip_reasons"])
        outcome = report["outcomes"][0]
        self.assertEqual(outcome["status"], "failed")
        self.assertTrue(outcome["reason"])
        self.assertEqual(outcome["organisation_number"], ORG)

    def test_non_public_url_is_skipped_without_touching_the_profile(self) -> None:
        profile = _profile()
        original_website = copy.deepcopy(profile["evidence"]["website"])

        with mock.patch(
            "scripts.rescue_website_pages.assert_public_url",
            side_effect=ValueError("Private, loopback, link-local, multicast, and reserved addresses are blocked"),
        ):
            rows, report = asyncio.run(
                rescue_selected([profile], renderer=_renderer({TARGET_URL: _rendered("<html></html>")}))
            )

        self.assertEqual(rows[0]["evidence"]["website"], original_website)
        self.assertEqual(report["skip_reasons"], {"not_public": 1})

    def test_robots_disallow_is_skipped_without_touching_the_profile(self) -> None:
        profile = _profile()
        original_website = copy.deepcopy(profile["evidence"]["website"])

        with mock.patch("scripts.rescue_website_pages.assert_public_url", return_value=None), mock.patch(
            "scripts.rescue_website_pages._robots_allowed", return_value=False
        ):
            rows, report = asyncio.run(
                rescue_selected([profile], renderer=_renderer({TARGET_URL: _rendered("<html></html>")}))
            )

        self.assertEqual(rows[0]["evidence"]["website"], original_website)
        self.assertEqual(report["skip_reasons"], {"robots_disallowed": 1})

    def test_browser_launch_failure_is_recorded_for_every_target(self) -> None:
        profile = _profile()

        with mock.patch("scripts.rescue_website_pages.assert_public_url", return_value=None), mock.patch(
            "scripts.rescue_website_pages._robots_allowed", return_value=True
        ):
            rows, report = asyncio.run(
                rescue_selected(
                    [profile],
                    renderer=_renderer({}),
                    browser_error="Executable doesn't exist at /root/.cache/ms-playwright",
                )
            )

        self.assertEqual(report["skip_reasons"], {"browser_launch_failed": 1})
        self.assertEqual(rows[0]["evidence"]["website"]["status"], "source_error")

    def test_a_missing_playwright_package_does_not_crash_the_stage(self) -> None:
        """The rescue must degrade, never kill the run.

        `playwright` is a declared dependency, but the browser binary is a
        separate one-time download (`playwright install chromium`). If either
        is absent the stage has to record the failure and exit cleanly: the
        external pipeline is fail-fast, so an exception here would take the
        whole 1,000-company run down with it.
        """
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("playwright"):
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)

        with mock.patch.dict("sys.modules", {"playwright": None}), mock.patch(
            "builtins.__import__", side_effect=fake_import
        ):
            rows, report = asyncio.run(
                _run_with_browser([_profile()], workers=1, timeout=5.0, limit=0)
            )

        self.assertEqual(report["skip_reasons"], {"browser_launch_failed": 1})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["evidence"]["website"]["status"], "source_error")

    def test_certificate_error_falls_back_to_http_for_a_scheme_less_registry_value(self) -> None:
        profile = _profile(website="example.no")
        calls: list[str] = []

        async def renderer(url: str, timeout: float) -> dict[str, Any] | None:
            calls.append(url)
            if url.startswith("http://"):
                return _rendered("<html><body>Org.nr 123456789</body></html>", final_url="http://example.no/")
            return None

        with mock.patch(
            "scripts.rescue_website_pages._LAST_RENDER_ERROR",
            "Error: net::ERR_CERT_COMMON_NAME_INVALID",
        ):
            rows, report = _run([profile], renderer=renderer)

        self.assertEqual(calls, ["https://example.no/", "http://example.no/"])
        self.assertEqual(report["rescued"], 1)
        self.assertEqual(rows[0]["evidence"]["website"]["status"], "available")
        self.assertEqual(rows[0]["evidence"]["website"]["value"]["requested_url"], "http://example.no/")

    def test_no_http_fallback_when_the_registry_value_already_declares_a_scheme(self) -> None:
        profile = _profile(website="https://example.no")
        calls: list[str] = []

        async def renderer(url: str, timeout: float) -> dict[str, Any] | None:
            calls.append(url)
            return None

        with mock.patch(
            "scripts.rescue_website_pages._LAST_RENDER_ERROR",
            "Error: net::ERR_CERT_COMMON_NAME_INVALID",
        ):
            _rows, report = _run([profile], renderer=renderer)

        self.assertEqual(calls, ["https://example.no/"])
        self.assertEqual(report["skip_reasons"], {"render_failed": 1})


class OutputShapeTests(unittest.TestCase):
    def test_output_has_exactly_one_row_per_input_row_in_input_order(self) -> None:
        profiles = [
            _profile("111", status="source_error"),
            _profile("222", status="available", extraction_state="static_complete"),
            _profile("333", status="available", extraction_state="js_fallback_candidate"),
            _profile("444", status="blocked"),
            _profile("555", status="source_error"),
        ]
        html = "<html><body>Org.nr 123456789</body></html>"

        rows, report = _run(profiles, renderer=_renderer({TARGET_URL: _rendered(html)}))

        self.assertEqual(len(rows), len(profiles))
        self.assertEqual(
            [row["organisation_number"] for row in rows],
            [profile["organisation_number"] for profile in profiles],
        )
        self.assertEqual(report["profiles"], 5)
        self.assertEqual(report["selected"], 3)
        self.assertEqual(report["rescued"], 3)

    def test_limit_caps_the_number_of_rescue_attempts(self) -> None:
        profiles = [
            _profile("111", status="source_error"),
            _profile("222", status="source_error"),
            _profile("333", status="source_error"),
        ]

        rows, report = _run(profiles, renderer=_renderer({}), limit=2)

        self.assertEqual(len(rows), 3)
        self.assertEqual(report["selected"], 2)
        self.assertEqual(report["failed"], 2)

    def test_profiles_without_a_website_are_skipped(self) -> None:
        profile = _profile(website=None)
        profile["evidence"]["website"]["source_url"] = ""

        rows, report = _run([profile], renderer=_renderer({}))

        self.assertEqual(report["skip_reasons"], {"no_target_url": 1})
        self.assertEqual(rows[0]["evidence"]["website"]["status"], "source_error")


if __name__ == "__main__":
    unittest.main()
