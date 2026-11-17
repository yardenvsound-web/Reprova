"""Secrets live only in the macOS Keychain (approved exception to the course stack).

Service name: "reprova". Accounts:
  runner-password            password of the Supabase "runner" user
  webhook-secret             value sent as X-QA-Secret to n8n
  <project_id>/<ref>         client credentials (F04); Supabase stores only the ref name

Values are never written to files, logs or Supabase.
"""
from __future__ import annotations

import getpass

import keyring

SERVICE = "reprova"
RUNNER_PASSWORD = "runner-password"
WEBHOOK_SECRET = "webhook-secret"


def get(account: str) -> str:
    value = keyring.get_password(SERVICE, account)
    if not value:
        raise SystemExit(
            f'Secret "{account}" is not in the Keychain.\n'
            f"Add it with:  python -m reprova_runner set-secret {account}"
        )
    return value


def has(account: str) -> bool:
    return bool(keyring.get_password(SERVICE, account))


def client_account(project_id: str, ref: str) -> str:
    return f"{project_id}/{ref}"


def get_client(project_id: str, ref: str) -> str | None:
    """A client credential for one run, or None when it is missing. Never logged."""
    return keyring.get_password(SERVICE, client_account(project_id, ref)) or None


def presence(projects: list[dict]) -> dict[str, bool]:
    """Which secret_refs of each project's targets exist in the Keychain: names only, never values.
    Reported on the heartbeat row so Readiness can show what is missing (decided for Milestone 2)."""
    found: dict[str, bool] = {}
    for p in projects:
        for t in p.get("targets") or []:
            for ref in t.get("secret_refs") or []:
                account = client_account(p["id"], ref)
                found[account] = has(account)
    return found


def set_interactive(account: str) -> None:
    value = getpass.getpass(f'Value for "{account}" (input hidden): ')
    if not value:
        raise SystemExit("Empty value, nothing saved.")
    keyring.set_password(SERVICE, account, value)
    print(f'Saved "{account}" in the Keychain (service "{SERVICE}").')
