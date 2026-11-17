"""Replaceable test engines. Each case names its adapter; each adapter is one file here."""
from .api_pytest import ApiPytestAdapter
from .base import RunContext, TestAdapter
from .web_playwright import WebPlaywrightAdapter

ADAPTERS: dict[str, type[TestAdapter]] = {
    WebPlaywrightAdapter.name: WebPlaywrightAdapter,
    ApiPytestAdapter.name: ApiPytestAdapter,
}

__all__ = ["ADAPTERS", "RunContext", "TestAdapter"]
