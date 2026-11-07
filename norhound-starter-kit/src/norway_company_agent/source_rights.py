"""Source-rights policy for published observations.

A host belongs here when its observations cannot be published safely:

* ``proff.no`` — every path, including ``robots.txt``, now answers with a
  CloudFront 403, so the permission state that allowed the original collection
  cannot be re-verified, and the collected rows carried third-party financial
  values (``revenue_nok`` / ``profit_nok``) that are not copied from an
  official register. Publishing them would put unsourced financial figures
  into the output, so the host is excluded by default.

* ``google.com`` — two independent reasons, either of which is enough.
  The Google Places API requires an API key, so its rows cannot be reproduced
  or re-verified by a run that must work without a credential. The other rows
  were scraped from Google Maps map pages, which Google's Terms of Service
  prohibit. Both are the same Maps/Places data reached by a route the source
  policy does not allow, so the whole host is excluded by default. The
  measured cost is in ``docs/evidence/keyless-google-exclusion-2026-11-07.md``.

Exclusion is by registered host, so ``www.proff.no`` and any subdomain of
``proff.no`` are excluded too, while lookalike hosts such as
``proff.no.example.com`` are not.
"""

from __future__ import annotations

from urllib.parse import urlparse

DEFAULT_EXCLUDED_HOSTS: tuple[str, ...] = ("proff.no", "google.com")


def source_host(source_url: str) -> str:
    """Host of a URL, lowercased and without a leading ``www.``."""
    try:
        host = (urlparse(str(source_url or "")).hostname or "").strip().lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def excluded_host_for(
    source_url: str,
    excluded_hosts: tuple[str, ...] | list[str] | set[str] = DEFAULT_EXCLUDED_HOSTS,
) -> str:
    """The excluded host that matches this URL, or an empty string."""
    host = source_host(source_url)
    if not host:
        return ""
    for excluded in excluded_hosts:
        candidate = str(excluded).strip().lower().removeprefix("www.")
        if not candidate:
            continue
        if host == candidate or host.endswith("." + candidate):
            return candidate
    return ""


def is_excluded_host(
    source_url: str,
    excluded_hosts: tuple[str, ...] | list[str] | set[str] = DEFAULT_EXCLUDED_HOSTS,
) -> bool:
    """True when observations from this URL must not be published."""
    return bool(excluded_host_for(source_url, excluded_hosts))
