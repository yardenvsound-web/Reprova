"""Job queue protocol (ARCHITECTURE.md, section 5)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .db import Database

log = logging.getLogger("reprova_runner.queue")

EMPTY_SUMMARY = {"passed": 0, "failed": 0, "error": 0, "blocked": 0, "skipped": 0, "flaky": 0}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


class Queue:
    def __init__(self, db: Database, runner_id: str, clock: Callable[[], datetime] = utcnow):
        self.db = db
        self.runner_id = runner_id
        self.clock = clock

    # -- claiming ------------------------------------------------------------
    def claim_next(self) -> dict[str, Any] | None:
        job = self.db.next_queued()
        if not job:
            return None
        now = iso(self.clock())
        ok = self.db.update_if_status(
            job["id"], ["queued"],
            {"status": "running", "claimed_by": self.runner_id, "claimed_at": now,
             "heartbeat_at": now, "started_at": now},
        )
        if not ok:
            log.info("job %s was taken by someone else, skipping", job["id"])
            return None
        log.info("claimed job %s (%s)", job["id"], job["kind"])
        return job

    # -- progress ------------------------------------------------------------
    def beat(self, run_id: str | None = None) -> bool:
        now = iso(self.clock())
        ok = self.db.update_heartbeat(self.runner_id, now)
        if not ok:
            log.warning("heartbeat row for %s not found; run seed.sql", self.runner_id)
        if run_id:
            self.db.update_if_status(run_id, ["running", "cancel_requested"], {"heartbeat_at": now})
        return ok

    def cancel_requested(self, run_id: str) -> bool:
        return self.db.get_status(run_id) == "cancel_requested"

    # -- finishing -----------------------------------------------------------
    def finish(self, run_id: str, *, summary: dict | None = None, results: list | None = None) -> bool:
        fields: dict[str, Any] = {"status": "done", "finished_at": iso(self.clock()),
                                  "summary": summary or dict(EMPTY_SUMMARY)}
        if results is not None:
            fields["results"] = results
        return self.db.update_if_status(run_id, ["running"], fields)

    def fail(self, run_id: str, error: str) -> bool:
        """Execution error: a problem in our engine, never a product bug."""
        return self.db.update_if_status(
            run_id, ["running", "cancel_requested"],
            {"status": "error", "error": error[:2000], "finished_at": iso(self.clock())},
        )

    def mark_cancelled(self, run_id: str) -> bool:
        return self.db.update_if_status(
            run_id, ["cancel_requested"], {"status": "cancelled", "finished_at": iso(self.clock())}
        )

    # -- recovery ------------------------------------------------------------
    def recover_stale(self, stale_seconds: int) -> int:
        """On startup: jobs this runner left 'running' with an old heartbeat become errors."""
        cutoff = iso(self.clock() - timedelta(seconds=stale_seconds))
        count = 0
        for row in self.db.stale_running(self.runner_id, cutoff):
            if self.fail(row["id"], "runner stopped during the run (stale heartbeat)"):
                count += 1
        if count:
            log.warning("marked %d stale run(s) as execution error", count)
        return count
