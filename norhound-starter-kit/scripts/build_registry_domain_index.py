#!/usr/bin/env python3
"""Index the domains that exactly one Norwegian entity declares in the register.

Brønnøysund stores a `hjemmeside` per organisation number, submitted by the
entity itself.  When a domain is declared by one and only one organisation
number in the whole register, that declaration identifies the entity as surely
as an official-API field does — and far more reliably than matching legal-name
tokens on a page, which fails for every brand site.

Only unique declarations are written.  A domain shared by two or more
organisation numbers is omitted entirely, so downstream promotion is
default-deny: absence means "cannot prove single ownership".

Rebuild (needs the frozen register dump, one bulk download, ~148 MB compressed):
    uv run python scripts/build_registry_domain_index.py \
        --register data/brreg-enheter.csv \
        --output data/registry-domain-unique.jsonl.gz
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HOST_STRIP = re.compile(r"^[a-z]+://")


def register_domain(url: str) -> str:
    """The registrable host of a `hjemmeside` value, scheme/www/port/path stripped."""
    value = (url or "").strip().lower()
    if not value:
        return ""
    value = HOST_STRIP.sub("", value)
    host = re.split(r"[/?:]", value, 1)[0]
    return host.removeprefix("www.")


def open_maybe_gzip(path: Path):
    """The frozen dump is gzip-compressed regardless of the name it was saved under."""
    with open(path, "rb") as probe:
        magic = probe.read(2)
    if magic == b"\x1f\x8b":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace", newline="")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--register", required=True, help="Frozen BRREG enhance dump (CSV, gzip or plain)")
    parser.add_argument("--output", required=True, help="JSONL(.gz) of {domain, organisation_number}")
    parser.add_argument("--report", help="Write summary JSON here")
    parser.add_argument("--gzip", action="store_true", help="Compress the output")
    args = parser.parse_args()

    source = Path(args.register)
    if not source.exists():
        raise SystemExit(f"register dump not found: {source}")

    handle = open_maybe_gzip(source)
    reader = csv.reader(handle)
    header = next(reader, [])
    lowered = [name.strip().lower() for name in header]
    try:
        index_org = lowered.index("organisasjonsnummer")
        index_web = lowered.index("hjemmeside")
    except ValueError:
        handle.close()
        raise SystemExit(f"expected organisasjonsnummer + hjemmeside columns, got: {header[:8]}")

    declarers: dict[str, set[str]] = defaultdict(set)
    rows = 0
    for record in reader:
        if len(record) <= index_web:
            continue
        rows += 1
        domain = register_domain(record[index_web])
        if not domain or "." not in domain:
            continue
        number = re.sub(r"\D", "", record[index_org])
        if len(number) != 9:
            continue
        declarers[domain].add(number)
    handle.close()

    unique = {domain: next(iter(orgs)) for domain, orgs in declarers.items() if len(orgs) == 1}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps({"domain": domain, "organisation_number": unique[domain]},
                             separators=(",", ":")) + "\n" for domain in sorted(unique))
    if args.gzip or output.suffix == ".gz":
        with gzip.open(output, "wt", encoding="utf-8") as sink:
            sink.write(body)
    else:
        output.write_text(body, encoding="utf-8")

    shared = len(declarers) - len(unique)
    report = {"register_rows": rows, "distinct_domains": len(declarers),
              "unique_single_declarer_domains": len(unique), "shared_domains_omitted": shared,
              "output": str(output)}
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
