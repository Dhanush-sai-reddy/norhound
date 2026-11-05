#!/usr/bin/env python3
"""Keyless Fagfolkguiden directory connector (sitemap-driven, strict identity).

Discovery follows the site's own declarations: ``robots.txt`` names the public
sitemaps, the sitemaps list the ``/bedrift/<slug>-<orgnr>`` listing pages, and a
listing page is published only when the page itself proves the exact legal
entity:

* the page's schema.org ``identifier`` equals the requested 9-digit organisation
  number exactly, and
* the page's ``name`` equals the BRREG legal name after legal-form
  normalisation.

No API key, no login, robots-allowed public pages only. ``--offline`` runs the
same pipeline from cached sitemaps and cached pages and reports every cache
miss explicitly instead of silently skipping a company.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup


UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
BASE = "https://www.fagfolkguiden.no"
ROBOTS_URL = f"{BASE}/robots.txt"
ROBOTS_NOTE = "Public /bedrift/ pages allowed; /api/ disallowed and not used"
DIRECTORY_HOSTS = {"fagfolkguiden.no", "www.fagfolkguiden.no"}
ALLOWED_NODE_TYPES = {"LocalBusiness", "Organization", "Store"}
MAX_BYTES = 4_000_000

# A listing lives at /bedrift/<slug>-<9 digit organisation number>.
LISTING_PATH_RE = re.compile(r"^/bedrift/(?P<slug>[^/?#]+?)-(?P<org>\d{9})/?$")
SITEMAP_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")

# Legal forms that may sit as one trailing token of a registered name.
LEGAL_FORM_SUFFIXES = (
    "a/s", "ab", "ans", "aps", "asa", "as", "ba", "co", "corp", "da", "enk",
    "gmbh", "ag", "bv", "i/s", "inc", "k/s", "kf", "limited", "ltd", "llc",
    "llp", "lp", "nv", "oy", "oyj", "p/s", "plc", "reg", "sa", "sarl", "sp",
    "spa", "srl", "ug",
)
TRANSLITERATION = str.maketrans({"ø": "o", "å": "a", "æ": "ae"})


def slug(value: object) -> str:
    text = str(value or "").translate(str.maketrans({"ø": "o", "å": "a", "æ": "ae", "Ø": "O", "Å": "A", "Æ": "AE"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return "-".join(re.findall(r"[a-z0-9]+", text))


def normalize_legal_name(value: object) -> str:
    """Transliterate, lowercase and drop one trailing legal-form token."""
    text = str(value or "").casefold().translate(TRANSLITERATION)
    text = re.sub(r"\s+", " ", text).strip()
    for form in LEGAL_FORM_SUFFIXES:
        if text == form:
            candidate = ""
        elif text.endswith(" " + form):
            candidate = text[: -len(form)].strip()
        else:
            continue
        if candidate:
            text = candidate
        break
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def rating_to_label(rating: float) -> str:
    if rating >= 4.0:
        return "positive"
    if rating >= 3.0:
        return "neutral"
    return "negative"


def sitemap_urls_from_robots(robots_text: str) -> list[str]:
    """The sitemap URLs declared by robots.txt, in declaration order."""
    urls: list[str] = []
    for line in str(robots_text or "").splitlines():
        line = line.strip()
        if not line.lower().startswith("sitemap:"):
            continue
        url = line.split(":", 1)[1].strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def sitemap_locs(xml_text: str) -> list[str]:
    return [match.strip() for match in SITEMAP_LOC_RE.findall(str(xml_text or "")) if match.strip()]


def listing_map_from_sitemap(xml_text: str) -> dict[str, str]:
    """Map organisation number -> listing URL for every /bedrift/<slug>-<org>."""
    mapping: dict[str, str] = {}
    for url in sitemap_locs(xml_text):
        match = LISTING_PATH_RE.match(urlparse(url).path)
        if match:
            mapping.setdefault(match.group("org"), url)
    return mapping


def sitemap_cache_name(url: str) -> str:
    """Stable cache file name for a sitemap URL (path only, no host)."""
    path = urlparse(url).path.strip("/")
    stem = path[:-4] if path.lower().endswith(".xml") else path
    return stem.replace("/", "-").replace(" ", "_") or "sitemap"


def _iter_jsonld(raw: bytes):
    """Yield (node, script_text) for every schema.org node in the page."""
    soup = BeautifulSoup(raw, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text() or ""
        try:
            data = json.loads(text)
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            yield candidate, text
            graph = candidate.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    if isinstance(item, dict):
                        yield item, text


def extract_jsonld_nodes(raw: bytes) -> list[dict]:
    return [node for node, _text in _iter_jsonld(raw)]


def select_listing_node(raw: bytes) -> tuple[dict | None, str | None]:
    """The first LocalBusiness/Organization/Store node and the script it came from."""
    for node, text in _iter_jsonld(raw):
        types = node.get("@type")
        if isinstance(types, str):
            types = [types]
        if not isinstance(types, list):
            continue
        if any(str(item) in ALLOWED_NODE_TYPES for item in types):
            return node, text
    return None, None


def identifier_value(node: dict) -> str:
    """The organisation number stated by the page's schema.org identifier."""
    identifier = node.get("identifier")
    candidates = identifier if isinstance(identifier, list) else [identifier]
    for item in candidates:
        if isinstance(item, dict):
            value = item.get("value")
            values = value if isinstance(value, list) else [value]
            for entry in values:
                if entry is not None and str(entry).strip():
                    return str(entry).strip()
        elif item is not None and str(item).strip():
            return str(item).strip()
    return ""


def sane_rating(node: dict) -> tuple[float, int] | None:
    """The aggregate rating of a listing node when it is usable (0 < r <= 5, count > 0)."""
    rating = node.get("aggregateRating")
    if not isinstance(rating, dict):
        return None
    try:
        value = float(rating.get("ratingValue"))
    except (TypeError, ValueError):
        return None
    raw_count = rating.get("ratingCount")
    if raw_count in (None, "", 0):
        raw_count = rating.get("reviewCount")
    try:
        count = int(float(raw_count))
    except (TypeError, ValueError):
        return None
    if not (0 < value <= 5) or count <= 0:
        return None
    return value, count


def extract_aggregate_rating(raw: bytes) -> tuple[float, int, str | None]:
    """Legacy helper: the first usable aggregate rating plus a review link."""
    soup = BeautifulSoup(raw, "html.parser")
    for node, _text in _iter_jsonld(raw):
        rating = sane_rating(node)
        if rating:
            review_link = soup.find("a", href=re.compile(r"search\.google\.com/local/reviews"))
            return rating[0], rating[1], review_link.get("href") if review_link else None
    for node in soup.find_all(attrs={"itemtype": re.compile(r"schema\.org/(Organization|LocalBusiness)")}):
        rating_node = node.find(attrs={"itemprop": "aggregateRating"})
        if not rating_node:
            continue
        value = rating_node.find(attrs={"itemprop": "ratingValue"})
        count = rating_node.find(attrs={"itemprop": "reviewCount"}) or rating_node.find(attrs={"itemprop": "ratingCount"})
        if value and count:
            raw_value = value.get("content") or value.get_text(strip=True)
            raw_count = count.get("content") or count.get_text(strip=True)
            try:
                parsed = float(raw_value)
                parsed_count = int(float(raw_count))
            except (TypeError, ValueError):
                continue
            if 0 < parsed <= 5 and parsed_count > 0:
                return parsed, parsed_count, None
    raise ValueError("no aggregate rating")


def raw_value_span(script_text: str, key: str) -> str | None:
    """The exact source text of a JSON-LD key/value pair, without prose."""
    marker = script_text.find(f'"{key}"')
    if marker < 0:
        return None
    index = marker + len(key) + 2
    while index < len(script_text) and script_text[index] in " \t\r\n:":
        index += 1
    if index >= len(script_text):
        return None
    char = script_text[index]
    if char == "{":
        depth = 0
        in_string = False
        escaped = False
        for position in range(index, len(script_text)):
            current = script_text[position]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    return script_text[marker: position + 1]
        return None
    if char == '"':
        end = script_text.find('"', index + 1)
        return script_text[marker: end + 1] if end >= 0 else None
    end = index
    while end < len(script_text) and script_text[end] not in ",}":
        end += 1
    return script_text[marker:end]


def website_domain(node: dict) -> str | None:
    """The company's own website, as stated by the listing's sameAs."""
    same_as = node.get("sameAs")
    values = same_as if isinstance(same_as, list) else [same_as]
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        candidate = text if "://" in text else f"http://{text}"
        host = (urlparse(candidate).hostname or "").strip().lower()
        if host:
            return host.removeprefix("www.")
    return None


def address_metrics(node: dict) -> dict:
    address = node.get("address")
    if not isinstance(address, dict):
        address = {}
    return {
        "street": address.get("streetAddress"),
        "locality": address.get("addressLocality"),
        "postal_code": address.get("postalCode"),
    }


def build_observations(
    org: str,
    profile_name: str,
    node: dict,
    listing_url: str,
    raw: bytes,
    retrieved_at: str,
    script_text: str = "",
) -> list[dict]:
    """The profile/review/sentiment rows for one identity-proved listing page."""
    content_digest = hashlib.sha256(raw).hexdigest()
    url_digest = hashlib.sha256(listing_url.encode("utf-8")).hexdigest()[:16]
    rating = sane_rating(node)
    metrics: dict = {"scale": 5}
    if rating:
        metrics["rating"] = rating[0]
        metrics["review_count"] = rating[1]
    metrics["website_domain"] = website_domain(node)
    metrics["address"] = address_metrics(node)
    proof = [
        {"type": "exact_organisation_number_on_directory_page", "value": org},
        {
            "type": "exact_legal_name_on_directory_page",
            "value": str(node.get("name") or ""),
            "matched_organisation_number": org,
        },
    ]
    common = {
        "organisation_number": org,
        "platform": "company_directory",
        "source_url": listing_url,
        "retrieved_at": retrieved_at,
        "content_sha256": content_digest,
        "exact_entity": True,
        "identity_proof": proof,
        "acquisition_mode": "permitted_public_page",
        "rights_status": "approved",
        "metrics": dict(metrics),
    }
    evidence_span = (raw_value_span(script_text, "aggregateRating") if rating else None) or raw_value_span(script_text, "identifier")
    rows = [
        {
            **common,
            "id": f"fagfolk-profile-{org}-{url_digest}",
            "signal_type": "profile_metrics",
            "strategy": "directory_profile_metrics",
            "source_class": "company_directory",
            "evidence_span": evidence_span,
        },
    ]
    if not rating:
        return rows
    label = rating_to_label(rating[0])
    rows.append(
        {
            **common,
            "id": f"fagfolk-review-{org}-{url_digest}",
            "signal_type": "review_summary",
            "strategy": "directory_rating_reviews",
            "source_class": "customer_review",
            "evidence_span": evidence_span,
        }
    )
    rows.append(
        {
            **common,
            "id": f"fagfolk-sentiment-{org}-{url_digest}",
            "signal_type": "sentiment",
            "strategy": "directory_review_sentiment",
            "source_class": "customer_review",
            "sentiment_label": label,
            "sentiment_model_version": "rule-based-v1",
            "evidence_span": evidence_span,
        }
    )
    return rows


def http_fetch(url: str, timeout: int = 25) -> tuple[bytes, str]:
    """Fetch a public page; returns the body and the URL actually retrieved."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BYTES)
        final_url = response.geturl() if hasattr(response, "geturl") else url
    return body, final_url


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_from_mtime(path: Path) -> str:
    stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return stamp.isoformat().replace("+00:00", "Z")


def _on_directory_host(url: str) -> bool:
    return (urlparse(str(url or "")).hostname or "").lower() in DIRECTORY_HOSTS


def discover_sitemap_listings(
    cache_dir: Path,
    *,
    offline: bool = False,
    fetcher=None,
    timeout: int = 25,
) -> tuple[dict[str, str], dict]:
    """Read robots.txt, fetch the declared sitemaps and map org -> listing URL."""
    fetch = fetcher or (lambda url: http_fetch(url, timeout))
    cache_dir = Path(cache_dir)
    sitemaps_dir = cache_dir / "sitemaps"
    sitemaps_dir.mkdir(parents=True, exist_ok=True)
    robots_path = cache_dir / "robots.txt"
    declared: list[str] = []
    errors: list[str] = []
    misses = 0
    robots_cached = False
    if offline:
        if robots_path.exists():
            robots_cached = True
            declared = sitemap_urls_from_robots(robots_path.read_text(encoding="utf-8", errors="replace"))
        else:
            misses += 1
            errors.append("robots.txt missing from cache: sitemap declarations unknown")
    else:
        try:
            body, _final = fetch(ROBOTS_URL)
            robots_path.write_bytes(body)
            robots_cached = True
            declared = sitemap_urls_from_robots(body.decode("utf-8", errors="replace"))
        except Exception as exc:
            errors.append(f"robots.txt fetch failed: {type(exc).__name__}: {str(exc)[:120]}")
            declared = [f"{BASE}/sitemap.xml"]

    listing_map: dict[str, str] = {}
    cached_names: list[str] = []
    pending = list(declared)
    seen: set[str] = set()
    while pending:
        url = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)
        name = sitemap_cache_name(url)
        path = sitemaps_dir / f"{name}.xml"
        if offline:
            if not path.exists():
                misses += 1
                errors.append(f"sitemap cache miss: {url}")
                continue
            body = path.read_bytes()
        else:
            try:
                body, _final = fetch(url)
            except Exception as exc:
                misses += 1
                errors.append(f"sitemap fetch failed: {url}: {type(exc).__name__}")
                continue
            path.write_bytes(body)
        cached_names.append(name)
        text = body.decode("utf-8", errors="replace")
        if "<sitemapindex" in text:
            for child in sitemap_locs(text):
                if child not in seen:
                    pending.append(child)
            continue
        for org, listing in listing_map_from_sitemap(text).items():
            listing_map.setdefault(org, listing)

    if offline:
        # A cached sitemap that robots.txt does not mention is still usable.
        for path in sorted(sitemaps_dir.glob("*.xml")):
            if path.stem in cached_names:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "<sitemapindex" in text:
                continue
            cached_names.append(path.stem)
            for org, listing in listing_map_from_sitemap(text).items():
                listing_map.setdefault(org, listing)

    stats = {
        "declared": declared,
        "cached": cached_names,
        "listing_urls": len(listing_map),
        "robots_cached": robots_cached,
        "cache_misses": misses,
        "errors": errors,
    }
    return listing_map, stats


def process_organisation(
    org: str,
    profile: dict,
    listing_url: str,
    cache_dir: Path,
    *,
    offline: bool,
    fetcher,
) -> tuple[list[dict], dict]:
    """Fetch (or read from cache) one listing page and publish its rows."""
    cache_path = Path(cache_dir) / f"{org}.html"
    status: dict = {"organisation_number": org, "accepted": False, "listing_found": False}
    final_url = listing_url
    if offline:
        if not cache_path.exists():
            status["reason"] = "page_cache_miss"
            status["requested_url"] = listing_url
            return [], status
        raw = cache_path.read_bytes()
        retrieved_at = _iso_from_mtime(cache_path)
        status["cache_hit"] = True
    else:
        try:
            raw, final_url = fetcher(listing_url)
        except urllib.error.HTTPError as exc:
            status["reason"] = "no_listing" if exc.code in (404, 410) else "page_fetch_error"
            status["error"] = f"HTTP {exc.code}"
            status["requested_url"] = listing_url
            return [], status
        except Exception as exc:
            status["reason"] = "page_fetch_error"
            status["error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
            status["requested_url"] = listing_url
            return [], status
        try:
            cache_path.write_bytes(raw)
        except OSError as exc:
            status["cache_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        retrieved_at = _now_iso()
        status["cache_hit"] = False
        final_url = final_url if _on_directory_host(final_url) else listing_url

    node, script_text = select_listing_node(raw)
    if node is None:
        status["reason"] = "no_listing"
        status["requested_url"] = listing_url
        return [], status
    status["listing_found"] = True
    # The listing states its own canonical URL; prefer it so that the row id is
    # identical whether the page came from the sitemap, the fallback URL or cache.
    canonical = str(node.get("url") or node.get("@id") or "")
    if _on_directory_host(canonical):
        resolved_url = canonical
    else:
        resolved_url = final_url if not offline else listing_url

    page_org = identifier_value(node)
    page_name = str(node.get("name") or "").strip()
    status["page_organisation_number"] = page_org
    status["page_name"] = page_name
    if page_org != org:
        status["reason"] = "org_number_mismatch"
        return [], status
    expected_name = str((profile or {}).get("name") or "").strip()
    if not expected_name:
        status["reason"] = "profile_name_missing"
        return [], status
    if normalize_legal_name(page_name) != normalize_legal_name(expected_name):
        status["reason"] = "legal_name_mismatch"
        status["profile_name"] = expected_name
        return [], status

    rows = build_observations(org, expected_name, node, resolved_url, raw, retrieved_at, script_text or "")
    status["accepted"] = True
    status["rated"] = any(row["signal_type"] == "review_summary" for row in rows)
    status["listing_url"] = resolved_url
    return rows, status


def run_connector(
    *,
    profiles: dict[str, dict],
    wanted: list[str],
    cache_dir: Path,
    offline: bool = False,
    workers: int = 4,
    fetcher=None,
    timeout: int = 25,
    min_interval: float = 0.0,
) -> tuple[list[dict], dict]:
    """Run the connector over the requested organisations."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetch = fetcher or (lambda url: http_fetch(url, timeout))
    listing_map, discovery = discover_sitemap_listings(
        cache_dir, offline=offline, fetcher=fetch, timeout=timeout
    )

    organisations: list[str] = []
    for org in wanted:
        org = str(org).strip()
        if org and org not in organisations:
            organisations.append(org)

    def work(org: str) -> tuple[list[dict], dict]:
        if min_interval > 0 and not offline:
            time.sleep(min_interval)
        listing_url = listing_map.get(org) or f"{BASE}/bedrift/{org}"
        return process_organisation(
            org,
            (profiles or {}).get(org, {}),
            listing_url,
            cache_dir,
            offline=offline,
            fetcher=fetch,
        )

    rows: list[dict] = []
    statuses: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers or 1), 8))) as pool:
        for org_rows, org_status in pool.map(work, organisations):
            rows.extend(org_rows)
            statuses.append(org_status)

    order = {org: index for index, org in enumerate(organisations)}
    rows.sort(key=lambda row: (order.get(row["organisation_number"], 0), row["signal_type"]))
    statuses.sort(key=lambda row: order.get(row["organisation_number"], 0))

    rejected_by_reason: dict[str, int] = {}
    for status in statuses:
        if status.get("accepted"):
            continue
        reason = str(status.get("reason") or "unknown")
        rejected_by_reason[reason] = rejected_by_reason.get(reason, 0) + 1
    signal_counts: dict[str, int] = {}
    for row in rows:
        signal = str(row.get("signal_type") or "")
        signal_counts[signal] = signal_counts.get(signal, 0) + 1
    page_misses = rejected_by_reason.get("page_cache_miss", 0)
    accepted = sum(1 for status in statuses if status.get("accepted"))
    report = {
        "connector": "fagfolkguiden_directory_sitemap_v2",
        "offline": bool(offline),
        "orgs_requested": len(organisations),
        "orgs_with_listing": sum(1 for status in statuses if status.get("listing_found")),
        "orgs_accepted": accepted,
        "orgs_rejected": len(organisations) - accepted,
        "rejected_by_reason": rejected_by_reason,
        "orgs_with_rating": sum(1 for status in statuses if status.get("rated")),
        "observations": len(rows),
        "observations_by_signal_type": signal_counts,
        "cache_misses": {"sitemap": int(discovery.get("cache_misses") or 0), "page": page_misses},
        "robots_note": ROBOTS_NOTE,
        "robots_cached": bool(discovery.get("robots_cached")),
        "sitemaps": {
            "declared": discovery.get("declared", []),
            "cached": discovery.get("cached", []),
            "listing_urls": discovery.get("listing_urls", 0),
        },
        "errors": sum(1 for status in statuses if status.get("error")),
        "discovery_errors": list(discovery.get("errors") or []),
        # Legacy keys kept so older report readers keep working.
        "companies": len(organisations),
        "exact_pages": accepted,
        "rated_companies": sum(1 for status in statuses if status.get("rated")),
        "robots_checked": ROBOTS_NOTE,
        "company_results": statuses,
    }
    return rows, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exact-entity Fagfolkguiden directory rows from sitemap-discovered public pages."
    )
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--organisations", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--offline", action="store_true", help="Use cached sitemaps and pages only; never touch the network")
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--min-interval", type=float, default=0.2, help="Seconds between page requests")
    args = parser.parse_args()

    wanted = [line.strip() for line in Path(args.organisations).read_text(encoding="utf-8").splitlines() if line.strip()]
    profiles = {
        str(row["organisation_number"]): row
        for row in (
            json.loads(line)
            for line in Path(args.profiles).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    rows, report = run_connector(
        profiles=profiles,
        wanted=wanted,
        cache_dir=Path(args.cache),
        offline=args.offline,
        workers=args.workers,
        timeout=args.timeout,
        min_interval=args.min_interval,
    )
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "company_results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
