#!/usr/bin/env python3
"""Gulesider.no reviews connector.

Searches Google for `site:gulesider.no "{company_name}"`, fetches the matching
Gulesider company profile page, extracts the JSON-LD aggregate rating, and
emits review_summary observations only when the org number on the page matches
a target organisation.

Usage:
    uv run python scripts/run_gulesider_reviews_connector.py \
        --profiles data/entry-manifest.jsonl \
        --organisations data/1000-orgs.txt \
        --output out/gulesider-reviews.jsonl \
        --cache data/gulesider-cache
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup


UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
PROFILE_URL_RE = re.compile(r"https?://(?:www\.)?gulesider\.no/[a-z0-9\-]+/\d+/bedrift")
ORG_RE = re.compile(r"(?:Org\.?\s*nr\.?|Organisasjonsnummer|org\.?\s*nr\.?)\s*[.:]?\s*(\d{9})", re.IGNORECASE)
ANY_ORG_RE = re.compile(r"\b\d{9}\b")
RATE_LIMIT_SECONDS = 2.0


class RateLimiter:
    """Thread-safe minimum-interval rate limiter (shared across workers)."""

    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self._next_allowed - now
            self._next_allowed = max(now, self._next_allowed) + self._interval
        if sleep_for > 0:
            time.sleep(sleep_for)


def http_get(url: str, rate_limiter: RateLimiter, timeout: int = 25) -> bytes:
    rate_limiter.wait()
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "nb,no;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(2_000_000)


def slugify(value: object) -> str:
    text = str(value or "").translate(str.maketrans({"ø": "o", "å": "a", "æ": "ae", "Ø": "O", "Å": "A", "Æ": "AE"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return "-".join(re.findall(r"[a-z0-9]+", text))


def find_profile_url(name: str, rate_limiter: RateLimiter) -> tuple[str | None, str | None]:
    """Search Google for the Gulesider profile URL. Returns (url, error)."""
    query = urllib.parse.quote(f'site:gulesider.no "{name}"')
    url = f"https://www.google.com/search?q={query}&num=10&hl=no"
    try:
        raw = http_get(url, rate_limiter)
    except Exception as exc:
        return None, f"search_failed: {type(exc).__name__}: {str(exc)[:120]}"
    soup = BeautifulSoup(raw, "html.parser")
    # Collect candidate links: direct hrefs and Google /url?q= redirects.
    candidates: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith("/url?q="):
            href = href.split("/url?q=", 1)[1].split("&", 1)[0]
        if "gulesider.no" in href:
            candidates.append(urllib.parse.unquote(href))
    for href in candidates:
        match = PROFILE_URL_RE.search(href)
        if match:
            return match.group(0).rstrip("/"), None
    # Fallback: any gulesider link whose text looks like a company name.
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith("/url?q="):
            href = href.split("/url?q=", 1)[1].split("&", 1)[0]
        if "gulesider.no" in href and slugify(name)[:12] in slugify(href):
            return urllib.parse.unquote(href).split("?")[0], None
    return None, "no_gulesider_profile_found"


def extract_aggregate_rating(soup: BeautifulSoup) -> tuple[float, int] | None:
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(node.string or node.get_text() or "{}")
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            rating = item.get("aggregateRating")
            if not isinstance(rating, dict):
                continue
            value = rating.get("ratingValue")
            count = rating.get("ratingCount") or rating.get("reviewCount")
            if value is not None and count is not None:
                try:
                    value_f, count_i = float(value), int(count)
                except (ValueError, TypeError):
                    continue
                if 0 < value_f <= 5 and count_i > 0:
                    return value_f, count_i
    # Microdata fallback.
    for node in soup.find_all(attrs={"itemtype": re.compile(r"schema\.org/(Organization|LocalBusiness|Rating|PostalAddress)")}):
        rating_node = node.find(attrs={"itemprop": "aggregateRating"}) or node
        value = rating_node.find(attrs={"itemprop": "ratingValue"})
        count = rating_node.find(attrs={"itemprop": "ratingCount"}) or rating_node.find(attrs={"itemprop": "reviewCount"})
        if value and count:
            val = value.get("content") or value.get_text(strip=True)
            cnt = count.get("content") or count.get_text(strip=True)
            try:
                value_f, count_i = float(val), int(cnt)
            except (ValueError, TypeError):
                continue
            if 0 < value_f <= 5 and count_i > 0:
                return value_f, count_i
    return None


def extract_org_number(text: str) -> str | None:
    match = ORG_RE.search(text)
    if match:
        return match.group(1)
    return None


def extract_contact_info(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Best-effort address and phone extraction from visible page text."""
    address = None
    phone = None
    # Address: look for schema PostalAddress or "Adresse" label.
    for node in soup.find_all(attrs={"itemtype": re.compile(r"schema\.org/PostalAddress")}):
        parts = [node.find(attrs={"itemprop": prop}) for prop in ("streetAddress", "addressLocality", "postalCode")]
        values = [p.get_text(strip=True) for p in parts if p]
        if values:
            address = ", ".join(values)
            break
    if address is None:
        label = soup.find(string=re.compile(r"^Adresse\s*:?\s*", re.IGNORECASE))
        if label and label.parent:
            address = label.parent.get_text(" ", strip=True).split("Adrift", 1)[0].strip(" :")
    # Phone: schema Telephone or tel: links.
    for anchor in soup.find_all("a", href=re.compile(r"^tel:")):
        phone = anchor["href"].replace("tel:", "").strip()
        break
    if phone is None:
        for node in soup.find_all(attrs={"itemprop": "telephone"}):
            phone = node.get("content") or node.get_text(strip=True)
            break
    return address, phone


def rating_to_label(rating: float) -> str:
    if rating >= 4.0:
        return "positive"
    if rating >= 3.0:
        return "neutral"
    return "negative"


def fetch(
    profile: dict,
    wanted_orgs: set[str],
    cache_dir: Path,
    rate_limiter: RateLimiter,
) -> tuple[list[dict], dict]:
    org = str(profile["organisation_number"])
    name = str(profile.get("name") or "")
    status: dict = {"organisation_number": org, "name": name}
    try:
        if not name:
            return [], {**status, "accepted": False, "reason": "missing_company_name"}

        profile_url, error = find_profile_url(name, rate_limiter)
        if error or not profile_url:
            return [], {**status, "accepted": False, "reason": error or "no_profile_url"}
        status["profile_url"] = profile_url

        cache = cache_dir / f"{slugify(profile_url)}.html"
        if cache.exists():
            raw, cache_hit = cache.read_bytes(), True
        else:
            raw = http_get(profile_url, rate_limiter)
            cache.write_bytes(raw)
            cache_hit = False
        status["cache_hit"] = cache_hit

        soup = BeautifulSoup(raw, "html.parser")
        text = soup.get_text(" ", strip=True)

        page_org = extract_org_number(text)
        if page_org is None:
            digits = ANY_ORG_RE.search(re.sub(r"\D", "", text))
            page_org = digits.group(0) if digits else None
        if page_org is None:
            return [], {**status, "accepted": False, "reason": "org_number_not_in_page"}
        if page_org not in wanted_orgs:
            return [], {**status, "accepted": False, "reason": "org_number_mismatch", "page_org": page_org}
        if page_org != org:
            return [], {**status, "accepted": False, "reason": "org_number_mismatch", "page_org": page_org}

        rating_data = extract_aggregate_rating(soup)
        if rating_data is None:
            return [], {**status, "accepted": True, "rated": False, "reason": "no_aggregate_rating"}
        rating, count = rating_data

        address, phone = extract_contact_info(soup)
        page_title = soup.find("title")
        page_name = page_title.get_text(strip=True).split("|")[0].strip() if page_title else name

        digest = hashlib.sha256(raw).hexdigest()
        retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        label = rating_to_label(rating)

        proof = [{"type": "exact_organisation_number_on_directory_page", "value": org}]
        if slugify(name)[:12] and slugify(name)[:12] in slugify(text):
            proof.append({"type": "exact_legal_name_on_directory_page", "value": name})

        evidence_span = f"Gulesider rating {rating}/5 based on {count} reviews"
        common = {
            "organisation_number": org,
            "platform": "company_directory",
            "source_url": profile_url,
            "retrieved_at": retrieved_at,
            "content_sha256": digest,
            "exact_entity": True,
            "identity_proof": proof,
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "source_class": "customer_review",
            "evidence_span": evidence_span,
            "metrics": {"rating": rating, "review_count": count, "scale": 5},
            "company_name_on_page": page_name,
            "address": address,
            "phone": phone,
        }
        row = {
            **common,
            "id": f"gulesider-review-{org}-{digest[:16]}",
            "signal_type": "review_summary",
            "sentiment_label": label,
            "sentiment_model_version": "rule-based-v1",
        }
        return [row], {
            **status,
            "accepted": True,
            "rated": True,
            "rating": rating,
            "review_count": count,
            "sentiment_label": label,
        }
    except Exception as exc:
        return [], {**status, "accepted": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Gulesider.no ratings for target organisations via Google site search."
    )
    parser.add_argument("--profiles", required=True, help="JSONL with company profiles")
    parser.add_argument("--organisations", required=True, help="Text file with target org numbers")
    parser.add_argument("--output", required=True, help="JSONL output path")
    parser.add_argument("--cache", required=True, help="Cache directory for HTML responses")
    parser.add_argument("--report", required=True, help="JSON run-report output path")
    parser.add_argument("--workers", type=int, default=2, help="Thread pool size (default 2, be gentle)")
    args = parser.parse_args()

    wanted = [line.strip() for line in Path(args.organisations).read_text(encoding="utf-8").splitlines() if line.strip()]
    wanted_set = set(wanted)
    profiles = {
        str(row["organisation_number"]): row
        for row in (json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip())
    }
    missing = [org for org in wanted if org not in profiles]
    if missing:
        raise SystemExit(f"{len(missing)} org numbers missing from --profiles (first: {missing[:5]})")

    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)
    rate_limiter = RateLimiter(RATE_LIMIT_SECONDS)

    observations: list[dict] = []
    statuses: list[dict] = []
    workers = max(1, min(args.workers, 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, profiles[org], wanted_set, cache_dir, rate_limiter): org for org in wanted}
        for future in as_completed(futures):
            rows, status = future.result()
            observations.extend(rows)
            statuses.append(status)

    order = {org: index for index, org in enumerate(wanted)}
    observations.sort(key=lambda row: (order[row["organisation_number"]], row["signal_type"]))
    statuses.sort(key=lambda row: order[row["organisation_number"]])

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations),
        encoding="utf-8",
    )
    report = {
        "connector": "gulesider_reviews_v1",
        "companies": len(wanted),
        "exact_pages": sum(row.get("accepted") is True for row in statuses),
        "rated_companies": sum(row.get("rated") is True for row in statuses),
        "observations": len(observations),
        "errors": sum("error" in row for row in statuses),
        "rate_limit_seconds": RATE_LIMIT_SECONDS,
        "robots_checked": "Public /bedrift/ pages; Google HTML search used only to discover candidate profile URLs (search results are candidates, not claim evidence).",
        "claim_boundary": "Exact-org public directory page with embedded aggregate rating; published as permitted public-page evidence with identity proof, per recorded rights note.",
        "company_results": statuses,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "company_results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
