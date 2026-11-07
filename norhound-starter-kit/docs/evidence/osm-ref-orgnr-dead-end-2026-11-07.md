# OSM `ref:NO:orgnr` is not a recall lever for this corpus

**Date:** 2026-11-07
**Question:** can OpenStreetMap supply exact-company social handles (or
websites) for the 1,000 companies in the evaluation set?
**Answer:** no — not at any scale that matters. Measured, not assumed.

## Why it looked promising

`ref:NO:orgnr` is the Norwegian organisation number written as an OSM tag. It
is an exact-entity key: the number identifies the legal entity, not a name
that could match the wrong company. The same objects often carry
`contact:facebook`, `contact:instagram`, `contact:linkedin`, `contact:twitter`,
`contact:youtube`, `website`, `phone` and `email`.

## The measurement

The cache was fetched with the official Overpass API, one request for every
object in the Norwegian bounding box that carries the tag:

```bash
uv run python scripts/fetch_osm_orgnr_cache.py --output .cache/osm/norway-ref-orgnr.json
# {"elements": 11164, "with_ref_orgnr": 11164, "with_any_social_contact": 63}
```

| Measure | Value |
|---|---|
| Objects in the Norwegian bbox carrying `ref:NO:orgnr` | 11,164 |
| Distinct organisation numbers | 11,151 |
| Objects carrying **any** social contact tag | **63** (0.56%) |
| Evaluation-set organisation numbers present in the cache | **4 / 1,000** |
| Of those 4, objects carrying a social contact or website tag | **0** |

The four matches are healthcare providers and one retail branch
(`992114169`, `986752900`, `833175262`, `993378496`); three carry only
`ref:nhn` and health tags, and the fourth carries an email and a phone but no
social handle and no website.

## Decision

**Not wired into the pipeline.** The connector
(`scripts/run_osm_overpass_connector.py`) exists but is broken (it calls an
undefined `fetch_osm` and reads `raw.get` on a string), and there is no point
repairing it: the yield for this corpus is **0 publishable facts**.

Two ceilings make it a dead end, and both are structural:

1. **Coverage.** 11,151 of Norway's registered companies are tagged, but only
   4 of the 1,000 companies in the evaluation set are among them. The
   evaluation set is drawn from companies with a website; OSM is a map
   database, so its coverage is concentrated on physical premises.
2. **Social density.** Of the tagged objects, 63 (0.56%) carry any social
   contact tag at all. Even perfect coverage of the evaluation set would yield
   at most a handful of handles.

## Cost

One public Overpass request, no key, 4.7 MB of cached JSON. The cache is kept
in `.cache/osm/` so the measurement above can be reproduced without touching
the network.

## Files

- `scripts/fetch_osm_orgnr_cache.py` — the bulk fetcher (research tool, not
  part of the pipeline).
- `.cache/osm/norway-ref-orgnr.json` — the cached Overpass response.
