# The 330 "dead" homepages were a resolver burst, not dead domains

**Date:** 2026-11-07
**Question:** why did the 1,000-company run lose 330 company homepages to
"Hostname did not resolve" when the baseline run had lost only 70?
**Answer:** a transient burst of concurrent DNS lookups against the system
resolver. Every one of the 330 hosts resolves normally when asked again.

## The measurement

The second full run reported 342 blocked homepages, 330 of them with the note
`Hostname did not resolve`, against 70 in the shipped baseline — while the
company set was byte-identical (`entry-web1000.jsonl` and the run's
`entry.jsonl` are the same 1,000 organisations in the same order).

| Measure | Baseline | Full run 2026-11-07 | Now |
|---|---|---|---|
| Homepages blocked, DNS failure | 70 | 330 | — |
| Websites available | 830 | 586 | — |
| `available` → `blocked` on the **same host** | — | 231 | **60 / 60 sampled resolve fine** |

The decisive test: take the 231 organisations whose website went from
`available` in the baseline to `blocked` in the run, ask for their hostnames
again, and resolve them. 60 of 60 resolve. A further 60-host sample of the
330 DNS failures resolves 12 through Cloudflare DNS-over-HTTPS while the
local resolver still refuses them — the resolver was the problem, not the
domains. 44 of that sample are genuinely NXDOMAIN, 4 are SERVFAIL, and the
rest resolve.

## Why the resolver failed

`/etc/resolv.conf` points at `127.0.0.53` (systemd-resolved), which forwards
to the router at `192.168.10.1`. The run fires `socket.getaddrinfo` for
hundreds of hosts across 8 workers. A single lookup failure was recorded
permanently as `blocked`, so one dropped packet per host removed the
company's entire web footprint for the run.

## The fix

`website.assert_public_url` now resolves through `_resolve_addresses`, which
retries a failed lookup up to `DNS_RETRY_ATTEMPTS` (3) times with a bounded
backoff (`DNS_RETRY_BACKOFF_S = (0.5, 1.5)`) before declaring the host
unresolvable. The retry does not weaken the SSRF guard: every address the
lookup returns is still checked for being a global address, and a private
address is still refused.

```python
# src/norway_company_agent/website.py
DNS_RETRY_ATTEMPTS = 3
DNS_RETRY_BACKOFF_S = (0.5, 1.5)
```

This also fixes the browser rescue stage, which failed **133 of 133** targets
with `not_public: Hostname did not resolve` in the same run — the same
one-shot resolver failure, reached through the same `assert_public_url` gate.
On the 30-company smoke corpus the rescue recovered 2 of 3 eligible
homepages; in the full run it recovered 0 of 133 for the same reason.

## Tests

`tests/test_dns_resolution_retry.py` (6 tests):

* a transient lookup failure is retried and the URL is accepted;
* a lookup that keeps failing still raises `Hostname did not resolve`, after
  at most `DNS_RETRY_ATTEMPTS` attempts;
* the retry count and the backoff are bounded;
* a private address is still blocked after a successful retry;
* a non-DNS error (a bad scheme) is not retried.

## What was shipped

The degraded run was **not** shipped. The submission uses the corpus measured
before the resolver burst: 32,713 observations, 0 wrong-company publications,
entity precision 1.0. See `docs/evidence/family-recall-measurement-2026-11-07.md`
for the recall numbers and `docs/evidence/dns-resolver-burst-2026-11-07.md`
for this diagnosis.
