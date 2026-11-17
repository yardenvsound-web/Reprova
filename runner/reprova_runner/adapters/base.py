"""The runner ↔ adapter contract (ARCHITECTURE.md, section 5).

A new engine is a new file in this folder plus a catalog entry; the core does not change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..results import NormalizedTestResult


@dataclass
class RunContext:
    project_id: str
    run_id: str
    work_dir: Path                         # temporary evidence folder for this run
    secrets: dict[str, str] = field(default_factory=dict)   # ref -> value, read from the Keychain
    case_timeout_s: float = 60.0
    log: list[str] = field(default_factory=list)


class TestAdapter:
    __test__ = False   # not a pytest test class
    name = "base"

    def __init__(self, target: dict[str, Any], ctx: RunContext):
        self.target = target
        self.ctx = ctx

    def validate_configuration(self) -> str | None:
        """None when the target can be tested; otherwise why every case is blocked
        (for example: the environment is down). Never a product failure."""
        return None

    def discover_capabilities(self) -> dict[str, Any]:
        return {}

    def execute(self, case: dict[str, Any], attempt: int = 1) -> NormalizedTestResult:
        raise NotImplementedError

    def cleanup(self) -> None:
        pass

    # helpers shared by adapters ------------------------------------------------
    def result(self, case: dict[str, Any], state: str, **kw) -> NormalizedTestResult:
        kw.setdefault("expected", case.get("expected", ""))
        return NormalizedTestResult(
            test_case_id=case["id"], target_id=self.target["id"], adapter=self.name,
            access_mode=self.target.get("access_mode", "black_box"), state=state,
            title=case.get("title", ""), **kw)

    def secret(self, ref: str) -> str:
        if ref not in self.ctx.secrets:
            raise LookupError(f'credential ref "{ref}" is not in the Keychain')
        return self.ctx.secrets[ref]

    def safe_name(self, case_id: str, attempt: int, suffix: str) -> Path:
        stem = "".join(x for x in case_id if x.isalnum() or x in "-_.")
        tag = "" if attempt == 1 else f"_try{attempt}"
        return self.ctx.work_dir / f"{self.target['id']}_{stem}{tag}{suffix}"
