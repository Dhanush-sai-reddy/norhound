"""Count the outbound HTTP requests a run makes.

The official submission contract asks for "a machine-readable run report with
runtime, request count and third-party cost":

  https://builderr.ai/starter-briefs/signalpost.md          (retrieved 2026-11-17)
  https://builderr.ai/signalpost-starter-kit.tar.gz         (retrieved 2026-11-18)

Every connector runs as its own process, so a counter inside one connector
would only see that connector's requests. This module is imported automatically
by the interpreter (CPython imports `sitecustomize` at startup when it is on
`sys.path`), which makes it the one place that can see every request of every
subprocess of a run.

It is **off unless NORHOUND_REQUEST_LOG is set**, it never changes what a
request returns, and it records only the host, the method and the status — no
path, no query string, no body. A failure in the counter must never break the
run, so every hook is wrapped.

The log is one JSON object per line, appended with a single atomic write, so
parallel workers cannot interleave a line.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.request

_LOG_PATH = os.environ.get("NORHOUND_REQUEST_LOG")
_lock = threading.Lock()
_original_urlopen = None


def _record(host: str, method: str, status: int) -> None:
    line = json.dumps(
        {"host": host, "method": method, "status": status}, ensure_ascii=False
    ) + "\n"
    try:
        fd = os.open(_LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        pass


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlsplit

        return urlsplit(url).netloc.lower()
    except Exception:
        return ""


def _method_of(request: object) -> str:
    method = getattr(request, "get_method", None)
    if callable(method):
        try:
            return str(method() or "GET")
        except Exception:
            return "GET"
    return "GET"


def _install_urlopen_counter() -> None:
    global _original_urlopen
    if _original_urlopen is not None:
        return
    _original_urlopen = urllib.request.urlopen

    def counting_urlopen(*args, **kwargs):
        url = ""
        method = "GET"
        try:
            request = args[0] if args else kwargs.get("url")
            url = getattr(request, "full_url", None) or str(request)
            method = _method_of(request)
        except Exception:
            pass
        status = 0
        try:
            response = _original_urlopen(*args, **kwargs)
            status = int(getattr(response, "status", 0) or 0)
            return response
        except Exception as exc:
            status = int(getattr(exc, "code", 0) or 0)
            raise
        finally:
            try:
                with _lock:
                    _record(_host_of(url), method, status)
            except Exception:
                pass

    urllib.request.urlopen = counting_urlopen


def _install_requests_counter() -> None:
    try:
        import requests
    except Exception:
        return
    session = requests.Session
    if getattr(session, "_norhound_counted", False):
        return
    original_request = session.request

    def counting_request(self, method, url, *args, **kwargs):
        status = 0
        try:
            response = original_request(self, method, url, *args, **kwargs)
            status = int(getattr(response, "status_code", 0) or 0)
            return response
        except Exception as exc:
            status = int(getattr(exc, "response", None).status_code or 0) if getattr(exc, "response", None) is not None else 0
            raise
        finally:
            try:
                with _lock:
                    _record(_host_of(str(url)), str(method).upper(), status)
            except Exception:
                pass

    session.request = counting_request
    session._norhound_counted = True


if _LOG_PATH:
    try:
        _install_urlopen_counter()
        _install_requests_counter()
    except Exception:
        # A broken counter must never break the run.
        pass
