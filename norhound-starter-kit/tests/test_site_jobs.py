"""Junk-gate tests for extract_company_site_jobs.

Grounded in the measured precision bug (worthknowing.md 7): ~10% of published
job_posting rows carried legal-page / section-header / CTA spans as titles
("Salgs- og leveringsbetingelser", "Bestill synstest", "Ledelsen"). The gate
must reject those (and close variants) while never blocking a real role title.
"""

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extract_company_site_jobs as jobs  # noqa: E402
from extract_company_site_jobs import (  # noqa: E402
    GENERIC_ANCHOR,
    discover,
    extract_jobs_from_page,
)


def _profile_with_no_captured_careers_page():
    return {
        "organisation_number": "123456789",
        "evidence": {
            "website": {
                "status": "available",
                "source_url": "https://example.test/",
                "value": {
                    "identity_assessment": {"status": "exact", "publishable": True},
                    "final_url": "https://example.test/",
                    "pages": [{"url": "https://example.test/om-oss", "title": "Om oss"}],
                },
            }
        },
    }


def test_discovers_careers_link_from_homepage_instead_of_guessing():
    requested = []

    def fake_fetch(url, *, timeout, max_bytes):
        requested.append(url)
        if url.rstrip("/") == "https://example.test":
            return '<html><a href="/karriere">Karriere</a></html>', b"x", url
        return "", b"", None

    with mock.patch.object(jobs, "fetch_page_html", side_effect=fake_fetch):
        with mock.patch.object(jobs, "extract_jobs_from_page", return_value=[]):
            rows, status = discover(_profile_with_no_captured_careers_page(), timeout=1.0, max_bytes=1000)

    assert status["status"] != "site_not_verified"
    assert "https://example.test/karriere" in requested
    assert "https://example.test/careers" not in requested


def test_falls_back_to_guessed_paths_when_homepage_has_no_careers_link():
    requested = []

    def fake_fetch(url, *, timeout, max_bytes):
        requested.append(url)
        if url.rstrip("/") == "https://example.test":
            return "<html><a href='/om-oss'>Om oss</a></html>", b"x", url
        return "", b"", None

    with mock.patch.object(jobs, "fetch_page_html", side_effect=fake_fetch):
        with mock.patch.object(jobs, "extract_jobs_from_page", return_value=[]):
            discover(_profile_with_no_captured_careers_page(), timeout=1.0, max_bytes=1000)

    assert any(url.endswith("/karriere") for url in requested)

MEASURED_JUNK = [
    "Salgs- og leveringsbetingelser",
    "Bestill synstest",
    "Ledelsen",
]

JUNK_VARIANTS = [
    "Salgsbetingelser",
    "Kjøpsvilkår",
    "Vilkår",
    "Personvern",
    "Informasjonskapsler",
    "Cookies",
    "Bestill time",
    "Styret",
    "Les vilkårene",
]

REAL_TITLES = [
    "Butikksjef Viksund",
    "R&D Engineer",
    "Barnehagelærer",
    "Sykepleier 100%",
    "Senior utvikler",
]


def test_measured_junk_spans_blocked():
    for span in MEASURED_JUNK:
        assert GENERIC_ANCHOR.search(span.casefold()), f"junk not blocked: {span}"


def test_junk_variants_blocked():
    for span in JUNK_VARIANTS:
        assert GENERIC_ANCHOR.search(span.casefold()), f"variant not blocked: {span}"


def test_real_role_titles_not_blocked():
    for span in REAL_TITLES:
        assert not GENERIC_ANCHOR.search(span.casefold()), f"real title blocked: {span}"


def _profile(domain: str = "example.no") -> dict:
    return {
        "organisation_number": "912345678",
        "evidence": {"website": {"value": {"registered_domain": domain}}},
    }


def _page(*links: tuple[str, str], body: str = "Søknadsfrist 1. november 2026") -> str:
    anchors = "".join(f'<a href="{href}">{text}</a>' for href, text in links)
    return f"<html><body><p>{body}</p>{anchors}</body></html>"


def test_page_level_junk_never_published():
    html = _page(
        ("/karriere/butikksjef-viksund", "Butikksjef Viksund"),
        ("/vilkar", "Salgs- og leveringsbetingelser"),
        ("/salgsbetingelser", "Salgsbetingelser"),
        ("/synstest", "Bestill synstest"),
        ("/ledelsen", "Ledelsen"),
    )
    obs = extract_jobs_from_page(
        _profile(), "https://example.no/karriere/", html, html.encode(), "https://example.no/karriere/"
    )
    titles = {o["evidence_span"] for o in obs}
    assert titles == {"Butikksjef Viksund"}, f"unexpected published titles: {titles}"


def test_real_role_still_published_with_junk_present():
    html = _page(("/karriere/utvikler-oslo", "Senior utvikler"))
    obs = extract_jobs_from_page(
        _profile(), "https://example.no/karriere/", html, html.encode(), "https://example.no/karriere/"
    )
    assert len(obs) == 1
    assert obs[0]["evidence_span"] == "Senior utvikler"
