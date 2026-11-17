"""Client for the local n8n triage webhook."""
from __future__ import annotations

from typing import Any

import httpx


class TriageClient:
    def __init__(self, url: str, secret: str, timeout: float = 60.0):
        self.url = url
        self.secret = secret
        self.timeout = timeout

    def post(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = httpx.post(self.url, json=payload, headers={"X-QA-Secret": self.secret}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def ping(self) -> dict[str, Any]:
        return self.post({"ping": True})
