"""Thin database layer over Supabase, so queue logic can be tested with a fake."""
from __future__ import annotations

from typing import Any, Protocol

JOB_KINDS = ("test_run", "retest", "report_pdf")


class Database(Protocol):
    def next_queued(self) -> dict[str, Any] | None: ...
    def update_if_status(self, run_id: str, expected: list[str], fields: dict[str, Any]) -> bool: ...
    def stale_running(self, runner_id: str, older_than_iso: str) -> list[dict[str, Any]]: ...
    def update_heartbeat(self, runner_id: str, at_iso: str, output: dict | None = None) -> bool: ...
    def get_status(self, run_id: str) -> str | None: ...
    def get_project(self, project_id: str) -> dict[str, Any] | None: ...
    def project_targets(self) -> list[dict[str, Any]]: ...
    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None: ...


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

    def update_heartbeat(self, runner_id, at_iso, output=None):
        fields = {"heartbeat_at": at_iso}
        if output is not None:
            fields["output"] = output
        res = (
            self.c.table("runs").update(fields)
            .eq("kind", "runner_heartbeat").eq("claimed_by", runner_id).execute()
        )
        return bool(res.data)

    def get_status(self, run_id):
        res = self.c.table("runs").select("status").eq("id", run_id).limit(1).execute()
        return res.data[0]["status"] if res.data else None

    def get_project(self, project_id):
        res = self.c.table("projects").select("*").eq("id", project_id).limit(1).execute()
        return res.data[0] if res.data else None

    def project_targets(self):
        res = self.c.table("projects").select("id, targets").neq("status", "closed").execute()
        return res.data or []

    def upload(self, bucket, path, data, content_type):
        self.c.storage.from_(bucket).upload(path, data, {"content-type": content_type, "upsert": "true"})
