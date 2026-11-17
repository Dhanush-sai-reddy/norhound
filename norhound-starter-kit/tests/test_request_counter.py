"""The run report must state a request count that was actually measured.

The official submission contract asks for "a machine-readable run report with
runtime, request count and third-party cost":

  https://builderr.ai/starter-briefs/signalpost.md          (retrieved 2026-11-17)
  https://builderr.ai/signalpost-starter-kit.tar.gz         (retrieved 2026-11-18)

Every connector is its own process, so the counter has to be installed where
the interpreter itself picks it up. These tests pin that the counter counts a
real request, stays inert when it is switched off, and never changes what a
request returns.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COUNTER = """
import json, os, urllib.request
import sitecustomize  # the counter the interpreter installs
response = urllib.request.urlopen("{url}")
print(response.status)
"""


class RequestCounterTests(unittest.TestCase):
    def test_the_counter_is_off_without_the_environment_variable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "probe.py"
            script.write_text(
                "import urllib.request, json\n"
                "print(json.dumps(sorted(k for k in dir(urllib.request) if 'urlopen' in k)))\n",
                encoding="utf-8",
            )
            env = {k: v for k, v in os.environ.items() if k != "NORHOUND_REQUEST_LOG"}
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(ROOT),
                timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("counting_urlopen", result.stdout)

    def test_the_counter_records_the_host_of_a_real_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "requests.jsonl"
            script = Path(tmp) / "probe.py"
            script.write_text(
                COUNTER.format(url="https://example.no/robots.txt"), encoding="utf-8"
            )
            env = dict(os.environ)
            env["NORHOUND_REQUEST_LOG"] = str(log)
            env["PYTHONPATH"] = str(ROOT)
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(ROOT),
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = [
                json.loads(line)
                for line in log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        self.assertTrue(lines, "the counter recorded no request")
        self.assertEqual(lines[0]["host"], "example.no")
        self.assertEqual(lines[0]["method"], "GET")
        # No path, no query string: the log keeps the host only.
        self.assertNotIn("path", lines[0])
        self.assertNotIn("url", lines[0])

    def test_the_report_sums_a_measured_request_log(self) -> None:
        sys.path.insert(0, str(ROOT))
        from scripts import build_official_run_report as report_builder

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            log = run_dir / "requests.jsonl"
            log.write_text(
                "\n".join(
                    json.dumps({"host": "example.no", "method": "GET", "status": 200})
                    for _ in range(7)
                )
                + "\n",
                encoding="utf-8",
            )
            report = report_builder.build(run_dir)

        self.assertTrue(report["requests"]["measured"])
        self.assertEqual(report["requests"]["total"], 7)
        self.assertEqual(report["requests"]["busiest_hosts"]["example.no"], 7)


if __name__ == "__main__":
    unittest.main()
