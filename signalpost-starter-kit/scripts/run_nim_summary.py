#!/usr/bin/env python3
"""Decision-useful synthesis layer: grounded company summaries via NVIDIA NIM.

Reads terminal envelopes (batch output) and produces per-company synthesis JSON.
The LLM may only restate evidence that is already verified in the envelope;
anything missing is reported as the honest availability state, never invented.
Model, endpoint and rights are declared in the submission's models/APIs section.

This stage is additive: it never alters the terminal envelope, never decides
identity, and a failure here is recorded per company without crashing the run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
NIM_BASE = "https://integrate.api.nvidia.com/v1"
SYSTEM_PROMPT = (
    "You restate only facts given in the supplied Evidence JSON. Never invent a field, never guess, never imply a "
    "value that is not present. For any section with no supported evidence respond with the exact value "
    "\"not_available\". Financial values are in NOK. Output ONLY a raw JSON object with exactly these keys: "
    "company_name, what_it_does, leadership, locations, financial_health, hiring_and_activity, "
    "social_and_external, updates_and_unknowns, boundary_statement. Each value is at most 3 short sentences. "
    "Do not include any text outside the JSON object."
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in sanitize_line_separators(path.read_text(encoding="utf-8")).splitlines() if line.strip()]



def sanitize_line_separators(text: str) -> str:
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _evidence_context(row: dict[str, Any]) -> dict[str, Any]:
    profile = row.get("profile") or {}
    evidence = profile.get("evidence") or {}
    financials = evidence.get("financials") or {}
    fin_records = (financials.get("value") or {}).get("records") or []
    latest = fin_records[0] if fin_records else None

    roles = evidence.get("roles") or {}
    people = [
        {"role": p.get("role") or p.get("group"), "name": p.get("name")}
        for p in (roles.get("value") or {}).get("roles", [])
        if not p.get("inactive")
    ][:12]

    locations = (evidence.get("locations") or {}).get("value") or {}
    locations_list = [
        {"name": item.get("name"), "address": item.get("address")}
        for item in (locations.get("locations") or [])[:12]
    ]

    website = evidence.get("website") or {}
    website_value = website.get("value") or {}
    gate = (website_value.get("identity_assessment") or {}).get("publishable")
    socials = [
        {"platform": s.get("platform"), "url": s.get("url")}
        for s in ((website_value.get("social_links") or []) if gate else [])
    ]

    external = []
    for obs in (evidence.get("external_observations") or []):
        if obs.get("acquisition_mode") == "rights_review_experiment":
            continue
        external.append({
            "signal_type": obs.get("signal_type"),
            "platform": obs.get("platform"),
            "source_url": obs.get("source_url"),
            "evidence_span": obs.get("evidence_span"),
            "sentiment_label": obs.get("sentiment_label"),
        })

    return {
        "registry_name": profile.get("name"),
        "status": {
            "bankrupt": profile.get("bankrupt"),
            "liquidating": profile.get("liquidating"),
        },
        "industry": profile.get("industry_label"),
        "latest_accounts_year": profile.get("latest_submitted_accounts"),
        "financials": latest,
        "leadership": people,
        "registered_locations": locations_list,
        "website_status": website.get("status"),
        "verified_social_handles": socials,
        "external_observations": external,
    }


def call_nim(context: dict[str, Any], *, api_key: str, model: str, timeout: float = 90.0) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Evidence JSON:\n" + json.dumps(context, ensure_ascii=False)},
        ],
        "max_tokens": 1600,
        "temperature": 0.0,
    }
    request = urllib.request.Request(
        f"{NIM_BASE}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    choices = body.get("choices") or [{}]
    message = (choices[0] if choices else {}).get("message") or {}
    return str(message.get("content") or "")


def parse_summary(content: str) -> dict[str, Any]:
    content = content.strip()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    end = content.rfind("}")
    while end != -1:
        start = content.rfind("{", 0, end)
        if start == -1:
            break
        candidate = content[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        end = content.rfind("}", 0, start)
    return {}


def summarize_row(row: dict[str, Any], *, api_key: str, model: str, timeout: float, retries: int = 3) -> dict[str, Any]:
    profile = row.get("profile") or {}
    context = _evidence_context(row)
    outcome: dict[str, Any] = {
        "organisation_number": row.get("organisation_number"),
        "company_name": context["registry_name"] or profile.get("name"),
        "synthesis_model": model,
        "summary": {},
        "synthesis_state": "failed",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    if not api_key:
        outcome["synthesis_state"] = "abstained"
        outcome["reason"] = "NVIDIA_API_KEY not found; abstains rather than guessing."
        return outcome
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            content = call_nim(context, api_key=api_key, model=model, timeout=timeout)
            summary = parse_summary(content)
            if summary:
                outcome["summary"] = summary
                outcome["synthesis_state"] = "available"
                return outcome
            last_error = ValueError("NIM returned no parseable JSON summary.")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            last_error = error
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    outcome["reason"] = f"NIM call failed: {type(last_error).__name__}: {last_error}" if last_error else "NIM returned no parseable JSON summary."
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description="Grounded synthesis summaries via NVIDIA NIM.")
    parser.add_argument("--envelopes", required=True, help="Terminal envelopes JSONL (batch output)")
    parser.add_argument("--output", required=True, help="Summary JSONL output")
    parser.add_argument("--report", required=True, help="Report JSON output")
    parser.add_argument("--api-key-env", default="NVIDIA_API_KEY", help="Environment variable holding the NIM key")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="NIM model id")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--min-interval", type=float, default=0.6, help="Minimum seconds between NIM calls")
    parser.add_argument("--limit", type=int, default=0, help="Cap on rows processed (0 = all)")
    parser.add_argument("--retries", type=int, default=3, help="Attempts per row on transient NIM errors")
    parser.add_argument("--workers", type=int, default=1, help="Parallel summarization workers (HTTP-bound; scale with rate limits)")
    parser.add_argument("--resume", action="store_true", help="Skip organisations already summarized (avail) in the existing output file")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env) or ""
    rows = read_jsonl(Path(args.envelopes))
    if args.limit:
        rows = rows[: args.limit]
    carried: list[dict[str, Any]] = []
    if args.resume and Path(args.output).exists():
        previous = read_jsonl(Path(args.output))
        carried = [item for item in previous if item.get("synthesis_state") == "available" and isinstance(item.get("summary"), dict) and item.get("summary")]
        done_orgs = {str(item.get("organisation_number")) for item in carried}
        if done_orgs:
            rows = [row for row in rows if str(row.get("organisation_number")) not in done_orgs]
            print(f"Resuming: {len(done_orgs)} carried, {len(rows)} to summarize", flush=True)
    if not rows:
        print("Nothing to do: all rows are already summarized.", flush=True)
        if carried:
            states: dict[str, int] = {}
            for item in carried:
                states[item["synthesis_state"]] = states.get(item["synthesis_state"], 0) + 1
            report = {
                "connector": "nim_synthesis",
                "model": args.model,
                "envelopes": len(carried),
                "states": states,
                "license_note": "NVIDIA NIM free trial key; OpenAI-compatible endpoint; used only to restate verified envelope evidence.",
            }
            Path(args.output).write_text("".join(sanitize_line_separators(json.dumps(item, ensure_ascii=False)) + "\n" for item in carried), encoding="utf-8")
            Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    done = 0
    lock = threading.Lock()
    pace = threading.Lock()
    def work(row: dict[str, Any]) -> dict[str, Any]:
        nonlocal done
        if args.min_interval:
            with pace:
                time.sleep(args.min_interval)
        item = summarize_row(row, api_key=api_key, model=args.model, timeout=args.timeout, retries=args.retries)
        with lock:
            done += 1
            if done % 25 == 0:
                print(f"({done}/{len(rows)} rows)", flush=True)
        return item
    if args.workers <= 1:
        results = [work(row) for row in rows]
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(work, rows))
    summaries = carried + results
    output_handle = Path(args.output).open("w", encoding="utf-8")
    try:
        for item in summaries:
            output_handle.write(sanitize_line_separators(json.dumps(item, ensure_ascii=False)) + "\n")
        output_handle.flush()
    finally:
        output_handle.close()
    states = {}
    for item in summaries:
        states.setdefault(item["synthesis_state"], 0)
        states[item["synthesis_state"]] += 1
    report = {
        "connector": "nim_synthesis",
        "model": args.model,
        "envelopes": len(summaries),
        "states": states,
        "license_note": "NVIDIA NIM free trial key; OpenAI-compatible endpoint; used only to restate verified envelope evidence.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()