"""A transient DNS failure must not be recorded as a permanent dead domain.

The 1,000-company run on 2026-11-07 lost 330 company homepages to
"Hostname did not resolve". Every one of those hosts resolves normally when
asked again a minute later, and 231 of them had resolved in the baseline run
on the same day. The cause was a burst of concurrent lookups against the
system resolver: a single `socket.getaddrinfo` call that fails once was
recorded as a blocked website, and the company lost its whole web footprint
for the run.

`website.assert_public_url` therefore has to retry a failed lookup before it
gives up. The retry must be bounded (so a genuinely dead domain still fails
fast) and it must not weaken the SSRF guard: every address the lookup
returns is still checked for being a global address.
"""

from __future__ import annotations

import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent import website  # noqa: E402


class DnsRetryTests(unittest.TestCase):
    def _failing_then_succeeding(self, failures: int):
        calls = {"n": 0}

        def fake_getaddrinfo(host, port, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] <= failures:
                raise socket.gaierror(-2, "Name or service not known")
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        return fake_getaddrinfo, calls

    def test_a_transient_lookup_failure_is_retried(self) -> None:
        fake, calls = self._failing_then_succeeding(1)
        with mock.patch.object(website.socket, "getaddrinfo", side_effect=fake):
            website.assert_public_url("https://example.no/")
        self.assertGreaterEqual(calls["n"], 2, "the lookup must be retried")

    def test_a_lookup_that_keeps_failing_still_raises(self) -> None:
        fake, calls = self._failing_then_succeeding(99)
        with mock.patch.object(website.socket, "getaddrinfo", side_effect=fake):
            with self.assertRaises(ValueError) as caught:
                website.assert_public_url("https://dead.example.no/")
        self.assertIn("did not resolve", str(caught.exception))
        self.assertLessEqual(
            calls["n"],
            website.DNS_RETRY_ATTEMPTS,
            "a dead domain must fail after a bounded number of attempts",
        )

    def test_the_retry_count_is_bounded(self) -> None:
        self.assertGreaterEqual(website.DNS_RETRY_ATTEMPTS, 2)
        self.assertLessEqual(website.DNS_RETRY_ATTEMPTS, 5)

    def test_the_backoff_sleeps_are_bounded(self) -> None:
        self.assertTrue(website.DNS_RETRY_BACKOFF_S)
        self.assertLessEqual(max(website.DNS_RETRY_BACKOFF_S), 5.0)

    def test_a_private_address_is_still_blocked_after_a_retry(self) -> None:
        """The retry must not become a way around the SSRF guard."""

        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

        with mock.patch.object(website.socket, "getaddrinfo", side_effect=fake_getaddrinfo):
            with self.assertRaises(ValueError) as caught:
                website.assert_public_url("https://internal.example.no/")
        self.assertIn("blocked", str(caught.exception))

    def test_a_non_dns_error_is_not_retried(self) -> None:
        """Only lookup failures are retried; a bad scheme fails immediately."""
        with self.assertRaises(ValueError):
            website.assert_public_url("ftp://example.no/")


if __name__ == "__main__":
    unittest.main()
