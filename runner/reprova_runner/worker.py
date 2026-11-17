"""What the runner does with a claimed job."""
from __future__ import annotations

import logging
from typing import Any

from .executor import Executor
from .queue import Queue

log = logging.getLogger("reprova_runner.worker")


def handle(job: dict[str, Any], queue: Queue, work_dir: str | None = None, **executor_kw) -> str:
    run_id = job["id"]
    try:
        if queue.cancel_requested(run_id):
            queue.mark_cancelled(run_id)
            return "cancelled"
        if job["kind"] in ("test_run", "retest"):
            queue.beat(run_id)
            if job.get("plan_version") is None:
                # Walking-skeleton job (no plan attached): nothing to execute.
                queue.finish(run_id, results=[])
                log.info("job %s done (no Test Plan attached)", run_id)
                return "done"
            return Executor(job, queue, work_dir or ".", **executor_kw).run()
        queue.fail(run_id, f"job kind '{job['kind']}' is not implemented yet (arrives in a later milestone)")
        return "error"
    except Exception as exc:  # an engine problem is an execution error, not a product bug
        log.exception("job %s failed", run_id)
        queue.fail(run_id, f"{type(exc).__name__}: {exc}")
        return "error"
