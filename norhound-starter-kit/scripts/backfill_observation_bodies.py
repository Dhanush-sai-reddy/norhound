#!/usr/bin/env python3
"""Backfill retained body excerpts onto observations from stored page text.

Only fills rows whose source_url exactly matches an already-stored page
(homepage final_url or a stored secondary page URL). Never invents text.
Improves evidence quality (retained body) without changing coverage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BODY_CHARS = 2000
MIN_TEXT = 200


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def norm(u: str) -> str:
    return (u or "").strip().rstrip("/").casefold()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--observations", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    profiles = {str(p["organisation_number"]): p for p in read_jsonl(Path(args.profiles))}
    obs = read_jsonl(Path(args.observations))
    filled = 0
    by_signal: dict[str, int] = {}
    for o in obs:
        m = o.get("metrics") or {}
        if m.get("body_excerpt") or o.get("evidence_body"):
            continue
        p = profiles.get(str(o.get("organisation_number")))
        if not p:
            continue
        val = ((p.get("evidence") or {}).get("website") or {}).get("value") or {}
        src = norm(str(o.get("source_url") or ""))
        text = None
        if src and norm(str(val.get("final_url") or "")) == src:
            text = val.get("main_text_excerpt") or ""
        else:
            pages = val.get("pages") or {}
            items = pages.values() if isinstance(pages, dict) else pages
            for pg in items or []:
                if isinstance(pg, dict) and norm(str(pg.get("url") or "")) == src:
                    text = pg.get("main_text_excerpt") or ""
                    break
        text = (text or "").strip()
        if len(text) >= MIN_TEXT:
            o.setdefault("metrics", {})["body_excerpt"] = text[:BODY_CHARS]
            o["metrics"]["body_source"] = "stored_page_text"
            filled += 1
            by_signal[o.get("signal_type", "?")] = by_signal.get(o.get("signal_type", "?"), 0) + 1

    write_jsonl(Path(args.output), obs)
    report = {"rows": len(obs), "filled": filled, "by_signal": by_signal, "output": args.output}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
