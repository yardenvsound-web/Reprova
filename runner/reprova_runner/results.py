"""The engine-independent result contract (from the PoC), stored in runs.results.

An adapter returns one of five states. The runner adds the sixth, `flaky`, after re-running
a failed case (repro.py): a case that fails and then passes on a re-run is flaky, not failed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

State = Literal["passed", "failed", "error", "blocked", "skipped", "flaky"]
STATES: tuple[str, ...] = ("passed", "failed", "error", "blocked", "skipped", "flaky")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class NormalizedTestResult:
    test_case_id: str
    target_id: str
    adapter: str
    access_mode: str
    state: State
    title: str = ""
    expected: str = ""
    actual: str = ""
    execution_error: str = ""          # set only when state == "error" (our engine, not the product)
    duration_ms: int = 0
    started_at: str = ""
    finished_at: str = ""
    evidence: list[str] = field(default_factory=list)   # local file names, then storage paths
    attempts: list[dict] = field(default_factory=list)  # [{n, state, actual, duration_ms}]

    def to_dict(self) -> dict:
        return asdict(self)


def summarize(results: list[dict]) -> dict[str, int]:
    summary = {s: 0 for s in STATES}
    for r in results:
        summary[r["state"]] = summary.get(r["state"], 0) + 1
    return summary
