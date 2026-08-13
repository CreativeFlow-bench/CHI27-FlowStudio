"""Shared pytest configuration (FlowStudio backend)."""

from __future__ import annotations

import os


def pytest_configure() -> None:
    # Tests swap benchmark manifests between cases; the discovery cache would
    # return stale listings across tests. Disable it for the test run.
    os.environ.setdefault("FLOWSTUDIO_DISABLE_BENCHMARK_CACHE", "1")
