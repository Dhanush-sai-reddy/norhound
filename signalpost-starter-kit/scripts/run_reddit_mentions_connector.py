#!/usr/bin/env python3
"""Free Reddit OAuth mention connector (client-credentials grant, 100 QPM public API).

Searches for exact legal-company-name mentions on Reddit's public search API.
Only posts whose title or selftext carries the full legal name are emitted, and
these are independent-user mentions (buzz), not company-published footprint, so
they use right-petitioning review buckets exactly like the news connector.

No dollar cost: only the free monthly rate limit applies. If Reddit credentials
are not present, the connector abstains for every profile it would have touched
rather than scraping the HTML site.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.discovery import BLOCKED_DISCOVERY_HOSTS  # noqa: E402

LEGAL_SUFFIXES = {"as", "asa", "ba", "da", "enk", "nuf", "sa", "stiftelsen"}


def normalized_company(value: str) -> str:
    words = re.findall(r"[a-z0-9æøå]+", urllib.parse.unquote(str(value or "")).casefold())
    while words and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)

TOKEN_ENDPOINT = "https://www.reddit.com/api/v1/access_token"
SEARCH_ENDPOINT = "https://oauth.reddit.com/search"
USER_AGENT = "linux:builderr-signalpost-poc:v0.1.0 (by /u/builderr_signalpost_poc)"


def token_sha(profile: dict) -> str:
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode("utf-8")).hexdigest()


def say_positive_or_negative(text: str) -> str | None:
    lowered = text.casefold()
    positive = ("anbefaler", "anbefaling", "bra", "god", "positiv", "utmerket", "topp", "fantastisk", "hjelpsomme", "proff")
    negative = ("svindel", "klag", "klagen", "dårlig", "elendig", "advarsel", "unngå", "styr unna", "misnøye", "ikke anbefal")
    score = sum(1 for token in positive if token in lowered) - sum(1 for token in negative if token in lowered)
    if score > 0:
        return "positive"
    if score < 0:
        return "negative"
    return None


def exact_name_in_text(name: str, text: str) -> bool:
    core = normalized_company(name)
    if not core or len(core) < 3:
        return False
    return re.search(r"(?:^|[^\w])" + re.escape(core) + r"(?:$|[^\w])", text.casefold()[:4000]) is not None


def fetch_token(client_id: str, client_secret: str, timeout: float = 15.0) -> str:
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("Reddit OAuth token response missing access_token")
    return token


def search_reddit(token: str, query: str, *, timeout: float = 20.0, limit: int = 25) -> tuple[list[dict], dict]:
    params = urllib.parse.urlencode({
        "q": query,
        "limit": min(limit, 100),
        "sort": "relevance",
        "restrict_sr": "false",
    })
    url = f"{SEARCH_ENDPOINT}?{params}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    payload = json.loads(raw)
    children = (payload.get("data") or {}).get("children") or []
    results = []
    for child in children:
        data = child.get("data") or {}
        permalink = str(data.get("permalink") or "")
        if not permalink.startswith("/r/"):
            continue
        title = str(data.get("title") or "").strip()
        selftext = str(data.get("selftext") or "").strip()
        subreddit = str(data.get("subreddit") or "")
        results.append({
            "subreddit": subreddit,
            "permalink": permalink,
            "url": f"https://www.reddit.com{permalink}",
            "title": title,
            "selftext": selftext[:4000] if selftext else title,
            "score": int(data.get("score") or 0),
            "num_comments": int(data.get("num_comments") or 0),
            "created_utc": int(data.get("created_utc") or 0),
            "external": (data.get("domain") or "") not in {"self.reddit.com", "reddit.com"},
        })
    return results, {
        "status": response.status,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "bytes": len(raw),
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    }


def fetch(profile: dict, token: str, limit: int) -> tuple[list[dict], dict]:
    org = str(profile["organisation_number"])
    query = f'"{profile["name"]}"'
    try:
        results, operation = search_reddit(token, query, limit=limit)
    except urllib.error.HTTPError as exc:
        body = getattr(exc, "read", lambda: b"")()
        return [], {"organisation_number": org, "status": getattr(exc, "code", 0), "error": f"HTTPError:{getattr(exc, 'code', 0)}", "bytes": len(body), "query": query}
    except Exception as exc:
        return [], {"organisation_number": org, "status": 0, "error": f"{type(exc).__name__}: {str(exc)[:180]}", "query": query}
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    output = []
    seen = set()
    for item in results:
        if item["external"]:
            continue
        text = f'{item["title"]} {item["selftext"]}'
        if not exact_name_in_text(profile["name"], text):
            continue
        digest = hashlib.sha256(f'{profile["name"]}|{item["url"]}|{text}'.encode("utf-8")).hexdigest()
        key = item["url"].rsplit("/", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        sentiment = say_positive_or_negative(text)
        observation = {
            "id": "reddit-mention-" + hashlib.sha256(f"{org}|{item['url']}".encode()).hexdigest()[:24],
            "organisation_number": org,
            "platform": "reddit",
            "signal_type": "public_mention",
            "source_url": item["url"],
            "retrieved_at": retrieved_at,
            "content_sha256": digest,
            "exact_entity": True,
            "identity_proof": [
                {"type": "exact_legal_name_in_reddit_title_or_body", "value": profile["name"]},
                {"type": "subreddit", "value": item["subreddit"]},
            ],
            "acquisition_mode": "rights_review_experiment",
            "rights_status": "review_required",
            "source_class": "independent_forum",
            "evidence_span": text[:600],
            "text": text[:2000],
            "sentiment_label": sentiment,
            "metrics": {
                "subreddit": item["subreddit"],
                "score": item["score"],
                "num_comments": item["num_comments"],
                "created_utc": item["created_utc"],
                "interpretation": "Independent user mention; not company-published footprint.",
            },
            "strategy": "independent_sentiment",
        }
        output.append(observation)
        if len(output) >= limit:
            break
    return output, {"organisation_number": org, "status": operation.get("status"), "results": len(results), "accepted": len(output), "query": query}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--client-id-env", default="REDDIT_CLIENT_ID")
    parser.add_argument("--client-secret-env", default="REDDIT_CLIENT_SECRET")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--min-interval", type=float, default=0.8)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    client_id = (Path(args.client_id_env) if args.client_id_env.startswith(".") else None)
    client_id_value = ""
    if Path(args.client_id_env).exists():
        client_id_value = Path(args.client_id_env).read_text().strip()
    else:
        client_id_value = os.environ.get(args.client_id_env, "")
    client_secret_value = os.environ.get(args.client_secret_env, "")
    rows = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not client_id_value or not client_secret_value:
        Path(args.output).write_text("", encoding="utf-8")
        report = {
            "connector": "reddit_free_oauth_mentions_v1",
            "profiles": len(rows),
            "observations": 0,
            "abstained": len(rows),
            "reason": "REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET not found; connector abstains rather than scraping HTML.",
            "claim_boundary": "Free public-API mentions only; independent-user buzz, not company-published footprint.",
        }
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({**report, "observations": report["observations"]}, ensure_ascii=False, indent=2))
        return

    token = fetch_token(client_id_value, client_secret_value, timeout=args.timeout)
    observations = []
    reports = []
    for index, profile in enumerate(rows):
        items, operation = fetch(profile, token, limit=args.limit)
        observations.extend(items)
        reports.append(operation)
        if index % 40 == 0:
            print(f"reddit {index}/{len(rows)} accepted={len(observations)}", flush=True)
        time.sleep(args.min_interval)
    Path(args.output).write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in observations), encoding="utf-8")
    report = {
        "connector": "reddit_free_oauth_mentions_v1",
        "profiles": len(rows),
        "observations": len(observations),
        "matched": sum(1 for item in reports if item.get("accepted")),
        "provider_errors": sum(1 for item in reports if item.get("error")),
        "sentiment_positive": sum(1 for item in observations if item.get("sentiment_label") == "positive"),
        "sentiment_negative": sum(1 for item in observations if item.get("sentiment_label") == "negative"),
        "claim_boundary": "Free public-API mentions only; independent-user buzz, not company-published footprint.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()