"""F16: API adapter (Pytest + httpx), from the PoC.

Case steps (one request per case):
  {"action": "request", "method": "GET", "path": "/api/health",
   "expected_status": 200, "assert_json": {"status": "ok"}, "auth": "demo_api_key"}
"auth" names a credential ref; its value comes from the Keychain and is sent as a bearer token.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from time import perf_counter

import httpx

from ..results import now_iso
from .base import TestAdapter

CONTRACT = Path(__file__).with_name("_api_contract.py")


class ApiPytestAdapter(TestAdapter):
    name = "api_pytest"

    @property
    def base_url(self) -> str:
        return self.target["location"].rstrip("/")

    def validate_configuration(self) -> str | None:
        try:
            httpx.get(self.base_url + "/", timeout=5, follow_redirects=False)
        except httpx.HTTPError as exc:
            return f"Environment unreachable: {type(exc).__name__} for {self.base_url}"
        return None

    def discover_capabilities(self):
        return {"methods": ["GET", "HEAD"], "assertions": ["expected_status", "assert_json"]}

    def execute(self, case, attempt=1):
        started_at, t0 = now_iso(), perf_counter()
        step = (case.get("steps") or [{}])[0]
        expected = case.get("expected") or f"HTTP {step.get('expected_status')}" + (
            f" + {step['assert_json']}" if step.get("assert_json") else "")
        try:
            auth = self.secret(step["auth"]) if step.get("auth") else ""
        except LookupError as exc:
            return self.result(case, "blocked", expected=expected, actual=str(exc),
                               started_at=started_at, finished_at=now_iso())

        xml_path = self.safe_name(case["id"], attempt, "_junit.xml")
        log_path = self.safe_name(case["id"], attempt, ".log")
        outcome_path = self.safe_name(case["id"], attempt, "_outcome.json")
        env = dict(os.environ, QA_API_CASE=json.dumps(case), QA_BASE_URL=self.base_url, QA_AUTH=auth,
                   QA_LOG_PATH=str(log_path), QA_OUTCOME_PATH=str(outcome_path),
                   PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        try:
            subprocess.run(
                [sys.executable, "-m", "pytest", "-q", str(CONTRACT), "--tb=short",
                 "-p", "no:cacheprovider", f"--junitxml={xml_path}"],
                env=env, capture_output=True, text=True, timeout=self.ctx.case_timeout_s,
                cwd=str(self.ctx.work_dir))
        except subprocess.TimeoutExpired:
            return self.result(case, "error", expected=expected, actual="Execution error (engine)",
                               execution_error=f"pytest timed out after {self.ctx.case_timeout_s:.0f}s",
                               started_at=started_at, finished_at=now_iso())
        except OSError as exc:
            return self.result(case, "error", expected=expected, actual="Execution error (engine)",
                               execution_error=str(exc)[:400], started_at=started_at, finished_at=now_iso())

        state, actual, exec_error = self._outcome(outcome_path, xml_path)
        outcome_path.unlink(missing_ok=True)
        evidence = [p.name for p in (log_path, xml_path) if p.exists()]
        return self.result(case, state, expected=expected, actual=actual, execution_error=exec_error,
                           duration_ms=round((perf_counter() - t0) * 1000), started_at=started_at,
                           finished_at=now_iso(), evidence=evidence)

    @staticmethod
    def _outcome(outcome_path: Path, xml_path: Path) -> tuple[str, str, str]:
        if outcome_path.exists():
            data = json.loads(outcome_path.read_text(encoding="utf-8"))
            return data["state"], data.get("actual", "")[:500], ""
        # The test did not reach an assertion: our engine failed (import error, bad case data...).
        detail = "pytest did not produce an outcome"
        if xml_path.exists():
            node = ET.parse(xml_path).getroot().find(".//testcase/*")
            if node is not None:
                detail = node.attrib.get("message", detail)
        return "error", "Execution error (engine)", detail[:450]
