"""Reprova runner.

  python -m reprova_runner init-config        write an example runner.json (no secrets)
  python -m reprova_runner set-secret NAME    store a secret in the Keychain (runner-password, webhook-secret,
                                              or a client credential <project_id>/<ref>)
  python -m reprova_runner check              sign in, write one heartbeat, ping n8n
  python -m reprova_runner once               process at most one queued job
  python -m reprova_runner run                poll the queue until Ctrl+C
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from . import config as cfgmod
from . import secrets
from .db import Database
from .db import SupabaseDatabase
from .queue import Queue
from .triage_client import TriageClient
from .worker import handle

log = logging.getLogger("reprova_runner")


def connect(cfg: cfgmod.Config):
    from supabase import create_client

    client = create_client(cfg.supabase_url, cfg.supabase_anon_key)
    client.auth.sign_in_with_password({"email": cfg.runner_email, "password": secrets.get(secrets.RUNNER_PASSWORD)})
    session = client.auth.get_session()
    role = (session.user.app_metadata or {}).get("role") if session and session.user else None
    if role != "runner":
        raise SystemExit(f'User {cfg.runner_email} must have app_metadata.role = "runner" (found: {role!r}).')
    return client


def cmd_check(cfg: cfgmod.Config) -> int:
    client = connect(cfg)
    db = SupabaseDatabase(client)
    q = Queue(db, cfg.runner_id)
    print("Supabase: signed in as runner")
    report = secret_report(db)
    print("Heartbeat:", "ok" if q.beat(output=report) else "row missing (run supabase/seed.sql)")
    if report:
        for account, ok in sorted(report["secret_refs"].items()):
            print(f"  Keychain {account}: {'found' if ok else 'MISSING'}")
    try:
        reply = TriageClient(cfg.n8n_triage_url, secrets.get(secrets.WEBHOOK_SECRET), timeout=10).ping()
        print("n8n triage:", reply)
    except Exception as exc:
        print("n8n triage: FAILED -", exc)
        return 1
    return 0


def secret_report(db: Database) -> dict | None:
    """Names of client credential refs found in the Keychain (F04), shown by Readiness."""
    try:
        return {"secret_refs": secrets.presence(db.project_targets()), "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    except Exception as exc:
        log.warning("could not check credential refs: %s", exc)
        return None


def loop(cfg: cfgmod.Config, once: bool) -> int:
    client = connect(cfg)
    db = SupabaseDatabase(client)
    q = Queue(db, cfg.runner_id)
    q.recover_stale(cfg.stale_seconds)
    try:
        TriageClient(cfg.n8n_triage_url, secrets.get(secrets.WEBHOOK_SECRET), timeout=10).ping()
        log.info("n8n triage webhook reachable")
    except Exception as exc:
        log.warning("n8n triage webhook not reachable: %s", exc)

    last_beat = 0.0
    log.info("runner %s started (poll %ss, heartbeat %ss)", cfg.runner_id, cfg.poll_seconds, cfg.heartbeat_seconds)
    while True:
        now = time.monotonic()
        if now - last_beat >= cfg.heartbeat_seconds:
            q.beat(output=secret_report(db))
            last_beat = now
        job = q.claim_next()
        if job:
            handle(job, q, cfg.work_dir)
            q.beat(output=secret_report(db))
            last_beat = time.monotonic()
            if once:
                return 0
        elif once:
            log.info("no queued job")
            return 0
        time.sleep(cfg.poll_seconds)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="python -m reprova_runner")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-config")
    s = sub.add_parser("set-secret")
    s.add_argument("name", help="runner-password | webhook-secret | <project_id>/<ref>")
    sub.add_parser("check")
    sub.add_parser("once")
    sub.add_parser("run")
    args = p.parse_args(argv)

    if args.cmd == "init-config":
        print("Wrote", cfgmod.write_example())
        return 0
    if args.cmd == "set-secret":
        secrets.set_interactive(args.name)
        return 0
    cfg = cfgmod.load()
    if args.cmd == "check":
        return cmd_check(cfg)
    try:
        return loop(cfg, once=args.cmd == "once")
    except KeyboardInterrupt:
        log.info("stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
