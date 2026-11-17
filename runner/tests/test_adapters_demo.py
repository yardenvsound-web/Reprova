"""End to end: the real Web and API adapters against the local demo targets (fixtures/).

Needs Playwright's Chromium (python -m playwright install chromium); skipped otherwise.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from demo_targets import ApiHandler, WebHandler, serve
from fakes import FakeDB
from reprova_runner.queue import Queue
from reprova_runner.worker import handle

PLANS = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "demo_plans.json").read_text())
SECRETS = {"demo_web_login": "Demo-Pa55-7781", "demo_api_key": "demo-token-0042"}


def chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


def run_plan(kind, location, tmp_path, *, port_server=None):
    plan = dict(PLANS[kind], status="approved")
    tid = "t-web" if kind == "web" else "t-api"
    ref = "demo_web_login" if kind == "web" else "demo_api_key"
    db = FakeDB([{"id": "hb", "kind": "runner_heartbeat", "status": "running", "claimed_by": "r", "created_at": "0"},
                 {"id": "run", "kind": "test_run", "status": "queued", "project_id": "p", "plan_version": 1,
                  "created_at": "1"}])
    db.projects["p"] = {"id": "p", "budget": {"max_minutes": 5, "repro_attempts": 3}, "test_plan": plan,
                        "targets": [{"id": tid, "kind": kind, "access_mode": "black_box", "location": location,
                                     "secret_refs": [ref]}]}
    q = Queue(db, "r")
    handle(q.claim_next(), q, str(tmp_path), secret_lookup=lambda pid, r: SECRETS.get(r))
    row = db.rows["run"]
    return {r["test_case_id"]: r["state"] for r in row["results"]}, row, db


@pytest.fixture
def api_server():
    ApiHandler.calls = 0
    s = serve(ApiHandler, 0)
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


@pytest.fixture
def web_server():
    s = serve(WebHandler, 0)
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


def test_api_plan_end_to_end(api_server, tmp_path):
    states, row, db = run_plan("api", api_server, tmp_path)
    assert states == {"API-01": "passed", "API-02": "failed", "API-03": "passed", "API-04": "passed",
                      "API-05": "flaky", "API-06": "skipped"}
    assert row["status"] == "done"
    flaky = next(r for r in row["results"] if r["test_case_id"] == "API-05")
    assert len(flaky["attempts"]) == 4
    assert all(b"demo-token-0042" not in data for data in db.uploads.values())


@pytest.mark.skipif(not chromium_available(), reason="Playwright Chromium is not installed")
def test_web_plan_end_to_end_and_password_is_redacted(web_server, tmp_path):
    states, row, db = run_plan("web", web_server, tmp_path)
    assert states == {"WEB-01": "passed", "WEB-02": "failed", "WEB-03": "passed", "WEB-04": "error",
                      "WEB-05": "skipped"}
    # the demo page prints the password to the console and the runner logs the fill step
    assert db.uploads, "evidence uploaded"
    for (_, path), data in db.uploads.items():
        assert b"Demo-Pa55-7781" not in data, path
        if path.endswith("WEB-03.log"):
            assert b"[REDACTED:demo_web_login]" in data
    assert any(p.endswith(".png") for p in row["evidence_paths"])   # screenshot for failed/error


def test_stopped_environment_is_blocked(tmp_path):
    s = serve(ApiHandler, 0)
    url = f"http://127.0.0.1:{s.server_port}"
    s.shutdown()
    s.server_close()
    states, row, _ = run_plan("api", url, tmp_path)
    selected = {k: v for k, v in states.items() if k != "API-06"}
    assert set(selected.values()) == {"blocked"}
    assert row["status"] == "done"
