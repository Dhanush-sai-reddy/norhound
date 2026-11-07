#!/usr/bin/env python3
"""Bulk OpenStreetMap lookup by Norwegian organisation number.

OpenStreetMap tags Norwegian businesses with `ref:NO:orgnr`, the legal
organisation number. That is an exact-entity key: the number identifies the
legal entity, not a name that might match the wrong company. The same objects
often carry `contact:facebook`, `contact:instagram`, `contact:linkedin`,
`contact:twitter`, `contact:youtube`, `website`, `phone` and `email`.

This script pulls every object in the Norwegian bbox that carries the tag, in
one Overpass request, and caches the raw JSON so the connector never has to
re-query. It is keyless: Overpass is a public endpoint, and the data is ODbL.
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
BBOX = "57.8,4.0,71.5,31.5"
USER_AGENT = "NorHound/1.0 (Signalpost company research; keyless public registry lookup)"


def fetch(query: str, *, timeout: float = 300.0) -> str:
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        url = endpoint + "?data=" + urllib.parse.quote_plus(query)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            last_error = exc
    raise SystemExit(f"every Overpass endpoint failed: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache every Norwegian OSM object tagged with ref:NO:orgnr.")
    parser.add_argument("--output", default=".cache/osm/norway-ref-orgnr.json")
    parser.add_argument("--query", default=None, help="Override the Overpass query.")
    args = parser.parse_args()
    query = args.query or (
        f'[out:json][timeout:300];nwr["ref:NO:orgnr"]({BBOX});out tags;'
    )
    raw = fetch(query)
    payload = json.loads(raw)
    elements = payload.get("elements", [])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(raw, encoding="utf-8")
    with_ref = [e for e in elements if (e.get("tags") or {}).get("ref:NO:orgnr")]
    social_keys = ("contact:facebook", "contact:instagram", "contact:linkedin",
                   "contact:twitter", "contact:x", "contact:youtube", "contact:tiktok")
    with_social = [e for e in with_ref if any((e.get("tags") or {}).get(k) for k in social_keys)]
    print(json.dumps({
        "elements": len(elements),
        "with_ref_orgnr": len(with_ref),
        "with_any_social_contact": len(with_social),
        "output": str(output),
    }, indent=2))


if __name__ == "__main__":
    main()
