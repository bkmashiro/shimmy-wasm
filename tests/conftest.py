"""Shared test configuration and fixtures."""

import shutil
import pytest

requires_wasmtime = pytest.mark.skipif(
    not shutil.which("wasmtime"),
    reason="wasmtime not installed"
)

requires_wasi_sdk = pytest.mark.skipif(
    not shutil.which("clang") or not shutil.which("wasmtime"),
    reason="WASI SDK (clang) or wasmtime not installed"
)


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests that need wasmtime when it's not installed."""
    if shutil.which("wasmtime"):
        return
    skip = pytest.mark.skip(reason="wasmtime not installed")
    for item in items:
        item.add_marker(skip)
