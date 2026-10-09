#!/usr/bin/env python3
"""Instagram profile connector — discovers and scrapes company Instagram profiles.

Discovers Instagram profile URLs from company website HTML, scrapes profile
data via the Apify Instagram Profile Scraper Actor, and matches profiles to
companies by domain or name.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

UA = "NorHound/1.0 (+https://github.com/Dhanush-sai-reddy/norhound)"
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
APIFY_ACTOR_URL = "https://api.apify.com/v2/acts/apify~instagram-profile-scraper/run-sync-get-dataset-items"
REQUEST_DELAY = 2.0
MAX_HTML_BYTES = 5_000_000
HTTP_TIMEOUT = 25

logger = logging.getLogger("instagram_connector")


def slug(value: object) -> str:
    """Normalise a string for comparison."""
    text = str(value or "").translate(str.maketrans({"ø": "o", "å": "a", "æ": "ae", "Ø": "O", "Å": "A", "Æ": "AE"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return "-".join(re.findall(r"[a-z0-9]+", text))


def extract_domain(url: object) -> str:
    """Extract hostname from a URL, stripping www."""
    raw = str(url or "")
    if "://" not in raw:
        raw = "https://" + raw
    hostname = (urlparse(raw).hostname or "").casefold()
    return hostname.removeprefix("www.")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_html(url: str, cache_dir: Path, org: str) -> tuple[bytes, bool]:
    """Fetch HTML with caching. Returns (raw_bytes, cache_hit)."""
    cache_file = cache_dir / f"{org}.html"
    if cache_file.exists():
        return cache_file.read_bytes(), True
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        raw = response.read(MAX_HTML_BYTES)
    cache_file.write_bytes(raw)
    return raw, False


def extract_instagram_urls(html: bytes) -> list[str]:
    """Extract Instagram profile URLs from HTML source."""
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if "instagram.com/" in href:
            # Normalise: strip query params, trailing slashes
            parsed = urlparse(href)
            path = parsed.path.rstrip("/")
            # Skip non-profile paths (p/, reel/, explore/, stories/)
            if re.match(r"^/[\w.]+$", path) and not any(
                path.startswith(f"/{p}") for p in ("p", "reel", "reels", "explore", "stories", "tv", "direct")
            ):
                clean_url = f"https://www.instagram.com{path}"
                urls.add(clean_url)
    return sorted(urls)


def scrape_instagram_profiles(usernames: list[str], cache_dir: Path) -> dict[str, dict]:
    """Scrape Instagram profiles via Apify Actor. Returns {username: data}."""
    if not usernames:
        return {}
    cache_file = cache_dir / "instagram_profiles.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    result: dict[str, dict] = {}
    batch_size = 10
    for i in range(0, len(usernames), batch_size):
        batch = usernames[i:i + batch_size]
        payload = json.dumps({"usernames": batch}).encode("utf-8")
        request = urllib.request.Request(
            APIFY_ACTOR_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {APIFY_TOKEN}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    raw = response.read()
                data = json.loads(raw)
                profiles = data if isinstance(data, list) else data.get("data", [])
                for profile in profiles:
                    username = profile.get("username") or profile.get("userName") or ""
                    if username:
                        result[username.lower()] = profile
                break
            except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as exc:
                logger.warning("Apify Instagram scrape failed (attempt %d): %s", attempt + 1, exc)
                if attempt < 2:
                    time.sleep(5)
        time.sleep(REQUEST_DELAY)

    cache_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def match_profile_to_company(
    ig_username: str,
    ig_data: dict,
    company_domain: str,
    company_name: str,
) -> tuple[bool, list[dict]]:
    """Match an Instagram profile to a company by domain or name."""
    proof: list[dict] = []
    bio = str(ig_data.get("biography") or ig_data.get("bio") or "")
    external_url = str(ig_data.get("externalUrl") or ig_data.get("external_url") or "")
    full_name = str(ig_data.get("fullName") or ig_data.get("full_name") or "")

    # Domain match: check bio and external URL for company domain
    if company_domain:
        domain_parts = company_domain.split(".")
        core_domain = domain_parts[0] if domain_parts else company_domain
        bio_lower = bio.casefold()
        ext_lower = external_url.casefold()
        if core_domain in bio_lower or core_domain in ext_lower:
            proof.append({"type": "domain_match", "value": company_domain})
        elif company_domain in bio_lower or company_domain in ext_lower:
            proof.append({"type": "domain_match", "value": company_domain})

    # Name match: check username and full name against company name
    company_slug = slug(company_name)
    if company_slug:
        name_tokens = [t for t in re.findall(r"[a-z0-9]+", company_name.casefold()) if len(t) > 2]
        ig_name_slug = slug(ig_username)
        ig_full_slug = slug(full_name)
        # Check if significant name tokens appear in IG username or full name
        if name_tokens and any(t in ig_name_slug for t in name_tokens):
            proof.append({"type": "name_match", "value": company_name})
        elif name_tokens and any(t in ig_full_slug for t in name_tokens):
            proof.append({"type": "name_match", "value": company_name})

    return bool(proof), proof


def process_company(
    profile: dict,
    cache_dir: Path,
    ig_cache_dir: Path,
) -> tuple[list[dict], dict]:
    """Process a single company: fetch website, find IG URLs, scrape, match."""
    org = str(profile["organisation_number"])
    name = str(profile.get("name") or "")
    website = str(profile.get("website") or profile.get("website_url") or "")
    company_domain = extract_domain(website) if website else ""

    if not website:
        return [], {"organisation_number": org, "accepted": False, "reason": "no_website"}

    url = website if "://" in website else f"https://{website}"

    try:
        raw, cache_hit = fetch_html(url, cache_dir, org)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        return [], {"organisation_number": org, "accepted": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}

    ig_urls = extract_instagram_urls(raw)
    if not ig_urls:
        return [], {"organisation_number": org, "accepted": True, "cache_hit": cache_hit, "reason": "no_instagram_links"}

    # Extract usernames from URLs
    usernames = []
    for ig_url in ig_urls:
        parsed = urlparse(ig_url)
        username = parsed.path.strip("/").split("/")[0] if parsed.path.strip("/") else ""
        if username and username not in usernames:
            usernames.append(username)

    if not usernames:
        return [], {"organisation_number": org, "accepted": True, "cache_hit": cache_hit, "reason": "no_usernames_extracted"}

    # Rate limit before Apify call
    time.sleep(REQUEST_DELAY)

    # Scrape profiles
    ig_profiles = scrape_instagram_profiles(usernames, ig_cache_dir)
    if not ig_profiles:
        return [], {"organisation_number": org, "accepted": True, "cache_hit": cache_hit, "reason": "apify_scrape_failed"}

    # Match and build observations
    rows: list[dict] = []
    matched = False
    for username in usernames:
        ig_data = ig_profiles.get(username.lower())
        if not ig_data:
            continue
        is_match, proof = match_profile_to_company(username, ig_data, company_domain, name)
        if not is_match:
            continue
        matched = True

        followers = ig_data.get("followersCount") or ig_data.get("followers") or ig_data.get("edge_followed_by", {}).get("count", 0)
        following = ig_data.get("followingCount") or ig_data.get("following") or ig_data.get("edge_follow", {}).get("count", 0)
        posts = ig_data.get("postsCount") or ig_data.get("posts") or ig_data.get("edge_owner_to_timeline_media", {}).get("count", 0)
        bio = ig_data.get("biography") or ig_data.get("bio") or ""
        external_url = ig_data.get("externalUrl") or ig_data.get("external_url") or ""
        profile_pic = ig_data.get("profilePicUrl") or ig_data.get("profile_pic_url") or ig_data.get("profilePicture") or ""

        profile_url = f"https://www.instagram.com/{username}/"
        profile_json = json.dumps(ig_data, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(profile_json.encode("utf-8")).hexdigest()
        retrieved_at = utc_now()

        metrics = {
            "followers": followers,
            "following": following,
            "posts": posts,
            "bio": bio,
            "external_url": external_url,
            "profile_picture_url": profile_pic,
        }
        evidence = f"Instagram profile with {followers} followers, {posts} posts"

        row = {
            "id": f"instagram-{org}-{digest[:16]}",
            "organisation_number": org,
            "signal_type": "buzz_metrics",
            "platform": "instagram",
            "source_url": profile_url,
            "source_class": "social_media",
            "acquisition_mode": "permitted_public_page",
            "rights_status": "approved",
            "exact_entity": True,
            "identity_proof": proof,
            "evidence_span": evidence,
            "metrics": metrics,
            "retrieved_at": retrieved_at,
            "content_sha256": digest,
        }
        rows.append(row)

    status: dict = {
        "organisation_number": org,
        "accepted": matched,
        "cache_hit": cache_hit,
        "ig_urls_found": len(ig_urls),
        "profiles_scraped": len(ig_profiles),
        "profiles_matched": sum(1 for r in rows),
    }
    if not matched:
        status["reason"] = "no_match"
    return rows, status


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and scrape company Instagram profiles.")
    parser.add_argument("--profiles", required=True, help="JSONL file with company profiles")
    parser.add_argument("--organisations", required=True, help="Text file with org numbers")
    parser.add_argument("--output", required=True, help="JSONL output path")
    parser.add_argument("--cache", required=True, help="Cache directory")
    parser.add_argument("--report", required=True, help="JSON report output path")
    parser.add_argument("--workers", type=int, default=2, help="Number of worker threads")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    wanted = [line.strip() for line in Path(args.organisations).read_text(encoding="utf-8").splitlines() if line.strip()]
    profiles = {
        str(row["organisation_number"]): row
        for row in (json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip())
    }

    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ig_cache_dir = cache_dir / "ig_profiles"
    ig_cache_dir.mkdir(parents=True, exist_ok=True)

    observations: list[dict] = []
    statuses: list[dict] = []

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        futures = {pool.submit(process_company, profiles[org], cache_dir, ig_cache_dir): org for org in wanted if org in profiles}
        for future in as_completed(futures):
            try:
                rows, status = future.result()
            except Exception as exc:
                org = futures[future]
                rows, status = [], {"organisation_number": org, "accepted": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}
            observations.extend(rows)
            statuses.append(status)

    order = {org: index for index, org in enumerate(wanted)}
    observations.sort(key=lambda row: (order.get(row["organisation_number"], 9999), row["signal_type"]))
    statuses.sort(key=lambda row: order.get(row["organisation_number"], 9999))

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations),
        encoding="utf-8",
    )

    matched_count = sum(1 for s in statuses if s.get("accepted"))
    report = {
        "connector": "instagram_profile_discovery_v1",
        "companies": len(wanted),
        "matched_companies": matched_count,
        "observations": len(observations),
        "errors": sum(1 for s in statuses if "error" in s),
        "rate_limit_seconds": REQUEST_DELAY,
        "workers": args.workers,
        "company_results": statuses,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {k: v for k, v in report.items() if k != "company_results"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
