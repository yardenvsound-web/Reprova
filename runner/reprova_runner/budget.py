"""Time budget for a run (projects.budget.max_minutes). The AI cost budget arrives with triage."""
from __future__ import annotations

import time
from typing import Callable


class Budget:
    def __init__(self, max_minutes: float, clock: Callable[[], float] = time.monotonic):
        self.max_seconds = max(0.0, float(max_minutes or 0)) * 60
        self.clock = clock
        self.start = clock()

    def elapsed_minutes(self) -> float:
        return (self.clock() - self.start) / 60

    def exceeded(self) -> bool:
        return bool(self.max_seconds) and (self.clock() - self.start) >= self.max_seconds

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - (self.clock() - self.start)) if self.max_seconds else float("inf")
