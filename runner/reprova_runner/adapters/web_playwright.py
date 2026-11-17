"""F15: Web adapter (Playwright), from the PoC step runner.

Case steps:
  {"action": "goto", "path": "/"}
  {"action": "fill", "selector": "#nights", "value": "0"}
  {"action": "fill", "selector": "#password", "secret": "demo_web_login"}   value from the Keychain
  {"action": "click", "selector": "button[type=submit]"}
  {"action": "assert_text", "selector": "#message", "contains": "Please enter"}
"""
from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx

from ..results import now_iso
from .base import TestAdapter

# Navigation errors that mean "the environment is not there", not "the product is wrong".
UNREACHABLE = ("ERR_CONNECTION_REFUSED", "ERR_NAME_NOT_RESOLVED", "ERR_CONNECTION_TIMED_OUT",
               "ERR_ADDRESS_UNREACHABLE", "ERR_BLOCKED_BY_ADMINISTRATOR", "ERR_INTERNET_DISCONNECTED")


class WebPlaywrightAdapter(TestAdapter):
    name = "web_playwright"
    step_timeout_ms = 4000

    def __init__(self, target, ctx):
        super().__init__(target, ctx)
        self._pw = None
        self._browser = None

    @property
    def base_url(self) -> str:
        return self.target["location"].rstrip("/")

    def validate_configuration(self) -> str | None:
        try:
            httpx.get(self.base_url + "/", timeout=5, follow_redirects=False)
        except httpx.HTTPError as exc:
            return f"Environment unreachable: {type(exc).__name__} for {self.base_url}"
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
        except Exception as exc:  # missing browser is our setup problem: reported as error per case
            self.cleanup()
            self._setup_error = f"Playwright could not start: {exc}"[:400]
        return None

    def discover_capabilities(self) -> dict[str, Any]:
        return {"steps": ["goto", "fill", "click", "assert_text"], "evidence": ["log", "trace", "screenshot"]}

    def execute(self, case, attempt=1):
        started_at, t0 = now_iso(), perf_counter()
        log_path = self.safe_name(case["id"], attempt, ".log")
        lines = [f"case {case['id']} attempt {attempt} on {self.base_url}"]
        if getattr(self, "_setup_error", None) or not self._browser:
            return self.result(case, "error", execution_error=getattr(self, "_setup_error", "browser not started"),
                               actual="Execution error (engine)", started_at=started_at, finished_at=now_iso())

        context = self._browser.new_context(accept_downloads=False)
        page = context.new_page()
        page.set_default_timeout(self.step_timeout_ms)
        page.on("console", lambda m: lines.append(f"console.{m.type}: {m.text}"))
        page.on("pageerror", lambda e: lines.append(f"pageerror: {e}"))
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        state, actual, expected, exec_error = "passed", "Assertions passed", case.get("expected", ""), ""
        evidence: list[str] = []
        try:
            for step in case.get("steps", []):
                op = step.get("action")
                if op == "goto":
                    url = self.base_url + step.get("path", "/")
                    lines.append(f"goto {url}")
                    page.goto(url, wait_until="domcontentloaded", timeout=8000)
                elif op == "fill":
                    value = self.secret(step["secret"]) if step.get("secret") else str(step.get("value", ""))
                    lines.append(f"fill {step['selector']} = {value}")   # redacted before upload (F05)
                    page.locator(step["selector"]).fill(value)
                elif op == "click":
                    lines.append(f"click {step['selector']}")
                    page.locator(step["selector"]).click()
                elif op == "assert_text":
                    text = page.locator(step["selector"]).inner_text()
                    expected = expected or f"{step['selector']} contains {step['contains']!r}"
                    lines.append(f"assert_text {step['selector']} contains {step['contains']!r}: got {text!r}")
                    if step["contains"] not in text:
                        raise AssertionError(f"Expected {step['contains']!r} in {step['selector']}, got {text!r}")
                else:
                    raise ValueError(f"Unsupported web step: {op}")
        except AssertionError as exc:
            state, actual = "failed", str(exc)[:500]
        except LookupError as exc:
            state, actual = "blocked", str(exc)
        except Exception as exc:
            detail = str(exc)[:500]
            if any(code in detail for code in UNREACHABLE):
                state, actual = "blocked", "Environment unreachable during navigation"
            else:
                # a step that cannot run (timeout, missing element, bad selector) is our engine/test problem
                state, actual, exec_error = "error", "Execution error (engine)", detail
            lines.append(f"{type(exc).__name__}: {detail}")
        finally:
            trace = self.safe_name(case["id"], attempt, "_trace.zip")
            try:
                context.tracing.stop(path=str(trace))
                evidence.append(trace.name)
            except Exception:
                pass
            if state in ("failed", "error"):
                shot = self.safe_name(case["id"], attempt, ".png")
                try:
                    page.screenshot(path=str(shot), full_page=True)
                    evidence.append(shot.name)
                except Exception:
                    pass
            context.close()
            lines.append(f"state {state}")
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            evidence.insert(0, log_path.name)

        return self.result(case, state, expected=expected, actual=actual, execution_error=exec_error,
                           duration_ms=round((perf_counter() - t0) * 1000), started_at=started_at,
                           finished_at=now_iso(), evidence=evidence)

    def cleanup(self):
        for closer in (getattr(self._browser, "close", None), getattr(self._pw, "stop", None)):
            try:
                if closer:
                    closer()
            except Exception:
                pass
        self._browser = self._pw = None
