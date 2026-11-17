"""Queue protocol tests with an in-memory fake database (no network)."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from fakes import FakeDB
from reprova_runner.queue import Queue
from reprova_runner.worker import handle


T0 = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


def job(id_, status="queued", kind="test_run", created="2026-10-20T08:00:00+00:00", **kw):
    return {"id": id_, "status": status, "kind": kind, "created_at": created, **kw}


def heartbeat_row(runner="runner-mac"):
    return job("hb", status="running", kind="runner_heartbeat", claimed_by=runner)


def test_empty_test_run_goes_from_queued_to_done():
    db = FakeDB([heartbeat_row(), job("j1")])
    q = Queue(db, "runner-mac", clock=lambda: T0)
    claimed = q.claim_next()
    assert claimed["id"] == "j1"
    assert db.rows["j1"]["status"] == "running"
    assert handle(claimed, q) == "done"
    assert db.rows["j1"]["status"] == "done"
    assert db.rows["j1"]["summary"]["passed"] == 0
    assert db.rows["hb"]["heartbeat_at"] == T0.isoformat()


def test_job_is_claimed_once_even_with_two_runners():
    db = FakeDB([job("j1")])
    results = []
    barrier = threading.Barrier(2)

    def worker(name):
        q = Queue(db, name, clock=lambda: T0)
        barrier.wait()
        results.append(q.claim_next())

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("runner-a", "runner-b")]
    for t in threads: t.start()
    for t in threads: t.join()
    assert sum(1 for r in results if r) == 1
    assert db.rows["j1"]["claimed_by"] in ("runner-a", "runner-b")


def test_second_claim_attempt_after_race_is_skipped():
    db = FakeDB([job("j1")])
    q = Queue(db, "runner-a", clock=lambda: T0)
    peeked = db.next_queued()
    db.update_if_status(peeked["id"], ["queued"], {"status": "running", "claimed_by": "runner-b"})
    # runner-a saw the job as queued, but the conditional update must refuse it
    assert db.update_if_status(peeked["id"], ["queued"], {"status": "running", "claimed_by": "runner-a"}) is False
    assert q.claim_next() is None
    assert db.rows["j1"]["claimed_by"] == "runner-b"


def test_oldest_job_first_and_heartbeat_row_is_never_a_job():
    db = FakeDB([heartbeat_row(), job("new", created="2026-10-20T08:30:00+00:00"), job("old", created="2026-10-20T08:00:00+00:00")])
    q = Queue(db, "runner-mac", clock=lambda: T0)
    assert q.claim_next()["id"] == "old"
    assert db.rows["hb"]["status"] == "running"


def test_cancel_requested_before_start_is_marked_cancelled():
    db = FakeDB([job("j1")])
    q = Queue(db, "runner-mac", clock=lambda: T0)
    claimed = q.claim_next()
    db.rows["j1"]["status"] = "cancel_requested"
    assert handle(claimed, q) == "cancelled"
    assert db.rows["j1"]["status"] == "cancelled"


def test_unknown_kind_is_an_execution_error_not_a_product_failure():
    db = FakeDB([job("j1", kind="report_pdf")])
    q = Queue(db, "runner-mac", clock=lambda: T0)
    assert handle(q.claim_next(), q) == "error"
    assert db.rows["j1"]["status"] == "error"
    assert "not implemented" in db.rows["j1"]["error"]


def test_stale_running_job_of_this_runner_becomes_error_on_startup():
    old = (T0 - timedelta(minutes=5)).isoformat()
    fresh = (T0 - timedelta(seconds=30)).isoformat()
    db = FakeDB([
        job("stale", status="running", claimed_by="runner-mac", heartbeat_at=old),
        job("fresh", status="running", claimed_by="runner-mac", heartbeat_at=fresh),
        job("other", status="running", claimed_by="runner-other", heartbeat_at=old),
    ])
    q = Queue(db, "runner-mac", clock=lambda: T0)
    assert q.recover_stale(120) == 1
    assert db.rows["stale"]["status"] == "error"
    assert db.rows["fresh"]["status"] == "running"
    assert db.rows["other"]["status"] == "running"


def test_missing_heartbeat_row_is_reported():
    db = FakeDB([])
    q = Queue(db, "runner-mac", clock=lambda: T0)
    assert q.beat() is False
