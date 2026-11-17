"""Thin database layer over Supabase, so queue logic can be tested with a fake."""
from __future__ import annotations

from typing import Any, Protocol

JOB_KINDS = ("test_run", "retest", "report_pdf")


class Database(Protocol):
    def next_queued(self) -> dict[str, Any] | None: ...
    def update_if_status(self, run_id: str, expected: list[str], fields: dict[str, Any]) -> bool: ...
    def stale_running(self, runner_id: str, older_than_iso: str) -> list[dict[str, Any]]: ...
    def update_heartbeat(self, runner_id: str, at_iso: str) -> bool: ...
    def get_status(self, run_id: str) -> str | None: ...


class SupabaseDatabase:
    def __init__(self, client: Any):
        self.c = client

    def next_queued(self):
        res = (
            self.c.table("runs").select("*")
            .eq("status", "queued").in_("kind", list(JOB_KINDS))
            .order("created_at").limit(1).execute()
        )
        return res.data[0] if res.data else None

    def update_if_status(self, run_id, expected, fields):
        # Conditional update: only rows still in an expected status change.
        res = (
            self.c.table("runs").update(fields)
            .eq("id", run_id).in_("status", expected).execute()
        )
        return bool(res.data)

    def stale_running(self, runner_id, older_than_iso):
        res = (
            self.c.table("runs").select("id, heartbeat_at, claimed_at")
            .eq("status", "running").eq("claimed_by", runner_id)
            .in_("kind", list(JOB_KINDS))
            .lt("heartbeat_at", older_than_iso).execute()
        )
        return res.data or []

    def update_heartbeat(self, runner_id, at_iso):
        res = (
            self.c.table("runs").update({"heartbeat_at": at_iso})
            .eq("kind", "runner_heartbeat").eq("claimed_by", runner_id).execute()
        )
        return bool(res.data)

    def get_status(self, run_id):
        res = self.c.table("runs").select("status").eq("id", run_id).limit(1).execute()
        return res.data[0]["status"] if res.data else None
