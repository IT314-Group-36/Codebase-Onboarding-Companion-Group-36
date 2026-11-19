"""Liveness is independent of the DB; readiness is bounded and safe to expose."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app import main


async def get(path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        return await client.get(path)


def connection_engine(monkeypatch, *, error=None):
    execute = AsyncMock()

    @asynccontextmanager
    async def connect():
        if error:
            raise error
        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(main, "engine", SimpleNamespace(connect=connect))
    return execute


@pytest.mark.parametrize("revision", ["a" * 40, "", "secret-not-a-sha", "A" * 40])
async def test_readiness_queries_database_and_only_exposes_valid_revision(monkeypatch, revision):
    execute = connection_engine(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", revision)
    response = await get("/ready")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    expected = {"status": "ready"}
    if revision == "a" * 40:
        expected["revision"] = revision
    assert response.json() == expected
    assert str(execute.call_args.args[0]) == "SELECT 1"


async def test_readiness_with_real_database(db):
    response = await get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


async def test_database_failure_is_sanitized_but_liveness_stays_healthy(monkeypatch):
    connection_engine(monkeypatch, error=RuntimeError("postgres://password@private-host"))
    response = await get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert (await get("/health")).json() == {"status": "ok"}


async def test_pool_checkout_timeout_returns_503(monkeypatch):
    @asynccontextmanager
    async def connect():
        await asyncio.Event().wait()
        yield

    monkeypatch.setattr(main, "engine", SimpleNamespace(connect=connect))
    timeout = asyncio.timeout
    monkeypatch.setattr(main, "asyncio", SimpleNamespace(timeout=lambda _: timeout(0.01)))
    response = await get("/ready")
    assert response.status_code == 503


async def test_readiness_does_not_swallow_request_cancellation(monkeypatch):
    connection_engine(monkeypatch, error=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await get("/ready")
