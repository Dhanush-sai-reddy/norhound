#!/usr/bin/env python3
"""Recover company homepages that the plain urllib crawl could not read.

The shipped 1000-company corpus contains two recoverable website failure modes:

* ``source_error`` - the urllib fetch never produced a page (timeout, unsupported
  content type, connection error).
* ``js_fallback_candidate`` - a page was fetched but the body was rendered by
  client-side JavaScript, so the static HTML was almost empty.

This connector re-fetches exactly those registry-declared homepages with a real
headless Chromium (Playwright), rebuilds the website evidence record with the
same shape ``fetch_website`` produces, and re-applies the unchanged identity
gate so an exact-entity judgement is never widened or softened.

Rules that are not negotiable:

* Keyless only - no API key, no login, no paid account.
* ``robots.txt`` is respected per URL through ``website._robots_allowed``.
* Only public HTTP(S) URLs through ``website.assert_public_url``.
* Every emitted field comes from the bytes actually fetched by the browser.
* A failed rescue never mutates the profile.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any, Awaitable, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bs4 import BeautifulSoup  # noqa: E402
import extruct  # noqa: E402

from norway_company_agent.evidence import evidence, utc_now  # noqa: E402
from norway_company_agent.identity import apply_website_identity_gate  # noqa: E402
from norway_company_agent.website import (  # noqa: E402
    USER_AGENT,
    _jsonld_organisations,
    _registered_domain,
    _robots_allowed,
    _social_links,
    assert_public_url,
    normalize_homepage,
)

RENDERER = "playwright-chromium"
SOURCE_TYPE = "registry_linked_company_website"
SOURCE_NOTE = "Company-controlled claim layer; not an official registry fact"
RENDER_SETTLE_MS = 2500
META_TIMEOUT_MS = 2000
BODY_TIMEOUT_MS = 5000
MAX_TEXT_CHARS = 5000

Renderer = Callable[[str, float], Awaitable[dict[str, Any] | None]]

# The browser is launched once per run and shared by every worker.
_BROWSER: Any = None
_LAST_RENDER_ERROR: str | None = None


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #
def select_rescue_targets(profiles: list[dict[str, Any]]) -> list[int]:
    """Return the indices of profiles whose website evidence is recoverable."""
    targets: list[int] = []
    for index, profile in enumerate(profiles):
        website = (profile.get("evidence") or {}).get("website") or {}
        status = str(website.get("status") or "")
        value = website.get("value") or {}
        extraction_state = str(value.get("extraction_state") or "")
        if status == "source_error" or extraction_state == "js_fallback_candidate":
            targets.append(index)
    return targets


def target_url(profile: dict[str, Any]) -> str | None:
    """The registry-declared homepage, normalised the same way the crawl does."""
    url = normalize_homepage(profile.get("website"))
    if url:
        return url
    website = (profile.get("evidence") or {}).get("website") or {}
    return normalize_homepage(website.get("source_url"))


def _scheme_less(value: Any) -> bool:
    """True when the registry declared a bare host rather than a full URL."""
    return not re.match(r"^https?://", str(value or "").strip(), re.I)


def _http_variant(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(("http", parsed.netloc, parsed.path or "/", "", "", ""))


# --------------------------------------------------------------------------- #
# browser seam
# --------------------------------------------------------------------------- #
async def _route_filter(route: Any) -> None:
    """Skip heavy sub-resources; only the DOM and its text are needed."""
    try:
        resource_type = route.request.resource_type
    except Exception:
        resource_type = "document"
    if resource_type in {"image", "media", "font"}:
        await route.abort()
    else:
        await route.continue_()


def _structured_organisations(html: str, base_url: str) -> list[dict[str, Any]]:
    try:
        metadata = extruct.extract(html, base_url=base_url, syntaxes=["json-ld", "microdata", "opengraph"])
    except Exception:
        return []
    return _jsonld_organisations(metadata)


async def render_page(url: str, timeout: float) -> dict[str, Any] | None:
    """Fetch one URL in headless Chromium and return the extracted fields.

    This is the ONLY place that talks to the browser. It returns ``None`` when
    the navigation fails; the caller records the skip reason. Every returned
    field is derived from the bytes the browser actually received.
    """
    global _LAST_RENDER_ERROR
    _LAST_RENDER_ERROR = None
    browser = _BROWSER
    if browser is None:
        _LAST_RENDER_ERROR = "browser_not_launched"
        return None
    context = None
    try:
        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="nb-NO",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        try:
            await page.route("**/*", _route_filter)
        except Exception:
            pass
        await page.goto(url, wait_until="domcontentloaded", timeout=int(float(timeout) * 1000))
        await page.wait_for_timeout(RENDER_SETTLE_MS)
        rendered_html = await page.content()
        final_url = page.url
        title = await page.title()
        description = ""
        for selector in ('meta[name="description"]', 'meta[property="og:description"]'):
            try:
                # A missing meta tag must not stall the run: get_attribute waits for the
                # element by default, so the timeout is bounded explicitly.
                value = await page.get_attribute(selector, "content", timeout=META_TIMEOUT_MS)
            except Exception:
                value = None
            if value and str(value).strip():
                description = str(value).strip()
                break
        try:
            visible_text = await page.inner_text("body", timeout=BODY_TIMEOUT_MS)
        except Exception:
            visible_text = ""
        visible_text = str(visible_text or "")[:MAX_TEXT_CHARS]
        soup = BeautifulSoup(rendered_html, "lxml")
        return {
            "rendered_html": rendered_html,
            "final_url": str(final_url or url),
            "title": str(title or "")[:500],
            "description": str(description or "")[:2000],
            "visible_text": visible_text,
            "social_links": _social_links(final_url, soup),
            "structured_organisations": _structured_organisations(rendered_html, final_url),
            "content_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
        }
    except Exception as exc:
        _LAST_RENDER_ERROR = f"{type(exc).__name__}: {str(exc)[:180]}"
        return None
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# record building
# --------------------------------------------------------------------------- #
def build_website_record(requested_url: str, rendered: dict[str, Any]) -> dict[str, Any]:
    """Build the website evidence record in the exact shape `fetch_website` uses."""
    rendered_html = str(rendered.get("rendered_html") or "")
    final_url = str(rendered.get("final_url") or requested_url)
    title = str(rendered.get("title") or "")[:500]
    description = str(rendered.get("description") or "")[:2000]
    visible_text = str(rendered.get("visible_text") or "")[:MAX_TEXT_CHARS]
    digest = str(rendered.get("content_sha256") or "") or hashlib.sha256(rendered_html.encode("utf-8")).hexdigest()

    social_links = rendered.get("social_links")
    if social_links is None:
        social_links = _social_links(final_url, BeautifulSoup(rendered_html, "lxml"))
    structured = rendered.get("structured_organisations")
    if structured is None:
        structured = _structured_organisations(rendered_html, final_url)

    extraction_state = "static_complete" if len(visible_text.strip()) >= 100 else "js_fallback_candidate"
    value = {
        "requested_url": requested_url,
        "final_url": final_url,
        "registered_domain": _registered_domain(final_url),
        "title": title,
        "description": description,
        "main_text_excerpt": visible_text,
        "social_links": list(social_links),
        "structured_organisations": list(structured),
        "content_sha256": digest,
        "extraction_state": extraction_state,
        "pages": [
            {
                "url": final_url,
                "title": title,
                "main_text_excerpt": visible_text,
                "content_sha256": digest,
            }
        ],
        "crawl_errors": [],
    }
    return evidence(
        "website",
        "available",
        SOURCE_TYPE,
        final_url,
        value=value,
        note=SOURCE_NOTE,
        content_sha256=digest,
    )


# --------------------------------------------------------------------------- #
# rescue
# --------------------------------------------------------------------------- #
async def _rescue_one(
    profile: dict[str, Any],
    timeout: float,
    renderer: Renderer,
    browser_error: str | None,
) -> dict[str, Any]:
    organisation_number = profile.get("organisation_number")
    if browser_error:
        return {
            "status": "failed",
            "reason_code": "browser_launch_failed",
            "reason": f"browser_launch_failed: {browser_error}",
            "organisation_number": organisation_number,
            "url": None,
        }

    url = target_url(profile)
    if not url:
        return {
            "status": "failed",
            "reason_code": "no_target_url",
            "reason": "no_target_url: the registry declares no website for this organisation",
            "organisation_number": organisation_number,
            "url": None,
        }

    try:
        assert_public_url(url)
    except ValueError as exc:
        return {
            "status": "failed",
            "reason_code": "not_public",
            "reason": f"not_public: {exc}",
            "organisation_number": organisation_number,
            "url": url,
        }

    robots_timeout = min(float(timeout), 15.0)
    try:
        allowed = bool(_robots_allowed(url, robots_timeout))
    except Exception as exc:
        return {
            "status": "failed",
            "reason_code": "robots_check_failed",
            "reason": f"robots_check_failed: {type(exc).__name__}: {str(exc)[:180]}",
            "organisation_number": organisation_number,
            "url": url,
        }
    if not allowed:
        return {
            "status": "failed",
            "reason_code": "robots_disallowed",
            "reason": "robots_disallowed: robots.txt does not allow this user agent",
            "organisation_number": organisation_number,
            "url": url,
        }

    rendered = await renderer(url, float(timeout))
    if not rendered:
        first_error = _LAST_RENDER_ERROR or "navigation_failed"
        # `fetch_website` already falls back to http for scheme-less registry values whose
        # https certificate is broken. The rescue mirrors that rule so a broken certificate
        # does not silently drop a company the normal crawl would still have reached.
        if _scheme_less(profile.get("website")) and url.startswith("https://") and "ERR_CERT" in str(first_error):
            fallback_url = _http_variant(url)
            fallback_rendered = await renderer(fallback_url, float(timeout))
            if fallback_rendered:
                rendered = fallback_rendered
                url = fallback_url
            else:
                first_error = f"{first_error} | http fallback: {_LAST_RENDER_ERROR or 'failed'}"
    if not rendered:
        return {
            "status": "failed",
            "reason_code": "render_failed",
            "reason": f"render_failed: {first_error}",
            "organisation_number": organisation_number,
            "url": url,
        }

    original = copy.deepcopy((profile.get("evidence") or {}).get("website"))
    record = build_website_record(url, rendered)
    gated = apply_website_identity_gate(profile, record)
    assessment = gated.get("assessment") or {}

    evidence_block = profile.setdefault("evidence", {})
    evidence_block["website"] = gated["website"]
    attempts = evidence_block.setdefault("website_attempts", [])
    if original is not None:
        attempts.append(original)
    original_value = (original or {}).get("value") or {}
    evidence_block["website_rescue"] = {
        "retrieved_at": utc_now(),
        "renderer": RENDERER,
        "original_status": (original or {}).get("status"),
        "original_extraction_state": original_value.get("extraction_state"),
    }
    return {
        "status": "rescued",
        "reason_code": None,
        "reason": None,
        "organisation_number": organisation_number,
        "url": url,
        "final_url": record.get("source_url"),
        "identity_status": assessment.get("status"),
        "publishable": bool(assessment.get("publishable")),
        "extraction_state": (record.get("value") or {}).get("extraction_state"),
        "social_links": len((record.get("value") or {}).get("social_links") or []),
    }


async def rescue_selected(
    profiles: list[dict[str, Any]],
    *,
    workers: int = 4,
    timeout: float = 45.0,
    limit: int = 0,
    renderer: Renderer | None = None,
    browser_error: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rescue the eligible profiles and return (enriched profiles, report).

    The output has exactly one row per input row, in input order, with the same
    organisation numbers. Profiles that are not eligible, and profiles whose
    rescue failed, are copied through unchanged.
    """
    if renderer is None:
        renderer = render_page
    eligible = select_rescue_targets(profiles)
    targets = eligible[:limit] if limit and limit > 0 else list(eligible)

    enriched = [copy.deepcopy(profile) for profile in profiles]
    outcomes: dict[int, dict[str, Any]] = {}
    semaphore = asyncio.Semaphore(max(1, int(workers)))

    async def one(index: int) -> dict[str, Any]:
        async with semaphore:
            return await _rescue_one(enriched[index], timeout, renderer, browser_error)

    if targets:
        results = await asyncio.gather(*(one(index) for index in targets), return_exceptions=True)
        for index, result in zip(targets, results):
            if isinstance(result, BaseException):
                outcomes[index] = {
                    "status": "failed",
                    "reason_code": "unexpected_error",
                    "reason": f"unexpected_error: {type(result).__name__}: {str(result)[:180]}",
                    "organisation_number": enriched[index].get("organisation_number"),
                    "url": None,
                }
            else:
                outcomes[index] = result

    identity_statuses: Counter[str] = Counter()
    skip_reasons: Counter[str] = Counter()
    rescued = 0
    failed = 0
    ordered_outcomes: list[dict[str, Any]] = []
    for index in targets:
        outcome = outcomes.get(index) or {
            "status": "failed",
            "reason_code": "not_attempted",
            "reason": "not_attempted",
            "organisation_number": enriched[index].get("organisation_number"),
            "url": None,
        }
        ordered_outcomes.append(outcome)
        if outcome.get("status") == "rescued":
            rescued += 1
            identity_statuses[str(outcome.get("identity_status") or "unknown")] += 1
        else:
            failed += 1
            skip_reasons[str(outcome.get("reason_code") or "unknown")] += 1

    report = {
        "generated_at": utc_now(),
        "renderer": RENDERER,
        "profiles": len(profiles),
        "eligible": len(eligible),
        "selected": len(targets),
        "rescued": rescued,
        "failed": failed,
        "identity_statuses": dict(identity_statuses),
        "skip_reasons": dict(skip_reasons),
        "outcomes": ordered_outcomes,
    }
    return enriched, report


# --------------------------------------------------------------------------- #
# io
# --------------------------------------------------------------------------- #
def read_profiles(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _sanitize_line_separators(text: str) -> str:
    """Escape U+2028/U+2029 so a JSONL row survives `str.splitlines()`."""
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def write_profiles(path: Path, profiles: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in profiles:
            handle.write(
                _sanitize_line_separators(json.dumps(row, ensure_ascii=False, separators=(",", ":"))) + "\n"
            )


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
async def _run_with_browser(
    profiles: list[dict[str, Any]],
    *,
    workers: int,
    timeout: float,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    global _BROWSER
    from playwright.async_api import async_playwright  # imported lazily so tests need no browser

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    except Exception as exc:
        return await rescue_selected(
            profiles,
            workers=workers,
            timeout=timeout,
            limit=limit,
            browser_error=f"{type(exc).__name__}: {str(exc)[:300]}",
        )
    _BROWSER = browser
    try:
        return await rescue_selected(profiles, workers=workers, timeout=timeout, limit=limit)
    finally:
        _BROWSER = None
        try:
            await browser.close()
        finally:
            await playwright.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rescue company websites with a headless Chromium browser.")
    parser.add_argument("--profiles", required=True, help="Input profiles JSONL.")
    parser.add_argument("--output", required=True, help="Enriched profiles JSONL (one row per input row).")
    parser.add_argument("--report", required=True, help="JSON report of the rescue run.")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent browser contexts.")
    parser.add_argument("--timeout", type=float, default=45.0, help="Seconds per navigation.")
    parser.add_argument("--limit", type=int, default=0, help="Max rescue attempts (0 = no limit).")
    args = parser.parse_args()

    profiles = read_profiles(Path(args.profiles))
    rows, report = asyncio.run(
        _run_with_browser(
            profiles,
            workers=args.workers,
            timeout=args.timeout,
            limit=args.limit,
        )
    )
    write_profiles(Path(args.output), rows)
    write_report(Path(args.report), report)
    print(
        json.dumps(
            {
                "profiles": report["profiles"],
                "selected": report["selected"],
                "rescued": report["rescued"],
                "failed": report["failed"],
                "identity_statuses": report["identity_statuses"],
                "skip_reasons": report["skip_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
