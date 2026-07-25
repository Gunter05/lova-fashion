"""
Shared pytest fixtures for Module 1 unit and property tests.
Uses FastAPI TestClient backed by the real app (no DB calls in smoke tests).
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _run_sync(coro):
    """
    Run a coroutine synchronously.

    Creates a new event loop when the current loop is missing or closed.
    This is safe to call from module-scope pytest fixtures and from
    Hypothesis test bodies, where pytest-asyncio may have already
    closed the per-test loop.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop is closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture(scope="module")
def client():
    """Synchronous TestClient for smoke and unit tests."""
    with TestClient(app) as c:
        yield c
