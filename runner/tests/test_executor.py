"""Executor rules with a scripted adapter (no browser, no network)."""
from __future__ import annotations

import pytest

from fakes import FakeDB
from reprova_runner.adapters.base import TestAdapter
from reprova_runner.queue import Queue
from reprova_runner.worker import handle

PID = "p1"


class ScriptedAdapter(TestAdapter):
    """Each case says what happens per attempt: case["script"] = ["failed", "passed", ...]."""
    name = "scripted"
    down = False
    calls: list = []
    on_execute = None

    def validate_configuration(self):
        return "Environment unreachable: ConnectError" if ScriptedAdapter.down else None

    def execute(self, case, attempt=1):
        ScriptedAdapter.calls.append((case["id"], attempt))
        if ScriptedAdapter.on_execute:
            ScriptedAdapter.on_execute(case)
        script = case.get("script", ["passed"])
        state = script[min(attempt, len(script)) - 1]
        log = self.safe_name(case["id"], attempt, ".log")
        value = self.ctx.secrets.get("login", "")
        log.write_text(f"fill #password = {value}\nconsole: password={value}\n")
        return self.result(case, state, actual=f"{state} on try {attempt}", evidence=[log.name])


@pytest.fixture(autouse=True)
def reset():
    ScriptedAdapter.down = False
    ScriptedAdapter.calls = []
    ScriptedAdapter.on_execute = None


def case(cid, script=("passed",), **kw):
    return {"id": cid, "target_id": "t1", "adapter": "scripted", "title": cid, "script": list(script), **kw}


def setup(cases, *, plan_status="approved", refs=("login",), budget=None):
    db = FakeDB([{"id": "hb", "kind": "runner_heartbeat", "status": "running", "claimed_by": "r", "created_at": "0"},
                 {"id": "run1", "kind": "test_run", "status": "queued", "project_id": PID, "plan_version": 2,
                  "created_at": "1"}])
    db.projects[PID] = {
        "id": PID, "targets": [{"id": "t1", "kind": "web", "access_mode": "black_box",
                                "location": "http://localhost:1", "secret_refs": list(refs)}],
        "budget": budget or {"max_minutes": 60, "repro_attempts": 3},
        "test_plan": {"version": 2, "status": plan_status, "cases": cases},
    }
    return db, Queue(db, "r")


def go(db, q, tmp_path, secrets=None, **kw):
    job = q.claim_next()
    lookup = lambda pid, ref: (secrets if secrets is not None else {"login": "S3cret-Pa55!"}).get(ref)
    return handle(job, q, str(tmp_path), secret_lookup=lookup, adapters={"scripted": ScriptedAdapter}, **kw)


def states(db):
    return {r["test_case_id"]: r["state"] for r in db.rows["run1"]["results"]}


def test_all_six_states_and_summary(tmp_path):
    db, q = setup([case("A"), case("B", ["failed"]), case("C", ["error"]), case("D", selected=False),
                   case("E", ["failed", "passed"])])
    assert go(db, q, tmp_path) == "done"
    assert states(db) == {"A": "passed", "B": "failed", "C": "error", "D": "skipped", "E": "flaky"}
    assert db.rows["run1"]["summary"] == {"passed": 1, "failed": 1, "error": 1, "blocked": 0, "skipped": 1, "flaky": 1}
    # B failed every re-run: original + 3 attempts
    assert len([c for c in ScriptedAdapter.calls if c[0] == "B"]) == 4
    assert ("D", 1) not in ScriptedAdapter.calls


def test_unreachable_environment_is_blocked_not_failed(tmp_path):
    ScriptedAdapter.down = True
    db, q = setup([case("A"), case("B", ["failed"])])
    assert go(db, q, tmp_path) == "done"
    assert set(states(db).values()) == {"blocked"}
    assert ScriptedAdapter.calls == []


def test_missing_credential_ref_blocks_the_target(tmp_path):
    db, q = setup([case("A")])
    go(db, q, tmp_path, secrets={})
    r = db.rows["run1"]["results"][0]
    assert r["state"] == "blocked" and "login" in r["actual"]


def test_only_an_approved_plan_runs(tmp_path):
    db, q = setup([case("A")], plan_status="draft")
    assert go(db, q, tmp_path) == "error"
    assert "not approved" in db.rows["run1"]["error"]
    assert ScriptedAdapter.calls == []


def test_cancel_mid_run_keeps_completed_cases(tmp_path):
    db, q = setup([case("A"), case("B"), case("C")])

    def cancel_after_b(c):
        if c["id"] == "B":
            db.rows["run1"]["status"] = "cancel_requested"
    ScriptedAdapter.on_execute = cancel_after_b
    assert go(db, q, tmp_path) == "cancelled"
    row = db.rows["run1"]
    assert row["status"] == "cancelled"
    assert [r["test_case_id"] for r in row["results"]] == ["A", "B"]
    assert row["summary"]["passed"] == 2


def test_time_budget_stops_the_run_and_skips_the_rest(tmp_path):
    ticks = iter([0, 0, 0, 30, 100, 100, 100, 100, 100, 100])
    db, q = setup([case("A"), case("B"), case("C")], budget={"max_minutes": 1, "repro_attempts": 0})
    assert go(db, q, tmp_path, budget_clock=lambda: next(ticks, 100)) == "done"
    assert states(db)["C"] == "skipped"
    assert "time budget" in db.rows["run1"]["error"]


def test_password_in_test_log_never_reaches_storage(tmp_path):
    db, q = setup([case("A", ["failed", "passed"])])
    go(db, q, tmp_path)
    assert db.uploads, "evidence was uploaded"
    for (bucket, path), data in db.uploads.items():
        assert bucket == "evidence" and path.startswith(f"{PID}/run1/")
        assert b"S3cret-Pa55!" not in data
    assert "S3cret-Pa55!" not in str(db.rows["run1"]["results"])
    assert db.rows["run1"]["evidence_paths"]
    assert not (tmp_path / PID / "run1").exists()   # work folder removed after upload


def test_secret_presence_report_on_the_heartbeat(monkeypatch):
    from reprova_runner import secrets
    monkeypatch.setattr(secrets, "has", lambda account: account.endswith("/login"))
    report = secrets.presence([{"id": PID, "targets": [{"secret_refs": ["login", "api"]}]}])
    assert report == {f"{PID}/login": True, f"{PID}/api": False}
