"""Operator script regressions; these never contact a deployed service."""
import io
import json
from types import SimpleNamespace

import pytest

from scripts import verify_deployment as verifier

SHA = "a" * 40


class Response(io.BytesIO):
    status = 200


@pytest.mark.parametrize("url", [
    "http://example.com", "https://user:password@example.com", "https://example.com/path",
    "https://example.com?secret=x", "https://example.com#fragment",
])
def test_invalid_origins_rejected_before_network_access(url):
    with pytest.raises(ValueError):
        verifier.verify(url, SHA)


def test_short_revision_rejected():
    with pytest.raises(ValueError):
        verifier.verify("https://example.com", "abc123")


def test_matching_revision_is_accepted(monkeypatch):
    def open_request(request, timeout):
        assert request.full_url == "https://example.com/ready"
        assert timeout <= 10
        return Response(json.dumps({"status": "ready", "revision": SHA}).encode())
    monkeypatch.setattr(verifier.urllib.request, "urlopen", open_request)
    verifier.verify("https://example.com/", SHA)


@pytest.mark.parametrize("body", [
    {"status": "ready", "revision": "b" * 40}, {"status": "ready"}, {"status": "unavailable"},
    [], "not-json",
])
def test_old_revision_or_invalid_response_never_passes(monkeypatch, body):
    clock = iter([0, 0, 0, 2, 2])
    monkeypatch.setattr(verifier, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    encoded = body.encode() if isinstance(body, str) else json.dumps(body).encode()
    monkeypatch.setattr(verifier.urllib.request, "urlopen", lambda *a, **kw: Response(encoded))
    with pytest.raises(TimeoutError, match="expected revision"):
        verifier.verify("https://example.com", SHA, timeout=1)


def test_cold_start_network_failure_is_retried(monkeypatch):
    clock = iter([0, 0, 1, 1, 2, 2])
    sleeps = []
    monkeypatch.setattr(verifier, "time", SimpleNamespace(
        monotonic=lambda: next(clock), sleep=sleeps.append,
    ))
    calls = []

    def open_request(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise OSError("private connection details")
        return Response(json.dumps({"status": "ready", "revision": SHA}).encode())

    monkeypatch.setattr(verifier.urllib.request, "urlopen", open_request)
    verifier.verify("https://example.com", SHA, timeout=30)
    assert len(calls) == 2 and sleeps == [10]
