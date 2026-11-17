"""Minimal re-run of failed cases (decided for Milestone 2; full F25 with AI triage is Milestone 4).

A case that failed is run again `attempts` more times. If any re-run passes, the case is flaky,
not failed. Only `failed` is re-run: `error` and `blocked` are not product behaviour.
"""
from __future__ import annotations

from typing import Callable

from .results import NormalizedTestResult


def attempt_record(n: int, r: NormalizedTestResult) -> dict:
    return {"n": n, "state": r.state, "actual": r.actual, "duration_ms": r.duration_ms}


def run_with_repro(run_once: Callable[[int], NormalizedTestResult], attempts: int,
                   should_stop: Callable[[], bool] = lambda: False) -> NormalizedTestResult:
    first = run_once(1)
    first.attempts = [attempt_record(1, first)]
    if first.state != "failed" or attempts <= 0:
        return first
    for n in range(2, attempts + 2):
        if should_stop():
            break
        again = run_once(n)
        first.attempts.append(attempt_record(n, again))
        first.evidence += [e for e in again.evidence if e not in first.evidence]
    reruns = [a for a in first.attempts[1:]]
    if any(a["state"] == "passed" for a in reruns):
        first.state = "flaky"
        failed = sum(1 for a in first.attempts if a["state"] == "failed")
        first.actual = f"{first.actual} (failed {failed} of {len(first.attempts)} attempts)"
    return first
