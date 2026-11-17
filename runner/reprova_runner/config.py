"""Runner configuration.

Lives outside the repo, in ~/Library/Application Support/Reprova/runner.json.
It holds no secrets: passwords live in the macOS Keychain (see secrets.py).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path.home() / "Library" / "Application Support" / "Reprova" / "runner.json"

EXAMPLE = {
    "supabase_url": "https://wnqxqtbmadoetwwyceun.supabase.co",
    "supabase_anon_key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InducXhxdGJtYWRvZXR3d3ljZXVuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQ3NzA5ODksImV4cCI6MjExMDM0Njk4OX0.5m4BLR9N4Rdp-ElQs-0pHw_EbWT4LnLyC8Tdhl5zqwE",
    "runner_email": "runner@example.com",
    "runner_id": "runner-mac",
    "n8n_triage_url": "https://homieyarden.app.n8n.cloud/webhook/reprova-triage",
    "work_dir": str(Path.home() / "Reprova Work"),
    "poll_seconds": 5,
    "heartbeat_seconds": 30,
    "stale_seconds": 120,
}


@dataclass(frozen=True)
class Config:
    supabase_url: str
    supabase_anon_key: str
    runner_email: str
    runner_id: str
    n8n_triage_url: str
    work_dir: str
    poll_seconds: int = 5
    heartbeat_seconds: int = 30
    stale_seconds: int = 120


def config_path() -> Path:
    return Path(os.environ.get("REPROVA_RUNNER_CONFIG", DEFAULT_PATH))


def load(path: Path | None = None) -> Config:
    p = path or config_path()
    if not p.is_file():
        raise SystemExit(
            f"Runner config not found: {p}\n"
            f"Create it with:  python -m reprova_runner init-config"
        )
    data = json.loads(p.read_text(encoding="utf-8"))
    known = {k: data[k] for k in Config.__dataclass_fields__ if k in data}
    missing = [k for k in ("supabase_url", "supabase_anon_key", "runner_email", "runner_id", "n8n_triage_url", "work_dir") if k not in known]
    if missing:
        raise SystemExit(f"Runner config {p} is missing: {', '.join(missing)}")
    return Config(**known)


def write_example(path: Path | None = None) -> Path:
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        raise SystemExit(f"{p} already exists; edit it instead.")
    p.write_text(json.dumps(EXAMPLE, indent=2) + "\n", encoding="utf-8")
    return p
