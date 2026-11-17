"""Secrets live only in the macOS Keychain (approved exception to the course stack).

Service name: "reprova". Accounts:
  runner-password            password of the Supabase "runner" user
  webhook-secret             value sent as X-QA-Secret to n8n
  <project>/<ref>            client credentials (from Milestone 2)

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


def set_interactive(account: str) -> None:
    value = getpass.getpass(f'Value for "{account}" (input hidden): ')
    if not value:
        raise SystemExit("Empty value, nothing saved.")
    keyring.set_password(SERVICE, account, value)
    print(f'Saved "{account}" in the Keychain (service "{SERVICE}").')
