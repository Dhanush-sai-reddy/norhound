"""Adversarial identity-gate tests: tricky cases must reject, clean cases must pass.

No network. Synthetic website records fed straight into assess_website_identity
and assess_social_identity. A single wrong-company acceptance fails the suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.identity import assess_social_identity, assess_website_identity  # noqa: E402


def profile_with_site(org, name, site_value, status="available"):
    return {
        "organisation_number": org,
        "name": name,
        "evidence": {"website": {"status": status, "source_url": site_value.get("final_url", ""), "value": site_value}},
    }


def test_orgnr_on_page_accepts():
    p = profile_with_site("123456789", "FJORDLYS HOLDING AS", {
        "final_url": "https://fjordlys-holding.no/",
        "title": "Fjordlys Holding",
        "main_text_excerpt": "Fjordlys Holding AS, org.nr. 123 456 789, driver investeringsvirksomhet. " * 10,
    })
    a = assess_website_identity(p)
    assert a["status"] == "exact" and a["score"] == 1.0, a


def test_exact_name_tokens_accept():
    p = profile_with_site("111222333", "NORDLYS BAKERI AS", {
        "final_url": "https://nordlysbakeri.no/",
        "title": "Nordlys Bakeri AS — ferske brød hver dag",
        "main_text_excerpt": "Velkommen til Nordlys Bakeri. " * 20,
    })
    a = assess_website_identity(p)
    assert a["status"] == "exact", a


def test_parked_domain_rejects():
    p = profile_with_site("111222333", "NORDLYS BAKERI AS", {
        "final_url": "https://nordlysbakeri.no/",
        "title": "nordlysbakeri.no is for sale",
        "main_text_excerpt": "This domain is for sale. Find the best information and most relevant links on all topics related to bakery.",
    })
    a = assess_website_identity(p)
    assert a["status"] != "exact" and a["score"] <= 0.3, a


def test_group_site_names_other_operator_rejects():
    # Page belongs to a group parent that merely mentions the assessed company.
    p = profile_with_site("999888777", "FJORDLYS DOTTRE AS", {
        "final_url": "https://konsern-eksempel.no/dotre/",
        "title": "Konsern Eksempel ASA — våre datterselskaper",
        "main_text_excerpt": ("Konsern Eksempel ASA eier Fjordlys Dottre. Kontakt konsernpost@konsern-eksempel.no. " * 15),
    })
    a = assess_website_identity(p)
    assert a["status"] != "exact", a


def test_empty_homepage_rejects():
    p = profile_with_site("111222333", "NORDLYS BAKERI AS", {
        "final_url": "https://nordlysbakeri.no/",
        "title": "",
        "main_text_excerpt": "",
    })
    a = assess_website_identity(p)
    assert a["status"] != "exact", a


def test_matching_social_handle_accepts():
    p = {"organisation_number": "1", "name": "ORLAND SPAREBANK"}
    a = assess_social_identity(p, {"platform": "facebook", "url": "https://facebook.com/orlandsparebank"})
    assert a["publishable"] is True, a


def test_unrelated_social_handle_rejects():
    p = {"organisation_number": "1", "name": "FJÆRLAND KRAFT AS"}
    a = assess_social_identity(p, {"platform": "facebook", "url": "https://facebook.com/briskebyskole"})
    assert a["publishable"] is False, a


def test_generic_social_url_rejects():
    p = {"organisation_number": "1", "name": "EQUINOR ASA"}
    a = assess_social_identity(p, {"platform": "facebook", "url": "https://facebook.com/terms.php"})
    assert a["publishable"] is False, a
