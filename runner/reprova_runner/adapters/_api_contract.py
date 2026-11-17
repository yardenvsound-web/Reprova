"""Parameterized API assertion, run by api_pytest.py in a pytest subprocess (from the PoC).

Not collected by the runner's own test suite: it is passed to pytest explicitly, one case per run.
Inputs come from the environment; the outcome is written to QA_OUTCOME_PATH as JSON so the
adapter can tell an unreachable environment (blocked) from a failed assertion.
"""
import json
import os
from urllib.parse import urljoin

import httpx

CASE = json.loads(os.environ.get("QA_API_CASE", "{}"))
BASE_URL = os.environ.get("QA_BASE_URL", "")
AUTH = os.environ.get("QA_AUTH", "")
LOG_PATH = os.environ.get("QA_LOG_PATH", "")
OUTCOME_PATH = os.environ.get("QA_OUTCOME_PATH", "")


def _write(outcome: dict, lines: list[str]) -> None:
    if OUTCOME_PATH:
        with open(OUTCOME_PATH, "w", encoding="utf-8") as f:
            json.dump(outcome, f)
    if LOG_PATH:
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def _lookup(body, dotted):
    current = body
    for part in dotted.split("."):
        assert isinstance(current, dict) and part in current, f"Missing JSON field: {dotted}"
        current = current[part]
    return current


def test_contract():
    step = (CASE.get("steps") or [{}])[0]
    method = step.get("method", "GET").upper()
    url = urljoin(BASE_URL + "/", step.get("path", "/").lstrip("/"))
    headers = {"Authorization": f"Bearer {AUTH}"} if AUTH else {}
    lines = [f"case {CASE.get('id')}: {method} {url}", f"request headers: {headers}"]
    # Non-destructive calls only in the MVP API adapter.
    assert method in ("GET", "HEAD"), f"Method {method} is not allowed by the API adapter"
    try:
        with httpx.Client(timeout=7, follow_redirects=False) as client:
            response = client.request(method, url, headers=headers)
    except httpx.TransportError as exc:
        lines.append(f"transport error: {exc!r}")
        _write({"state": "blocked", "actual": f"Environment unreachable: {type(exc).__name__}"}, lines)
        raise
    lines.append(f"response {response.status_code}: {response.text[:2000]}")
    try:
        assert response.status_code == step["expected_status"], (
            f"Expected HTTP {step['expected_status']}, got {response.status_code}")
        for key, expected in (step.get("assert_json") or {}).items():
            current = _lookup(response.json(), key)
            assert current == expected, f"{key}: expected {expected!r}, got {current!r}"
    except AssertionError as exc:
        _write({"state": "failed", "actual": str(exc)}, lines)
        raise
    _write({"state": "passed", "actual": f"HTTP {response.status_code}, assertions passed"}, lines)
