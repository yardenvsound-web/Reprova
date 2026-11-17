"""In-memory stand-ins for Supabase, used by the runner tests (no network)."""
from __future__ import annotations

import copy
import threading


class FakeDB:
    """Mimics conditional updates atomically, like a single SQL UPDATE ... WHERE status IN (...)."""

    def __init__(self, rows):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.lock = threading.Lock()
        self.projects: dict = {}
        self.uploads: dict = {}

    def next_queued(self):
        with self.lock:
            q = [r for r in self.rows.values() if r["status"] == "queued" and r["kind"] != "runner_heartbeat"]
            q.sort(key=lambda r: r["created_at"])
            return copy.deepcopy(q[0]) if q else None

    def update_if_status(self, run_id, expected, fields):
        with self.lock:
            r = self.rows.get(run_id)
            if not r or r["status"] not in expected:
                return False
            r.update(fields)
            return True

    def stale_running(self, runner_id, older_than_iso):
        return [dict(r) for r in self.rows.values()
                if r["status"] == "running" and r.get("claimed_by") == runner_id
                and r["kind"] != "runner_heartbeat" and (r.get("heartbeat_at") or "") < older_than_iso]

    def update_heartbeat(self, runner_id, at_iso, output=None):
        with self.lock:
            for r in self.rows.values():
                if r["kind"] == "runner_heartbeat" and r.get("claimed_by") == runner_id:
                    r["heartbeat_at"] = at_iso
                    if output is not None:
                        r["output"] = output
                    return True
            return False

    def get_status(self, run_id):
        return self.rows[run_id]["status"] if run_id in self.rows else None


    # Milestone 2 ---------------------------------------------------------------

    def get_project(self, project_id):
        return copy.deepcopy(self.projects.get(project_id))

    def project_targets(self):
        return [{"id": p["id"], "targets": p.get("targets", [])} for p in self.projects.values()]

    def upload(self, bucket, path, data, content_type):
        self.uploads[(bucket, path)] = data
