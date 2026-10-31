"""Publication timestamps kept exactly as the source published them.

The verified-pool key for a dated-news fact is the lower-cased string
``"<title> (<published datetime>)"``, and the organiser's reference value carries
the source's own UTC offset (``2025-09-22T20:00:00+02:00``). Converting a
timestamp to UTC, rewriting ``+01:00`` as ``Z``, or dropping the time makes every
news fact we capture unmatchable, so the offset is preserved verbatim and never
invented: a naive timestamp stays naive and a date-only one stays date-only.

This lives in one place because four connectors previously carried their own
copy and each of them quietly normalised to ``Z``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

MIN_PLAUSIBLE_YEAR = 2000
FUTURE_TOLERANCE = timedelta(days=2)

_DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_LOOSE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?))?")


def parse_publication(raw: object) -> datetime | str | None:
    """Parse a source timestamp without touching its offset.

    Returns a datetime (offset-bearing only if the source carried one), a
    date-only string, or None when the value is not a plausible publication date.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    if _DATE_ONLY.match(text):
        return text
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00") if text[-1] in "Zz" else datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except Exception:
            parsed = None
    if parsed is not None:
        return parsed
    loose = _LOOSE.match(text)
    if not loose:
        return None
    return text[:10] if not loose.group(2) else f"{loose.group(1)}T{loose.group(2)}"


def publication_timestamp(raw: object, *, now: datetime | None = None) -> str | None:
    """Source-faithful publication value, or None when implausible.

    Year and future-dated guards are judged against the value's own calendar; a
    naive timestamp is treated as UTC only for that comparison and is still
    published without an invented offset. A source that wrote ``Z`` keeps
    ``Z``, because the pool compares these values as strings.
    """
    text = str(raw or "").strip()
    parsed = parse_publication(text)
    if parsed is None:
        return None
    if isinstance(parsed, str):
        return parsed
    reference = now or datetime.now(timezone.utc)
    comparable = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    if comparable.year < MIN_PLAUSIBLE_YEAR or comparable > reference + FUTURE_TOLERANCE:
        return None
    value = parsed.isoformat()
    if text[-1] in "Zz" and value.endswith("+00:00"):
        return f"{value[:-6]}Z"
    return value
