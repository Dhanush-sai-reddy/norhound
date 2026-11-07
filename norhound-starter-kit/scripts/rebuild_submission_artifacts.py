#!/usr/bin/env python3
"""Rewrite the shipped envelopes without the duplicated contract payload.

The emitter used to nest the freshly built contract envelope under a
``contract`` key, so every claim and every evidence record was written twice:
``envelopes.jsonl`` reached 118 MB, past the 100 MiB per-file limit of the
Git host. The emitter no longer writes that copy (see ``merge_envelope`` in
``scripts/emit_contract_envelope.py``); this script applies exactly the same
merge to an envelope file that was produced by the old code, so an already
shipped corpus can be slimmed without changing a single fact.

Usage:
    python3 scripts/rebuild_submission_artifacts.py \
        --envelopes out/submission/envelopes.jsonl \
        --output out/submission/envelopes.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.emit_contract_envelope import merge_envelope  # noqa: E402


def rewrite(envelope: dict) -> dict:
    """Drop the duplicate contract copy, keeping every fact exactly once."""
    contract = envelope.pop("contract", None)
    if not isinstance(contract, dict):
        return envelope
    return merge_envelope(envelope, contract)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--envelopes", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows = 0
    claims = 0
    with args.envelopes.open(encoding="utf-8") as src, args.output.open("w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            envelope = rewrite(json.loads(line))
            claims += len(envelope.get("claims") or [])
            dst.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")
            rows += 1
    print(json.dumps({"envelopes": rows, "claims": claims, "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
