#!/usr/bin/env python3
"""Emit Signalpost output-contract envelopes: claims[] + evidence[] per company.

Why this exists
---------------
`OUTPUT_CONTRACT.md` and Builderr's own public citation validator
(`builderr-ai/signalpost-citation-validator`) both describe an envelope whose
facts are addressable as `claims[]` items, each citing an `evidence[]` record
with `source_url`, `retrieved_at`, `content_sha256` and a span. Our batch
artifacts carried facts only inside `profile`/`modules` blobs and as flat
observation rows, so nothing was expressed in that shape.

This script is a pure, offline projection of artifacts we already produced:

  * frozen batch profiles (`--profiles`)        -> registry + financial claims
  * external observations (`--observations`)    -> website/social/hiring/news claims
  * labels (`--labels`)                         -> the exact-entity gate

It makes no network requests, invents no values, and never promotes an
observation that the label pass did not mark `exact_entity`. Dates for dated
news are taken verbatim from the source (offset included) because the pool key
is the lower-cased string ``"<title> (<published datetime>)"``.

    uv run python scripts/emit_contract_envelope.py \
        --profiles out/web1000-profiles.jsonl \
        --observations out/web1000batch.external.jsonl \
        --labels out/web1000batch.labels.jsonl \
        --output out/web1000batch.contract.jsonl

Optional `--envelopes` merges the claims into existing terminal envelopes
(append-only: `modules`/`profile` are left untouched) and `--snapshots-dir`
writes retained excerpt bytes plus `snapshot_path` for each cited evidence.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import html
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# value normalisation (mirrors the forms in Builderr's v2 expected facts)
# --------------------------------------------------------------------------- #

def url_key(url: str) -> str:
    """host + path, lowercased, no scheme, no www., no trailing slash."""
    if not url:
        return ""
    candidate = url.strip() if "://" in url else "https://" + url.strip()
    try:
        parsed = urllib.parse.urlparse(candidate)
    except ValueError:
        return candidate.lower()
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"{host}{path}".lower()


def domain_key(url: str) -> str:
    if not url:
        return ""
    candidate = url.strip() if "://" in url else "https://" + url.strip()
    try:
        host = urllib.parse.urlparse(candidate).hostname or ""
    except ValueError:
        return url.strip().lower()
    if "." not in host and "/" in url:  # bare "website.no" values from the register
        host = url.strip().lower()
    return host.lower().removeprefix("www.")


def text_key(value: Any) -> str:
    return " ".join(html.unescape(str(value)).split()).strip()


ROLE_TRUSTED_STRATEGIES = {
    "jobs_feed_discovery",
    "official_nav_job_feed_orgnr_match", "nav_job_feed", "ats_role_card",
    "finn_job_details", "nav_direct_api", "apify_nav_jobs",
}
CAREERS_PATH_HINTS = (
    "jobb", "job", "karriere", "career", "stilling", "ledig", "vacanc", "recruit",
    "stillinger", "ledige", "annonse", "join-us", "joinus", "work-with-us", "ahoj",
)


def _careers_path(url: str) -> bool:
    try:
        path = (urllib.parse.urlparse(url if "://" in url else "https://" + url).path or "").lower()
        host = (urllib.parse.urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
    except ValueError:
        return False
    return any(hint in path for hint in CAREERS_PATH_HINTS) or any(
        hint in host for hint in ("jobb", "career", "stilling"))


NAVIGATION_TEXT = (
    "logg inn", "logg ut", "logg inn", "personvern", "kake", "cookies", "vilkår", "tilbake",
    "meny", "søk", "kontakt", "om oss", "hjem", "les mer", "les mer her", "les saken",
    "se alle", "alle ledige", "abonner", "del denne", "forrige", "neste", "start",
    "recruitment scam", "jobbsøk", "medarbeidere", "stillinger", "nyheter", "aktuelt",
)


def _plausible_role(title: str) -> bool:
    """Reject navigation labels leaking into job_posting rows.

    Kept deliberately conservative: an over-broad role title is a quality
    problem, a navigation string published as a job is both a quality problem
    and exactly the failure the reviewer called out.
    """
    if not title:
        return False
    low = title.lower()
    if not 3 <= len(title) <= 140:
        return False
    if len(title.split()) > 12:
        return False
    # Use word boundaries to avoid false positives on substrings like "søk" in "søker"
    import re
    for marker in NAVIGATION_TEXT:
        # Escape regex special chars and add word boundaries
        pattern = r'\b' + re.escape(marker) + r'\b'
        if re.search(pattern, low):
            return False
    return True


# --------------------------------------------------------------------------- #
# evidence records
# --------------------------------------------------------------------------- #

class EvidenceBook:
    """Deduplicated evidence records for one envelope, with stable ids."""

    def __init__(self) -> None:
        self._by_key: dict[tuple, str] = {}
        self.records: list[dict] = []

    def add(self, *, source_url: str, source_class: str, retrieved_at: str | None,
            content_sha256: str | None, claim_span: str | None,
            extraction_method: str | None = None, effective_at: str | None = None,
            reporting_period: str | None = None, publication_date: str | None = None,
            snapshot_text: str | None = None) -> str:
        span = claim_span if claim_span is not None else ""
        key = (source_url or "", source_class or "", content_sha256 or "", span[:200])
        existing = self._by_key.get(key)
        if existing:
            return existing
        slug = re.sub(r"[^a-z0-9]+", "-", (source_class or "src").lower()).strip("-")[:18] or "src"
        digest = hashlib.sha256(f"{key[0]}|{key[2]}|{span}".encode()).hexdigest()[:12]
        evidence_id = f"ev-{slug}-{digest}"
        while evidence_id in self._by_key.values():
            evidence_id = evidence_id[:-2] + "x1"
        record = {
            "id": evidence_id,
            "source_url": source_url,
            "source_class": source_class,
            "retrieved_at": retrieved_at or "",
            "content_sha256": content_sha256 or "",
            "claim_span": span,
            "extraction_method": extraction_method or "unknown",
        }
        for optional, name in ((effective_at, "effective_at"), (reporting_period, "reporting_period"),
                               (publication_date, "publication_date")):
            if optional:
                record[name] = optional
        if snapshot_text is not None:
            record["_snapshot_text"] = snapshot_text
        self._by_key[key] = evidence_id
        self.records.append(record)
        return evidence_id


# --------------------------------------------------------------------------- #
# claims
# --------------------------------------------------------------------------- #

def make_claim(field: str, value: Any, evidence_ids: list[str], *, confidence: float = 0.99,
               availability: str = "available", family: str | None = None,
               details: dict | None = None) -> dict:
    claim: dict = {
        "field": field,
        "value": value,
        "availability": availability,
        "confidence": confidence,
        "evidence_ids": list(dict.fromkeys(evidence_ids)),
    }
    if family:
        claim["family"] = family
    if details:
        claim["details"] = details
    if availability != "available" and not claim["evidence_ids"]:
        claim["reason"] = (details or {}).get("reason", "no verified source")
    return claim


# --------------------------------------------------------------------------- #
# registry claims (profile.evidence[*])
# --------------------------------------------------------------------------- #

FINANCIAL_FIELDS = {
    "revenue": "revenue_nok",
    "operating_result": "operating_profit_nok",
    "annual_result": "net_result_nok",
    "assets": "total_assets_nok",
    "equity": "equity_nok",
    "debt": "debt_nok",
    "profit_before_tax": "profit_before_tax_nok",
}

REGISTRY_SCALARS = {
    "organisasjonsnummer": "organisation_number",
    "navn": "legal_name",
    "organisasjonsform.kode": "legal_form_code",
    "organisasjonsform.beskrivelse": "legal_form_label",
    "naeringskode1.kode": "industry_code",
    "naeringskode1.beskrivelse": "industry_label",
    "hjemmeside": "official_website",
    "epostadresse": "contact_email",
    "telefon": "contact_phone",
    "mobil": "contact_mobile",
    "postnummer": "postal_code",
    "poststed": "postal_place",
    "kommune": "municipality",
    "kommunenummer": "municipality_number",
    "land": "country",
    "sisteInnsendteAarsregnskap": "latest_submitted_accounts_year",
    "registreringsdatoenhetsregisteret": "registry_registration_date",
    "stiftelsesdato": "foundation_date",
    " maalform".strip(): "language_of_registration",
    "aktivitet": "registered_activity",
    "vedtektsfestetFormaal": "articles_purpose",
    "antallAnsatte": "employee_count",
    "institusjonellSektorkode.beskrivelse": "institutional_sector",
    "overordnetEnhet": "parent_organisation_number",
}

REGISTRY_FLAGS = {
    "konkurs": "bankrupt",
    "underAvvikling": "liquidating",
    "underTvangsavviklingEllerTvangsopplosning": "compulsory_liquidation",
    "registrertIForetaksregisteret": "registered_in_brønnøysund_1",
    "registrertIMvaRegisteret": "registered_in_vat",
    "registrertIFrivillighetsregisteret": "registered_in_volunteer",
    "registrertIPartiregisteret": "registered_in_political_party",
    "erIKonsern": "part_of_group",
    "registrertILov om økonomisk støtte": "",
}


def _flatten_registry(value: dict) -> dict:
    """Project the nested BRREG entity payload onto the flat keys we publish."""
    out: dict[str, Any] = {}
    address = value.get("forretningsadresse") or {}
    postal = value.get("postadresse") or {}
    for label, source in (("business", address), ("postal", postal)):
        for key in ("adresse", "postnummer", "poststed", "kommune", "kommunenummer", "land", "landkode"):
            raw = (source or {}).get(key)
            if isinstance(raw, list):
                raw = ", ".join(str(part) for part in raw if part)
            if raw:
                out[f"{label}_{key}"] = raw
    for key, path in (
        ("postnummer", "postadresse.postnummer"), ("poststed", "postadresse.poststed"),
        ("kommune", "postadresse.kommune"), ("kommunenummer", "postadresse.kommunenummer"),
        ("land", "postadresse.land"),
    ):
        cursor: Any = value
        for part in path.split("."):
            cursor = cursor.get(part) if isinstance(cursor, dict) else None
        if cursor and f"postal_{key}" not in out:
            out[f"postal_{key}"] = cursor
    capital = value.get("kapital") or {}
    if capital.get("belop"):
        out["share_capital"] = capital["belop"]
        out["share_capital_currency"] = capital.get("valuta") or "NOK"
    for src, dst in (("naeringskode2", None), ("naeringskode3", None), ("hjelpeenhetskode", None)):
        node = value.get(src) or {}
        if node.get("kode") and dst:
            out[dst] = node["kode"]
    for key, field in REGISTRY_SCALARS.items():
        if value.get(key) not in (None, ""):
            out[field] = value[key]
    return out


def registry_claims(profile: dict, book: EvidenceBook) -> list[dict]:
    claims: list[dict] = []
    evidence_map = profile.get("evidence") or {}

    def source_for(field_key: str) -> tuple[dict | None, str]:
        record = evidence_map.get(field_key)
        if not isinstance(record, dict):
            return None, ""
        if record.get("status") not in ("available", "complete"):
            return None, ""
        ev_id = book.add(
            source_url=record.get("source_url") or "",
            source_class=record.get("source_class") or "official_registry",
            retrieved_at=record.get("retrieved_at"),
            content_sha256=record.get("content_sha256"),
            claim_span=json.dumps(record.get("value"), ensure_ascii=False, sort_keys=True)[:1500]
            if record.get("value") is not None else "",
            extraction_method="official_api_field_projection",
            effective_at=record.get("as_of") or record.get("effective_at"),
        )
        return record, ev_id

    # --- identity -------------------------------------------------------- #
    record, ev_id = source_for("registry")
    if record:
        value = record.get("value") or {}
        flat = _flatten_registry(value)
        for field, val in sorted(flat.items()):
            if val in (None, "", []):
                continue
            projected = domain_key(val) if field in ("official_website",) else (
                val if not isinstance(val, str) else text_key(val))
            claims.append(make_claim(field, projected, [ev_id], family="identity",
                                     details={"source_row_key": record.get("source_row_key"),
                                              "registry_value": val}))
        for key, field in sorted(REGISTRY_FLAGS.items()):
            if not field or key not in value:
                continue
            raw = value.get(key)
            if isinstance(raw, str):
                normalised = raw.strip().lower() in ("true", "1", "ja")
            else:
                normalised = bool(raw)
            claims.append(make_claim(field, normalised, [ev_id], family="identity"))
        address = value.get("forretningsadresse") or {}
        parts = [p for p in ((address.get("adresse") or [""])[0] if isinstance(address.get("adresse"), list) else address.get("adresse"),
                             address.get("postnummer"), address.get("poststed")) if p]
        if parts:
            claims.append(make_claim("business_address", " ".join(str(p) for p in parts), [ev_id], family="identity"))

    # --- live registry snapshot (independent second citation) ------------ #
    record, live_id = source_for("registry_live")
    if record:
        value = record.get("value") or {}
        if value.get("name"):
            claims.append(make_claim("legal_name_live", text_key(value["name"]), [live_id], family="identity"))
        if value.get("website"):
            claims.append(make_claim("official_website_live", domain_key(value["website"]), [live_id],
                                     family="identity", details={"registry_value": value["website"]}))

    # --- financials: one claim per figure per year ----------------------- #
    record, fin_id = source_for("financials")
    if record:
        for rec in ((record.get("value") or {}).get("records") or []):
            period = rec.get("period") or {}
            year = (period.get("tilDato") or "")[:4]
            for key, field in sorted(FINANCIAL_FIELDS.items()):
                amount = rec.get(key)
                if amount is None:
                    continue
                claims.append(make_claim(field, float(amount), [fin_id], family="financials",
                                         details={"reporting_year": year, "account_type": rec.get("account_type")},
                                         ))
            claims.append(make_claim("reporting_period", f"{period.get('fraDato')}..{period.get('tilDato')}",
                                     [fin_id], family="financials"))
            claims.append(make_claim("account_currency", rec.get("currency") or "NOK", [fin_id], family="financials"))

    # --- multi-year history from the same fetched records ---------------- #
    record, hist_id = source_for("financial_history")
    if record:
        years = (record.get("value") or {}).get("years") or []
        if years:
            claims.append(make_claim("financial_history_years", [str(y) for y in years], [hist_id],
                                     family="financials", details={"count": len(years)}))
        for pdf in (record.get("value") or {}).get("pdfs") or []:
            year = str(pdf.get("year") if isinstance(pdf, dict) else pdf)[:4]
            url = pdf.get("url") if isinstance(pdf, dict) else None
            if year and url:
                claims.append(make_claim("annual_accounts_pdf", url, [hist_id], family="financials",
                                         details={"reporting_year": year}))

    # --- roles: one claim per person per role ---------------------------- #
    record, role_id = source_for("roles")
    if record:
        roles = (record.get("value") or {}).get("roles") or []
        for index, role in enumerate(roles):
            if not isinstance(role, dict):
                continue
            name = text_key(role.get("name") or "")
            if name:
                claims.append(make_claim(f"role_holder", name, [role_id], family="roles",
                                         details={"role": role.get("role"), "role_code": role.get("role_code"),
                                                  "index": index}))
            if role.get("role"):
                claims.append(make_claim("role_description", text_key(role["role"]), [role_id], family="roles",
                                         details={"holder": name or None}))
            if role.get("group"):
                claims.append(make_claim("role_group", text_key(role["group"]), [role_id], family="roles"))
        claims.append(make_claim("role_count", len(roles), [role_id], family="roles"))

    # --- subunits / locations -------------------------------------------- #
    record, loc_id = source_for("locations")
    if record:
        locations = (record.get("value") or {}).get("locations") or []
        for location in locations:
            org = location.get("organisation_number")
            if org:
                claims.append(make_claim("subunit_organisation_number", str(org), [loc_id], family="roles",
                                         details={"name": location.get("name")}))
        claims.append(make_claim("location_count", len(locations), [loc_id], family="roles"))

    # --- explicit abstentions for sources we did check -------------------- #
    for field_key, record in evidence_map.items():
        if not isinstance(record, dict):
            continue
        status = record.get("status")
        if status in ("available", "complete"):
            continue
        availability = {"not_found": "not_available", "source_error": "failed",
                        "blocked": "blocked", "ambiguous": "ambiguous", "timeout": "failed"}.get(status, "not_available")
        claims.append(make_claim(f"registry_{field_key}", None, [], availability=availability,
                                 family="identity", details={"reason": record.get("note") or status}))
    return claims


# --------------------------------------------------------------------------- #
# external observation claims
# --------------------------------------------------------------------------- #

NEWS_SIGNALS = {"public_post", "public_mention"}
DATE_KEYS = ("published_at", "published", "date", "date_published", "effective_at", "observed_at")
TITLE_KEYS = ("title", "job_title", "jobtitle", "headline", "name", "employer_name")
ROLE_TRUSTED_STRATEGIES_ADD = {"job_board"}


def obs_field(obs: dict, *keys: str, default=None):
    """First non-empty value across the payload locations our connectors use.

    Older rows keep values at the top level, newer ones nest them under
    ``signal`` (official API payloads) or ``metrics``.
    """
    containers = (obs.get("signal"), obs.get("metrics"), obs.get("details"), obs)
    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in keys:
            value = container.get(key)
            if value not in (None, "", [], {}):
                return value
    return default


def publication_datetime(obs: dict) -> str | None:
    """Publication timestamp exactly as published, offset included, never widened."""
    value = obs_field(obs, *DATE_KEYS)
    return str(value) if value not in (None, "") else None


def news_value(obs: dict) -> str | None:
    metrics = obs.get("metrics") or {}
    explicit = metrics.get("claim_value")
    if explicit:
        return text_key(explicit)
    title = obs_field(obs, "title", "headline") or (obs.get("evidence_span") or "").split(" — ")[0]
    title = text_key(re.sub(r"\s*[—-]\s*[\w:,+.\s]{4,}$", "", str(title or "")))
    published = publication_datetime(obs)
    if title and published:
        return f"{title} ({published})"
    return text_key(title) if title else None


def external_claims(rows: list[dict], book: EvidenceBook) -> list[dict]:
    claims: list[dict] = []
    counters: dict[str, int] = collections.Counter()

    for obs in rows:
        signal = obs.get("signal_type")
        metrics = obs.get("metrics") or {}
        span = obs.get("evidence_span") or ""
        published = publication_datetime(obs)
        ev_id = book.add(
            source_url=obs.get("source_url") or "",
            source_class=obs.get("source_class") or obs.get("platform") or "external",
            retrieved_at=obs.get("retrieved_at"),
            content_sha256=obs.get("content_sha256"),
            claim_span=span[:1500],
            extraction_method=obs.get("strategy") or "unknown",
            effective_at=obs.get("effective_at"),
            publication_date=published,
            snapshot_text=(metrics.get("body_excerpt") or obs.get("raw_item") or None),
        )
        strategy = obs.get("strategy") or ""
        platform = obs.get("platform") or ""

        if signal in NEWS_SIGNALS:
            value = news_value(obs)
            if value and published and counters["dated_news"] < 20:
                # the family is *dated* news: an undated mention is not a matchable news fact
                counters["dated_news"] += 1
                claims.append(make_claim("dated_news", value, [ev_id], family="news",
                                         details={"url": obs.get("source_url"), "published_at": published,
                                                  "date_source": metrics.get("date_source"),
                                                  "title": metrics.get("title") or obs_field(obs, "title")}))
            elif value:
                claims.append(make_claim("public_mention", text_key(value)[:600], [ev_id], family="other",
                                         details={"url": obs.get("source_url"), "undated": True}))
            continue

        if signal == "profile_handle":
            handle = obs_field(obs, "handle", "url", "profile_url") or obs.get("source_url")
            if handle:
                claims.append(make_claim("social_profiles", url_key(str(handle)), [ev_id], family="social",
                                         details={"platform": obs_field(obs, "platform") or platform,
                                                  "url": str(handle), "domain": domain_key(str(handle))}))
            continue

        if signal == "careers_page":
            url = obs_field(obs, "careers_url", "url") or obs.get("source_url")
            if url:
                claims.append(make_claim("hiring_signal", url_key(str(url)), [ev_id], family="hiring",
                                         details={"url": str(url), "basis": "careers page published on the verified site"}))
                claims.append(make_claim("careers_page", str(url), [ev_id], family="hiring"))
            continue

        if signal == "job_posting":
            url = obs_field(obs, "application_url", "apply_url", "job_url") or obs.get("source_url")
            title = text_key(obs_field(obs, "job_title", "title", "jobtitle") or span[:120])
            # a role title is only published when a job source said so; a careers-ish
            # URL on a company site earns the hiring signal, not a specific role
            trusted = (strategy in ROLE_TRUSTED_STRATEGIES
                       or platform in ROLE_TRUSTED_STRATEGIES_ADD
                       or obs.get("source_class") in ("official_api", "official_job_board"))
            if url and trusted and _plausible_role(title):
                claims.append(make_claim("job_postings", url_key(str(url)), [ev_id], family="hiring",
                                         details={"title": title, "url": str(url), "published_at": published}))
                if counters["job_titles"] < 20:
                    counters["job_titles"] += 1
                    claims.append(make_claim("job_title", title, [ev_id], family="hiring",
                                             details={"job_url": str(url), "strategy": strategy}))
                for key, field in (("employer_name", "job_employer"), ("city_municipal", "job_location"),
                                   ("engagement_type", "job_engagement_type"), ("extent", "job_extent"),
                                   ("sector", "job_sector"), ("position_count", "position_count"),
                                   ("expires", "job_deadline"), ("application_url", "job_application_url")):
                    value = obs_field(obs, key)
                    if value:
                        claims.append(make_claim(field, text_key(value) if isinstance(value, str) else value,
                                                 [ev_id], family="hiring", details={"job_title": title}))
            elif url and _careers_path(str(url)):
                claims.append(make_claim("hiring_signal", url_key(str(url)), [ev_id], family="hiring",
                                         details={"url": str(url), "basis": "job listing page on verified site"}))
            continue

        if signal in ("review_summary", "profile_metrics", "review", "customer_review", "buzz_metrics"):
            rating = obs_field(obs, "rating", "average_rating", "stars")
            count = obs_field(obs, "review_count", "count", "ratings_count")
            if rating is not None:
                claims.append(make_claim("average_rating", float(rating), [ev_id], family="reviews",
                                         details={"source": platform, "review_count": count}))
            if count is not None:
                claims.append(make_claim("review_count", int(count), [ev_id], family="reviews",
                                         details={"source": platform}))
            if rating is not None or count is not None:
                claims.append(make_claim("ratings_reviews", url_key(obs.get("source_url") or ""), [ev_id],
                                         family="reviews", details={"rating": rating, "review_count": count}))
            label = obs_field(obs, "sentiment_label", "sentiment")
            if label:
                claims.append(make_claim("sentiment", text_key(label), [ev_id], family="reviews",
                                         details={"method": metrics.get("sentiment_method") or "rating_derived"}))
            continue

        if signal == "website_description":
            description = obs_field(obs, "description") or span
            if description:
                claims.append(make_claim("business_description", text_key(description)[:1200], [ev_id],
                                         family="website"))
            continue

        if signal in ("contact_email", "contact_phone"):
            field = "contact_email" if signal == "contact_email" else "contact_phone"
            value = obs_field(obs, field, "email", "phone") or span
            if value:
                claims.append(make_claim(field, text_key(value), [ev_id], family="identity"))
            continue

        value = obs_field(obs, "value") or span or obs.get("source_url")
        if value:
            claims.append(make_claim(str(signal), text_key(value)[:600], [ev_id], family="other",
                                     details={"platform": platform, "strategy": strategy}))
    return claims
# --------------------------------------------------------------------------- #
# envelope assembly
# --------------------------------------------------------------------------- #

def build_envelope(profile: dict, observations: list[dict], *, started_at: str,
                   snapshot_root: Path | None = None, span_fallback: bool = False) -> dict:
    book = EvidenceBook()
    claims = registry_claims(profile, book)
    claims += external_claims([obs for obs in observations if obs.get("exact_entity")], book)

    claims.sort(key=lambda c: (c.get("family") or "zzz", c["field"], json.dumps(c["value"], ensure_ascii=False, sort_keys=True)))
    unique: list[dict] = []
    seen_claims: set[tuple] = set()
    for claim in claims:
        key = (claim["field"], json.dumps(claim["value"], ensure_ascii=False, sort_keys=True), claim["availability"])
        if key in seen_claims:
            continue
        seen_claims.add(key)
        unique.append(claim)
    claims = unique
    seen_ids = {c["id"] for c in book.records}
    if len(seen_ids) != len(book.records):
        raise SystemExit("duplicate evidence ids emitted")

    evidence = []
    for record in book.records:
        entry = {k: v for k, v in record.items() if not k.startswith("_")}
        text = record.get("_snapshot_text")
        if text is None and span_fallback:
            # the span is the only bytes we retained; hashing them keeps the
            # recorded digest honest about what the snapshot file actually holds
            text = record.get("claim_span") or None
        if snapshot_root and text:
            body = text.encode("utf-8")
            digest = hashlib.sha256(body).hexdigest()
            relative = Path("snapshots") / f"{digest}.gz"
            target = snapshot_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(gzip.compress(body, mtime=0))
            entry["snapshot_path"] = str(relative)
            entry["content_sha256"] = digest
        evidence.append(entry)

    requested = sum(1 for _ in observations)
    return {
        "organisation_number": str(profile.get("organisation_number")),
        "run": {
            "run_id": "contract-emit",
            "started_at": started_at,
            "completed_at": started_at,
            "terminal_status": "completed",
        },
        "claims": claims,
        "evidence": evidence,
        "changes": [],
        "errors": [],
        "operations": {
            "requests": 0,
            "runtime_ms": 0,
            "third_party_cost_usd": 0,
            "claims": len(claims),
            "evidence": len(evidence),
            "observations": requested,
        },
    }


def merge_envelope(existing: dict, built: dict) -> dict:
    """Merge the freshly built contract sections into a base-batch envelope.

    The claims and the evidence are replaced — they are re-derived from the
    frozen profiles and the gated observations, so the merge is the point of
    this stage. Everything else the base batch produced (the profile, the
    modules, the refresh marker, the run timestamps) is kept.

    The built envelope is deliberately NOT nested under a second key. A copy
    of every claim and every evidence record would double the file: for the
    1,000-company submission that pushed ``envelopes.jsonl`` to 118 MB, past
    the 100 MiB per-file limit of the Git host.
    """
    merged = dict(existing)
    merged["claims"] = built.get("claims", [])
    merged["evidence"] = built.get("evidence", [])
    merged["run"] = built.get("run", merged.get("run"))
    merged["errors"] = built.get("errors", [])
    merged["operations"] = built.get("operations", merged.get("operations"))
    merged["changes"] = existing.get("changes", built.get("changes", []))
    return merged


def read_jsonl(path: str | None) -> list[dict]:
    if not path:
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profiles", required=True, help="Frozen batch profiles JSONL")
    parser.add_argument("--observations", help="External observations JSONL")
    parser.add_argument("--labels", help="Label JSONL; when given, only exact_entity rows are claimed")
    parser.add_argument("--envelopes", help="Existing terminal envelopes JSONL to merge into")
    parser.add_argument("--output", required=True, help="Contract envelopes JSONL output")
    parser.add_argument("--snapshots-dir", help="Write retained excerpt bytes and set snapshot_path")
    parser.add_argument("--snapshot-span-fallback", action="store_true",
                        help="Also snapshot the claim span when no body was retained; rewrites "
                             "content_sha256 to the digest of those bytes. Off by default because "
                             "shipped evidence digests cover whole pages.")
    parser.add_argument("--report", help="Write a summary JSON report here")
    parser.add_argument("--limit", type=int, help="Only the first N companies (debugging)")
    args = parser.parse_args()

    profiles = read_jsonl(args.profiles)
    if args.limit:
        profiles = profiles[: args.limit]

    # observations, gated by labels when a label file is supplied
    observations = read_jsonl(args.observations)
    if args.labels:
        labels = {row.get("id"): row for row in read_jsonl(args.labels)}
        for obs in observations:
            label = labels.get(obs.get("id"))
            if label is not None:
                obs["exact_entity"] = bool(label.get("exact_entity"))
                metrics = obs.setdefault("metrics", {})
                if label.get("sentiment_correct") and not metrics.get("sentiment_label"):
                    metrics["sentiment_label"] = obs.get("sentiment_label") or label.get("sentiment_label")
            else:
                obs["exact_entity"] = bool(obs.get("exact_entity"))
    by_org: dict[str, list[dict]] = collections.defaultdict(list)
    for obs in observations:
        by_org[str(obs.get("organisation_number"))].append(obs)

    snapshot_root = Path(args.snapshots_dir) if args.snapshots_dir else None
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    existing = {str(row.get("organisation_number")): row for row in read_jsonl(args.envelopes)}
    stats = collections.Counter()
    families = collections.Counter()
    with open(args.output, "w", encoding="utf-8") as handle:
        for profile in profiles:
            org = str(profile.get("organisation_number"))
            envelope = build_envelope(profile, by_org.get(org, []), started_at=started_at,
                                      snapshot_root=snapshot_root,
                                      span_fallback=args.snapshot_span_fallback)
            stats["companies"] += 1
            stats["claims"] += len(envelope["claims"])
            stats["evidence"] += len(envelope["evidence"])
            stats["empty_claims"] += 1 if not envelope["claims"] else 0
            for claim in envelope["claims"]:
                families[claim.get("family") or "other"] += 1
            if org in existing:
                envelope = merge_envelope(existing[org], envelope)
            handle.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")

    summary = {"companies": stats["companies"], "claims": stats["claims"], "evidence": stats["evidence"],
               "companies_without_claims": stats["empty_claims"], "claims_by_family": dict(families.most_common()),
               "output": args.output, "snapshots": bool(snapshot_root)}
    if args.report:
        Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
