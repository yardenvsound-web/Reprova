"""What the runner does with a claimed job.

Milestone 1 (Walking Skeleton): a test_run with no approved cases finishes as done
with an empty summary. Real execution through adapters arrives in Milestone 2.
"""
from __future__ import annotations

import logging
from typing import Any

from .queue import Queue

log = logging.getLogger("reprova_runner.worker")


def handle(job: dict[str, Any], queue: Queue) -> str:
    run_id = job["id"]
    try:
        if queue.cancel_requested(run_id):
            queue.mark_cancelled(run_id)
            return "cancelled"
        if job["kind"] in ("test_run", "retest"):
            queue.beat(run_id)
            queue.finish(run_id, results=[])
            log.info("job %s done (walking skeleton: no test cases yet)", run_id)
            return "done"
        queue.fail(run_id, f"job kind '{job['kind']}' is not implemented yet (arrives in a later milestone)")
        return "error"
    except Exception as exc:  # an engine problem is an execution error, not a product bug
        log.exception("job %s failed", run_id)
        queue.fail(run_id, f"{type(exc).__name__}: {exc}")
        return "error"
