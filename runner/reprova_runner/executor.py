"""Runs an approved Test Plan for one claimed test_run (F03, F08, F15, F16).

Order of checks for every case:
  cancel requested        -> stop, keep what is done, mark the run cancelled
  not selected in the plan -> skipped
  time budget exceeded     -> skipped (the run stops; partial results are kept)
  missing credential ref   -> blocked
  environment unreachable  -> blocked (never failed)
  otherwise the adapter runs it; a failed case is re-run (repro.py) and may become flaky.
Everything that leaves the Mac goes through the Redactor first (F05).
"""
from __future__ import annotations

import logging
import mimetypes
import shutil
from pathlib import Path
from typing import Any, Callable

from . import secrets as secretsmod
from .adapters import ADAPTERS, RunContext, TestAdapter
from .budget import Budget
from .queue import Queue
from .redact import Redactor
from .repro import run_with_repro
from .results import NormalizedTestResult, now_iso, summarize

log = logging.getLogger("reprova_runner.executor")

EVIDENCE_BUCKET = "evidence"


class PlanError(Exception):
    """The job cannot run as queued (no approved plan, wrong version): an execution error."""


def _skipped(case: dict, target: dict | None, reason: str) -> NormalizedTestResult:
    return NormalizedTestResult(
        test_case_id=case["id"], target_id=case.get("target_id", ""), adapter=case.get("adapter", ""),
        access_mode=(target or {}).get("access_mode", "black_box"), state="skipped",
        title=case.get("title", ""), expected=case.get("expected", ""), actual=reason,
        started_at=now_iso(), finished_at=now_iso())


def _blocked(case: dict, target: dict | None, reason: str) -> NormalizedTestResult:
    r = _skipped(case, target, reason)
    r.state = "blocked"
    return r


def _error(case: dict, target: dict | None, detail: str) -> NormalizedTestResult:
    r = _skipped(case, target, "Execution error (engine)")
    r.state, r.execution_error = "error", detail[:500]
    return r


class Executor:
    def __init__(self, job: dict[str, Any], queue: Queue, work_dir: str | Path,
                 secret_lookup: Callable[[str, str], str | None] = secretsmod.get_client,
                 adapters: dict[str, type[TestAdapter]] | None = None,
                 budget_clock: Callable[[], float] | None = None):
        self.job = job
        self.q = queue
        self.db = queue.db
        self.run_id = job["id"]
        self.root = Path(work_dir)
        self.secret_lookup = secret_lookup
        self.adapters = adapters or ADAPTERS
        self.budget_clock = budget_clock
        self.results: list[dict] = []
        self.evidence_paths: list[str] = []
        self.upload_failed = False

    # ---------------------------------------------------------------- setup
    def load_plan(self) -> tuple[dict, list[dict], dict[str, dict]]:
        project = self.db.get_project(self.job["project_id"])
        if not project:
            raise PlanError("project not found or not readable by the runner")
        plan = project.get("test_plan") or {}
        if plan.get("status") != "approved":
            raise PlanError("the Test Plan is not approved; only an approved plan runs")
        if self.job.get("plan_version") is not None and plan.get("version") != self.job["plan_version"]:
            raise PlanError(f"plan v{self.job['plan_version']} was queued but the approved plan is "
                            f"v{plan.get('version')}; queue the run again")
        targets = {t["id"]: t for t in project.get("targets") or []}
        return project, plan.get("cases") or [], targets

    # ---------------------------------------------------------------- run
    def run(self) -> str:
        try:
            project, cases, targets = self.load_plan()
        except PlanError as exc:
            self.q.fail(self.run_id, f"Execution error: {exc}")
            return "error"

        pid = project["id"]
        budget_cfg = project.get("budget") or {}
        budget = (Budget(budget_cfg.get("max_minutes", 60), self.budget_clock) if self.budget_clock
                  else Budget(budget_cfg.get("max_minutes", 60)))
        attempts = int(budget_cfg.get("repro_attempts", 3))

        used_targets = {c.get("target_id") for c in cases}
        found: dict[str, str] = {}
        missing: dict[str, list[str]] = {}
        for tid in used_targets:
            for ref in (targets.get(tid) or {}).get("secret_refs") or []:
                value = self.secret_lookup(pid, ref)
                if value:
                    found[ref] = value
                else:
                    missing.setdefault(tid, []).append(ref)
        redactor = Redactor(found)

        work = self.root / pid / self.run_id
        work.mkdir(parents=True, exist_ok=True)
        ctx = RunContext(project_id=pid, run_id=self.run_id, work_dir=work, secrets=found)
        live: dict[str, TestAdapter] = {}
        blocked_reason: dict[str, str | None] = {}
        stop: str | None = None
        log.info("run %s: %d case(s), budget %s min, %d repro attempt(s)",
                 self.run_id, len(cases), budget_cfg.get("max_minutes", 60), attempts)
        try:
            for case in cases:
                if self.q.cancel_requested(self.run_id):
                    stop = "cancelled"
                    break
                target = targets.get(case.get("target_id"))
                if not case.get("selected", True):
                    r = _skipped(case, target, "Not selected in the Test Plan")
                elif stop == "budget" or budget.exceeded():
                    stop = "budget"
                    r = _skipped(case, target, "Not run: the time budget was exceeded")
                elif target is None:
                    r = _error(case, None, f"case refers to unknown target {case.get('target_id')!r}")
                elif missing.get(target["id"]):
                    refs = ", ".join(missing[target["id"]])
                    r = _blocked(case, target, f"Credential ref not in the Keychain: {refs}")
                else:
                    adapter_cls = self.adapters.get(case.get("adapter", ""))
                    if adapter_cls is None:
                        r = _error(case, target, f"no adapter named {case.get('adapter')!r}")
                    else:
                        if target["id"] not in live:
                            live[target["id"]] = adapter_cls(target, ctx)
                            blocked_reason[target["id"]] = live[target["id"]].validate_configuration()
                        if blocked_reason[target["id"]]:
                            r = _blocked(case, target, blocked_reason[target["id"]])
                        else:
                            ctx.case_timeout_s = min(60.0, max(5.0, budget.remaining_seconds()))
                            adapter = live[target["id"]]
                            try:
                                r = run_with_repro(lambda n: adapter.execute(case, n), attempts,
                                                   should_stop=budget.exceeded)
                            except Exception as exc:  # an adapter crash is our problem, not the product's
                                log.exception("adapter crashed on %s", case.get("id"))
                                r = _error(case, target, f"{type(exc).__name__}: {exc}")
                self._record(r, redactor, work, pid)
        finally:
            for a in live.values():
                a.cleanup()

        return self._close(stop, budget, work)

    # ---------------------------------------------------------------- per case
    def _record(self, r: NormalizedTestResult, redactor: Redactor, work: Path, pid: str) -> None:
        r.actual = redactor.text(r.actual)
        r.expected = redactor.text(r.expected)
        r.execution_error = redactor.text(r.execution_error)
        r.attempts = redactor.obj(r.attempts)
        uploaded = []
        for name in r.evidence:
            local = work / name
            if not local.exists():
                continue
            redactor.file(local)
            path = f"{pid}/{self.run_id}/{name}"
            try:
                ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
                self.db.upload(EVIDENCE_BUCKET, path, local.read_bytes(), ctype)
                uploaded.append(path)
            except Exception as exc:
                self.upload_failed = True
                log.warning("evidence upload failed for %s: %s", name, exc)
        r.evidence = uploaded
        self.evidence_paths += uploaded
        self.results.append(r.to_dict())
        self.q.progress(self.run_id, {"results": self.results, "summary": summarize(self.results),
                                      "evidence_paths": self.evidence_paths})
        self.q.beat()

    # ---------------------------------------------------------------- end of run
    def _close(self, stop: str | None, budget: Budget, work: Path) -> str:
        fields = {"results": self.results, "summary": summarize(self.results),
                  "evidence_paths": self.evidence_paths}
        if not self.upload_failed:
            shutil.rmtree(work, ignore_errors=True)   # evidence is in Storage now
        if stop == "cancelled" or self.q.cancel_requested(self.run_id):
            self.q.mark_cancelled(self.run_id, fields)
            log.info("run %s cancelled after %d case(s)", self.run_id, len(self.results))
            return "cancelled"
        if stop == "budget":
            fields["error"] = (f"Stopped: time budget of {budget.max_seconds / 60:.0f} min exceeded "
                               f"after {budget.elapsed_minutes():.1f} min; partial results kept")
        if self.upload_failed:
            fields["error"] = ((fields.get("error") or "") + " Some evidence could not be uploaded; "
                               "it is kept in the runner's work folder.").strip()
        if not self.q.finish(self.run_id, summary=fields.pop("summary"), results=fields.pop("results"),
                             extra=fields):
            if self.q.cancel_requested(self.run_id):
                self.q.mark_cancelled(self.run_id, {"results": self.results, "summary": summarize(self.results),
                                                    "evidence_paths": self.evidence_paths})
                return "cancelled"
        log.info("run %s done: %s", self.run_id, summarize(self.results))
        return "done"
