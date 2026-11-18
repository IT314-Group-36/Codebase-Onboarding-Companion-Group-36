"""Conversation and shared storage reservations, including races and legacy data."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api import deps
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import Conversation, ConversationMessage, Repository
from app.services.conversations import bounded_citations, bounded_text
from app.services.indexing import run_indexing
from app.services.jobs import recover_interrupted_jobs
from app.services.storage import (
    CONVERSATION_BYTES,
    PROGRESS_BYTES,
    check_storage_budget,
    lock_storage,
    storage_usage_bytes,
)
from tests.conftest import api_client
from tests.test_api import RecordingLLM, _ask, _messages, _sse, client, index  # noqa: F401
from tests.test_onboarding_progress import add_issue, put


def use_stream(llm=None):
    llm = llm or RecordingLLM()
    app.dependency_overrides[deps.get_llm_dep] = lambda: llm
    return llm


async def counts():
    async with SessionLocal() as session:
        return (
            await session.scalar(select(func.count()).select_from(Conversation)),
            await session.scalar(select(func.count()).select_from(ConversationMessage)),
        )


async def usage():
    async with SessionLocal() as session:
        return await storage_usage_bytes(session)


def conversation_id(response):
    assert response.status_code == 200, response.text
    return next(event["conversation_id"] for event in _sse(response) if event["type"] == "conversation")


def test_utf8_and_citation_bounds(monkeypatch):
    assert bounded_text("😀" * 20, 7) == "😀"
    monkeypatch.setattr(get_settings(), "max_message_citations_bytes", 120)
    citations = [{"path": f"file-{i}.py", "start_line": 1, "end_line": 2} for i in range(50)]
    result = bounded_citations(citations)
    assert result and len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= 120
    assert bounded_citations([{"path": "x", "start_line": -1, "end_line": 2}]) == []
    assert bounded_citations([{"path": "legacy.py"}]) == [{"path": "legacy.py"}]


@pytest.mark.parametrize("setting,status", [
    ("max_conversations_per_repo", 403), ("max_conversations_per_user", 403), ("max_total_conversations", 503),
])
async def test_create_and_stream_cannot_bypass_conversation_caps(client, git_repo, monkeypatch, setting, status):
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), setting, 1)
    first = (await client.post(f"/repos/{rid}/conversations", json={})).json()["id"]
    reused = (await client.post(f"/repos/{rid}/conversations", json={})).json()["id"]
    assert first == reused
    llm = use_stream()
    conversation_id(await _ask(client, rid, "Where are payments handled?", first))
    assert (await client.post(f"/repos/{rid}/conversations", json={})).status_code == status
    assert (await _ask(client, rid, "Where are payments handled?")).status_code == status
    assert await counts() == (1, 2) and len(llm.sent) == 1


@pytest.mark.parametrize("setting,status", [
    ("max_messages_per_conversation", 403), ("max_messages_per_user", 403), ("max_total_messages", 503),
])
async def test_turn_reserves_two_message_rows_before_model_call(client, git_repo, monkeypatch, setting, status):
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), setting, 2)
    llm = use_stream()
    cid = conversation_id(await _ask(client, rid, "Where are payments handled?"))
    response = await _ask(client, rid, "And refunds?", cid)
    assert response.status_code == status
    assert await counts() == (1, 2) and len(llm.sent) == 1


async def test_concurrent_turns_cannot_overshoot_global_message_cap(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "max_total_messages", 2)
    llm = use_stream()
    results = await asyncio.gather(_ask(client, rid, "Where are payments handled?"),
                                   _ask(client, rid, "Where are refunds handled?"))
    assert sorted(response.status_code for response in results) == [200, 503]
    assert await counts() == (1, 2) and len(llm.sent) == 1


async def test_concurrent_empty_creates_reuse_one_chat(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "max_conversations_per_repo", 1)
    results = await asyncio.gather(*(client.post(f"/repos/{rid}/conversations", json={}) for _ in range(3)))
    assert all(response.status_code == 201 for response in results)
    assert len({response.json()["id"] for response in results}) == 1
    assert await counts() == (1, 0)


async def test_progress_and_chat_share_one_atomic_planning_budget(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    await add_issue(rid, 1)
    budget = await usage() + CONVERSATION_BYTES
    monkeypatch.setattr(get_settings(), "storage_budget_bytes", budget)
    progress, chat = await asyncio.gather(put(client, rid, "issue-1", "completed"),
                                         client.post(f"/repos/{rid}/conversations", json={}))
    assert sorted([progress.status_code, chat.status_code]) in ([200, 503], [201, 503])
    assert await usage() <= budget


async def test_full_shared_budget_blocks_new_rows_but_not_reads_or_progress_reset(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    await add_issue(rid, 1)
    monkeypatch.setattr(get_settings(), "storage_budget_bytes", await usage() + PROGRESS_BYTES)
    assert (await put(client, rid, "issue-1", "completed")).status_code == 200
    llm = use_stream()
    assert (await _ask(client, rid, "Where are payments handled?")).status_code == 503
    assert await counts() == (0, 0) and not llm.sent
    assert (await client.get(f"/repos/{rid}/files")).status_code == 200
    assert (await put(client, rid, "issue-1", "pending")).status_code == 200
    assert (await put(client, rid, "issue-1", "completed")).status_code == 200


async def test_deleting_chat_frees_counts_and_budget_and_preserves_other_users(client, git_repo, monkeypatch, make_user):
    rid = await index(client, git_repo)
    use_stream()
    cid = conversation_id(await _ask(client, rid, "Where are payments handled?"))
    monkeypatch.setattr(get_settings(), "max_total_messages", 2)
    monkeypatch.setattr(get_settings(), "storage_budget_bytes", await usage())
    assert (await _ask(client, rid, "Another question?")).status_code == 503
    _, headers = await make_user(github_id=2, login="other")
    async with api_client(headers) as other:
        assert (await other.delete(f"/repos/{rid}/conversations/{cid}")).status_code == 404
    assert (await client.delete(f"/repos/{rid}/conversations/{cid}")).status_code == 204
    assert await counts() == (0, 0)
    assert (await client.get(f"/repos/{rid}/conversations/{cid}/messages")).status_code == 404
    conversation_id(await _ask(client, rid, "Where are payments handled?"))
    assert await counts() == (1, 2)


async def test_pending_reservation_counts_and_is_recoverable_after_restart(client, git_repo):
    rid = await index(client, git_repo)
    cid = (await client.post(f"/repos/{rid}/conversations", json={})).json()["id"]
    before = await usage()
    async with SessionLocal() as session:
        session.add(ConversationMessage(conversation_id=cid, role="assistant", content="", status="pending"))
        await session.commit()
    assert await usage() > before
    assert (await client.delete(f"/repos/{rid}/conversations/{cid}")).status_code == 409
    await recover_interrupted_jobs()
    assert (await _messages(client, rid, cid))[0]["status"] == "failed"
    assert (await client.delete(f"/repos/{rid}/conversations/{cid}")).status_code == 204


async def test_unicode_output_is_bounded_and_marked_failed_not_silently_completed(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "max_message_content_bytes", 64)
    use_stream(RecordingLLM(answer="😀" * 1000))
    response = await _ask(client, rid, "Where are payments handled?")
    cid = conversation_id(response)
    events = _sse(response)
    assert events[-1]["type"] == "error" and "byte limit" in events[-1]["message"]
    assert not any(event["type"] == "done" for event in events)
    answer = (await _messages(client, rid, cid))[1]
    assert answer["status"] == "failed" and len(answer["content"].encode("utf-8")) == 64


async def test_oversized_question_allocates_nothing(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "max_message_content_bytes", 8)
    llm = use_stream()
    assert (await _ask(client, rid, "😀😀😀")).status_code == 413
    assert await counts() == (0, 0) and not llm.sent


async def test_stream_timeout_keeps_bounded_failed_answer(client, git_repo, monkeypatch):
    class SlowModel:
        async def astream(self, messages):
            yield SimpleNamespace(content="Partial answer.")
            await asyncio.sleep(10)
    rid = await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "conversation_stream_timeout_seconds", 1)
    use_stream(SlowModel())
    response = await _ask(client, rid, "Where are payments handled?")
    cid = conversation_id(response)
    assert "timed out" in _sse(response)[-1]["message"]
    assert (await _messages(client, rid, cid))[1]["status"] == "failed"


async def test_legacy_reads_are_paginated_bounded_and_not_silently_deleted(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    cid = (await client.post(f"/repos/{rid}/conversations", json={})).json()["id"]
    async with SessionLocal() as session:
        for i in range(5):
            session.add(ConversationMessage(conversation_id=cid, role="assistant", status="completed",
                                            content=f"{i}:" + "😀" * 1000,
                                            citations=[{"path": "x" * 10000, "start_line": 1, "end_line": 2}]))
        await session.commit()
    monkeypatch.setattr(get_settings(), "max_message_content_bytes", 64)
    monkeypatch.setattr(get_settings(), "max_message_citations_bytes", 128)
    response = await client.get(f"/repos/{rid}/conversations/{cid}/messages", params={"limit": 2})
    page = response.json()
    assert [row["content"][:1] for row in page] == ["3", "4"]
    assert all(row["truncated"] and len(row["content"].encode("utf-8")) <= 64 and row["citations"] == [] for row in page)
    older = (await client.get(f"/repos/{rid}/conversations/{cid}/messages", params={"limit": 2, "offset": 2})).json()
    assert [row["content"][:1] for row in older] == ["1", "2"]
    assert (await client.get(f"/repos/{rid}/conversations/{cid}/messages", params={"limit": 201})).status_code == 422
    assert await counts() == (1, 5)
    assert await usage() > 5 * 10000  # Lowering limits must not undercount larger legacy payloads.


async def test_indexing_rechecks_shared_budget_before_embedding(client, git_repo, monkeypatch):
    class NoEmbedding:
        async def aembed_documents(self, texts):
            pytest.fail("Shared storage budget must be checked before embedding")
    rid = await index(client, git_repo)
    use_stream()
    conversation_id(await _ask(client, rid, "Where are payments handled?"))
    monkeypatch.setattr(get_settings(), "storage_budget_bytes", await usage())
    created = await client.post("/repos", json={"url": str(git_repo), "branch": "main"})
    other_id = created.json()["id"]
    await run_indexing(other_id, None, llm=None, embedder=NoEmbedding())
    async with SessionLocal() as session:
        repo = await session.get(Repository, other_id)
        assert repo.status == "failed" and "storage planning budget" in repo.error
    assert await counts() == (1, 2)


async def test_shared_budget_checks_are_enforced_under_database_lock(client, git_repo, monkeypatch):
    await index(client, git_repo)
    monkeypatch.setattr(get_settings(), "storage_budget_bytes", await usage())
    async with SessionLocal() as session:
        await lock_storage(session)
        with pytest.raises(HTTPException) as error:
            await check_storage_budget(session, 1)
        assert error.value.status_code == 503
