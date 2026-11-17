"""F05: remove secrets and PII from logs and evidence before they leave the Mac.

Two layers:
  1. exact values: every secret the run read from the Keychain is replaced by its ref name;
  2. patterns: common secret and PII shapes (tokens, JWTs, emails, card and phone numbers).

Applied to result text, text evidence files and the text members of Playwright trace zips,
before upload and before anything is sent to the AI.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Authorization headers and bearer tokens
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [REDACTED]"),
    # JSON Web Tokens
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[REDACTED:jwt]"),
    # key=value and "key": "value" for secret-looking keys
    # (the closing quote is not consumed, so JSON stays valid)
    (re.compile(r"(?i)(\"?(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|authorization)\"?\s*[:=]\s*)(\"?)(?!\[REDACTED)[^\s\",;&<>]+"),
     r"\1\2[REDACTED]"),
    # email addresses
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED:email]"),
]

# Number shapes would corrupt timestamps inside structured files (trace JSON, JUnit XML),
# so they are applied to plain text only.
NUMBER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # payment card numbers (13 to 19 digits, optional spaces or dashes)
    (re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), "[REDACTED:number]"),
    # phone numbers such as +972-50-123-4567 or 050 123 4567
    (re.compile(r"(?<![\w.])\+?\d{1,3}[ -]?\(?\d{2,3}\)?[ -]?\d{3}[ -]?\d{4}\b"), "[REDACTED:phone]"),
]

PLAIN_SUFFIXES = {".log", ".txt", ".md", ".csv"}
STRUCTURED_SUFFIXES = {".json", ".xml", ".html", ".har", ".network", ".trace"}


class Redactor:
    def __init__(self, secrets: dict[str, str] | None = None):
        # longest first, so a secret that contains another is replaced whole
        self.secrets = sorted(((ref, v) for ref, v in (secrets or {}).items() if v), key=lambda x: -len(x[1]))

    def text(self, s: str | None, structured: bool = False) -> str:
        if not s:
            return s or ""
        for ref, value in self.secrets:
            s = s.replace(value, f"[REDACTED:{ref}]")
        for pattern, repl in PATTERNS if structured else PATTERNS + NUMBER_PATTERNS:
            s = pattern.sub(repl, s)
        return s

    def obj(self, value):
        """Redact every string inside a JSON-like value."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.obj(v) for v in value]
        if isinstance(value, dict):
            return {k: self.obj(v) for k, v in value.items()}
        return value

    def bytes_(self, data: bytes, structured: bool = False) -> bytes:
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError:
            # binary content: still remove exact secret values if they appear as raw bytes
            for ref, value in self.secrets:
                data = data.replace(value.encode(), f"[REDACTED:{ref}]".encode())
            return data
        return self.text(decoded, structured).encode("utf-8")

    def file(self, path: Path) -> Path:
        """Redact a file in place. Text files and zip members are rewritten; images are left as is."""
        if path.suffix == ".zip":
            self._zip(path)
        elif path.suffix in PLAIN_SUFFIXES | STRUCTURED_SUFFIXES:
            path.write_bytes(self.bytes_(path.read_bytes(), structured=path.suffix in STRUCTURED_SUFFIXES))
        return path

    def _zip(self, path: Path) -> None:
        tmp = path.with_suffix(".redacting.zip")
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if not info.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    data = self.bytes_(data, structured=True)
                dst.writestr(info, data)
        tmp.replace(path)
