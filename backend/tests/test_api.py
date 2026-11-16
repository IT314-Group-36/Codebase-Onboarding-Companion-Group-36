"""End-to-end: real Postgres + pgvector via the Alembic migration, real git clone of a local repo,
real tree-sitter/NetworkX, hash embedder, fake LLM, FastAPI app through httpx."""
import json
import re
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.runnables import RunnableLambda
from sqlalchemy import func, select

from ai_pipeline.module_map import EntryPoint, ModuleInfo, ModuleMap
from ai_pipeline.summary import RepoSummary
from app.api import deps
from app.db.session import SessionLocal
from app.main import app
from app.models import Chunk, ConversationMessage, Edge, Repository, Symbol
from app.services.indexing import run_indexing
from app.services.qa import Answer, Citation, ImpactExplanation
from app.services.retrieval import PgHybridRetriever
from app.services.runtime import get_embedder
from tests.conftest import FakeGitHub, FakeQueue


class FakeLLM:
    """Stands in for a LangChain chat model: only `with_structured_output` is needed by our chains."""

    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(lambda prompt_value: self._respond(schema, prompt_value.to_string()))

    def _respond(self, schema, prompt):
        self.calls.append(schema.__name__)
        if self.fail:
            raise RuntimeError("rate limited")
        if schema is ModuleMap:
            return ModuleMap(project_summary="A shop.", entry_points=[
                EntryPoint(path="shop/api.py", reason="checkout"), EntryPoint(path="invented.py", reason="x")],
                modules=[ModuleInfo(name="Shop", path="shop", purpose="Orders and payments",
                                    key_files=["shop/payments.py", "shop/ghost.py"]),
                         ModuleInfo(name="Web", path="web", purpose="UI", key_files=["web/app.js"]),
                         ModuleInfo(name="Ghost", path="ghost", purpose="invented", key_files=[])])
        if schema is RepoSummary:
            return RepoSummary(title="Shop", one_line="demo", description="d", architecture="a", tech_highlights=["Python"],
                               key_files=["README.md", "nope.md"], how_to_run="n/a")
        if schema is Answer:
            first = re.search(r"\[1\] (\S+) lines (\d+)-(\d+)", prompt)
            return Answer(answer="Payments are in shop/payments.py", citations=[
                Citation(path=first.group(1), start_line=int(first.group(2)), end_line=int(first.group(3))),
                Citation(path=first.group(1), start_line=1, end_line=99999),
                Citation(path="invented.py", start_line=1, end_line=2)])
        if schema is ImpactExplanation:
            return ImpactExplanation(explanation="Callers may break.", suggested_checks=["run checkout tests"])
        raise AssertionError(schema)
class FakeStreamingLLM:
    async def astream(self, messages):
        yield SimpleNamespace(content="Payments are handled ")
        yield SimpleNamespace(content="in shop/payments.py.")


@pytest.fixture
async def client(db, make_user):
    """An API client signed in as a test user (the routes require a session cookie)."""
    app.state.queue = FakeQueue()
    app.dependency_overrides[deps.get_llm_dep] = lambda: FakeLLM()
    user, headers = await make_user()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=headers) as c:
        c.user = user
        yield c
    app.dependency_overrides.clear()


async def index(client, git_repo, llm="fake", branch=""):
    r = await client.post("/repos", json={"url": str(git_repo), "branch": branch})
    assert r.status_code == 202, r.text
    rid = r.json()["id"]
    await run_indexing(rid, None, llm=FakeLLM() if llm == "fake" else llm, embedder=get_embedder())
    return rid


async def test_register_validates_and_enqueues(client, git_repo):
    assert (await client.post("/repos", json={"url": "file:///etc/passwd"})).status_code == 422
    assert (await client.post("/repos", json={"url": "https://github.com/a/b", "branch": "--x"})).status_code == 422
    r = await client.post("/repos", json={"url": "https://github.com/tiangolo/fastapi.git", "access_token": "tok"})
    assert r.status_code == 202 and r.json()["status"] == "queued" and "tok" not in r.text
    assert app.state.queue.jobs == [("index_repository", (r.json()["id"], "tok"))]
    again = await client.post("/repos", json={"url": "https://github.com/tiangolo/fastapi"})
    assert again.json()["id"] == r.json()["id"] and len(app.state.queue.jobs) == 1      # idempotent
    assert (await client.get(f"/repos/{r.json()['id']}/map")).status_code == 409          # not ready yet
    assert (await client.get("/repos/999")).status_code == 404


async def test_full_index_and_read_endpoints(client, git_repo):
    rid = await index(client, git_repo)
    d = (await client.get(f"/repos/{rid}")).json()
    assert d["status"] == "ready" and d["stage"] is None and len(d["commit_sha"]) == 40
    assert d["index_report"]["secrets_redacted"] == 1 and d["index_report"]["sensitive_files"] == 1
    assert d["summary"]["key_files"] == ["README.md"]                                   # invented path dropped
    assert any("nope.md" in w for w in d["warnings"])

    m = (await client.get(f"/repos/{rid}/map")).json()
    assert [x["name"] for x in m["modules"]] == ["Shop", "Web"]                         # invented module dropped
    assert m["modules"][0]["key_files"] == ["shop/payments.py"] and [e["path"] for e in m["entry_points"]] == ["shop/api.py"]
    assert {n["id"] for n in m["graph"]["nodes"]} == {"shop", "web"}
    assert m["graph"]["edges"] == []                                                    # no cross-module imports in the demo

    files = (await client.get(f"/repos/{rid}/files")).json()
    assert {f["path"]: f["sensitive"] for f in files}[".env"] is True
    fd = (await client.get(f"/repos/{rid}/files/shop/payments.py")).json()
    assert [s["qualname"] for s in fd["symbols"]] == ["charge_card", "refund_payment"]
    assert fd["imports"] == ["shop/db.py"] and fd["imported_by"] == ["shop/api.py"]

    syms = (await client.get(f"/repos/{rid}/symbols", params={"q": "charge"})).json()
    assert [s["uid"] for s in syms] == ["shop/payments.py::charge_card"]


async def test_search_finds_payment_code_and_never_leaks_secrets(client, git_repo):
    rid = await index(client, git_repo)
    hits = (await client.post(f"/repos/{rid}/search", json={"query": "where is the payment logic handled?"})).json()["hits"]
    assert hits and hits[0]["file_path"] == "shop/payments.py"
    async with SessionLocal() as s:
        leaked = (await s.execute(select(func.count()).select_from(Chunk).where(
            Chunk.content.contains("AKIA") | Chunk.content.contains("supersecret")))).scalar_one()
    assert leaked == 0


async def test_ask_validates_citations(client, git_repo):
    rid = await index(client, git_repo)
    r = (await client.post(f"/repos/{rid}/ask", json={"question": "where is the payment logic handled?"})).json()
    assert r["answer"].startswith("Payments")
    assert [c["path"] for c in r["citations"]] == [r["sources"][0]["file_path"]]        # invented citation removed
    app.dependency_overrides[deps.get_llm_dep] = lambda: None
    assert (await client.post(f"/repos/{rid}/ask", json={"question": "anything?"})).status_code == 503


async def test_impact_symbol_file_and_ambiguity(client, git_repo):
    rid = await index(client, git_repo)
    r = (await client.get(f"/repos/{rid}/impact", params={"symbol": "save_order", "explain": True})).json()
    got = {s["qualname"]: s["distance"] for s in r["affected_symbols"]}
    assert got == {"charge_card": 1, "refund_payment": 1, "checkout": 2}
    assert r["explanation"].startswith("Callers") and "Static analysis" in r["caveat"]
    shallow = (await client.get(f"/repos/{rid}/impact", params={"symbol": "shop/db.py::save_order", "depth": 1})).json()
    assert {s["qualname"] for s in shallow["affected_symbols"]} == {"charge_card", "refund_payment"}
    f = (await client.get(f"/repos/{rid}/impact", params={"file": "shop/db.py"})).json()
    assert {x["path"] for x in f["affected_files"]} == {"shop/payments.py", "shop/api.py"}
    amb = await client.get(f"/repos/{rid}/impact", params={"symbol": "c"})
    assert amb.status_code == 409 and amb.json()["detail"]["candidates"]
    assert (await client.get(f"/repos/{rid}/impact")).status_code == 422
    assert (await client.get(f"/repos/{rid}/impact", params={"symbol": "zzzz"})).status_code == 404


async def test_reindex_replaces_data_without_duplicates(client, git_repo):
    rid = await index(client, git_repo)

    async def counts():
        async with SessionLocal() as s:
            return [(await s.execute(select(func.count()).select_from(m).where(m.repo_id == rid))).scalar_one() for m in (Chunk, Symbol, Edge)]
    first = await counts()
    assert (await client.post(f"/repos/{rid}/reindex")).status_code == 202
    assert app.state.queue.jobs[-1][0] == "index_repository"
    await run_indexing(rid, None, llm=FakeLLM(), embedder=get_embedder())
    assert await counts() == first
    async with SessionLocal() as s:
        repo = await s.get(Repository, rid)
        repo.status = "indexing"
        await s.commit()
    assert (await client.post(f"/repos/{rid}/reindex")).status_code == 409


async def test_llm_failure_degrades_to_deterministic_map(client, git_repo):
    rid = await index(client, git_repo, llm=FakeLLM(fail=True))
    d = (await client.get(f"/repos/{rid}")).json()
    assert d["status"] == "ready" and d["summary"] is None and len(d["warnings"]) == 2
    m = (await client.get(f"/repos/{rid}/map")).json()
    assert {x["path"] for x in m["modules"]} == {"shop", "web"} and "Description unavailable" in m["modules"][0]["purpose"]
    rid2 = await index(client, git_repo, llm=None, branch="main")                      # no API key at all
    d2 = (await client.get(f"/repos/{rid2}")).json()
    assert d2["status"] == "ready" and "LLM_API_KEY" in d2["warnings"][0]


async def test_failed_clone_marks_repo_failed_and_cleans_up(client, git_repo):
    rid = await index(client, git_repo, branch="no-such-branch")
    d = (await client.get(f"/repos/{rid}")).json()
    assert d["status"] == "failed" and "Could not clone" in d["error"]
    import os
    assert not any(n.startswith(f"job_{rid}_") for n in os.listdir("/tmp/onboarding_test_work"))


async def test_retriever_returns_langchain_documents_from_pgvector(client, git_repo):
    from langchain_core.documents import Document
    rid = await index(client, git_repo)
    docs = await PgHybridRetriever(repo_id=rid, embeddings=get_embedder(), k=3).ainvoke("where is the payment logic handled?")
    assert docs and all(isinstance(d, Document) for d in docs) and len(docs) <= 3
    assert docs[0].metadata["file_path"] == "shop/payments.py" and "charge_card" in docs[0].page_content
    assert set(docs[0].metadata) == {"file_path", "symbol_uid", "start_line", "end_line", "score"}
    assert await PgHybridRetriever(repo_id=rid + 99, embeddings=get_embedder()).ainvoke("payment") == []   # other repos' data never leaks


async def test_llm_failure_on_ask_and_impact_is_a_clear_502(client, git_repo):
    rid = await index(client, git_repo)
    app.dependency_overrides[deps.get_llm_dep] = lambda: FakeLLM(fail=True)
    r = await client.post(f"/repos/{rid}/ask", json={"question": "where is the payment logic handled?"})
    assert r.status_code == 502 and "LLM call failed" in r.json()["detail"]
    r = await client.get(f"/repos/{rid}/impact", params={"symbol": "shop/db.py::save_order", "explain": True})
    assert r.status_code == 502
    plain = await client.get(f"/repos/{rid}/impact", params={"symbol": "shop/db.py::save_order"})
    assert plain.status_code == 200                                       # impact without explanation never needs the LLM


async def test_source_is_fetched_from_the_indexed_commit_with_secrets_redacted_and_sensitive_files_blocked(client, git_repo):
    from app.api import deps
    from app.core.security import encrypt_token
    from app.db.session import SessionLocal
    rid = await index(client, git_repo)
    async with SessionLocal() as session:
        repo = await session.get(Repository, rid)
        repo.url = "https://github.com/owner/shop"
        sha = repo.commit_sha
        user = await session.get(type(client.user), client.user.id)
        user.encrypted_access_token = encrypt_token("gho_testtoken")
        await session.commit()

    gh = FakeGitHub()
    gh.branches["owner/shop"] = ["main"]
    app.dependency_overrides[deps.get_github_client] = gh.client
    response = await client.get(f"/repos/{rid}/source/shop/payments.py")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"].startswith("# Sample source")
    assert "[REDACTED_SECRET]" in body["content"] and "sk_live_" not in body["content"]
    assert body["secrets_redacted"] == 1
    assert body["commit_sha"] == sha
    assert any(req.url.params.get("ref") == sha for req in gh.requests if "/contents/" in str(req.url))   # pinned commit

    assert (await client.get(f"/repos/{rid}/source/.env")).status_code == 403              # sensitive: never fetched
    assert (await client.get(f"/repos/{rid}/source/nope.py")).status_code == 404           # not in the index
    assert (await client.get(f"/repos/{rid}/files/shop/payments.py/content")).status_code == 404   # old duplicate route is gone


async def test_conversation_persistence_and_user_isolation(client, git_repo, make_user):
    rid = await index(client, git_repo)

    # Create a conversation.
    created = await client.post(
        f"/repos/{rid}/conversations",
        json={"title": "Checkout questions"},
    )
    assert created.status_code == 201, created.text
    conversation = created.json()
    conversation_id = conversation["id"]

    # Verify it appears in the conversation list.
    listed = await client.get(f"/repos/{rid}/conversations")
    assert listed.status_code == 200
    assert any(item["id"] == conversation_id for item in listed.json())

    # Insert a message to simulate a persisted assistant response.
    async with SessionLocal() as session:
        session.add(
            ConversationMessage(
                conversation_id=conversation_id,
                role="assistant",
                content="Payments are handled in shop/payments.py.",
                status="completed",
                citations=[{"path": "shop/payments.py"}],
            )
        )
        await session.commit()

    # Verify the message can be retrieved.
    messages = await client.get(
        f"/repos/{rid}/conversations/{conversation_id}/messages"
    )
    assert messages.status_code == 200
    assert len(messages.json()) == 1
    assert messages.json()[0]["content"] == (
        "Payments are handled in shop/payments.py."
    )
    assert messages.json()[0]["citations"] == [
        {"path": "shop/payments.py"}
    ]

    # A different user must not access this repository's conversation.
    _, other_headers = await make_user(github_id=2, login="other")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://t",
        headers=other_headers,
    ) as other_client:
        denied = await other_client.get(
            f"/repos/{rid}/conversations/{conversation_id}/messages"
        )
        assert denied.status_code == 404


async def test_streamed_answer_is_persisted(client, git_repo):
    rid = await index(client, git_repo)

    streaming_llm = FakeStreamingLLM()
    app.dependency_overrides[deps.get_llm_dep] = lambda: streaming_llm

    response = await client.post(
        f"/repos/{rid}/ask/stream",
        json={"question": "Where are payments handled?"},
    )

    assert response.status_code == 200

    # Parse the Server-Sent Events.
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]

    conversation_event = next(
        event for event in events if event["type"] == "conversation"
    )

    assert any(event["type"] == "token" for event in events)
    assert any(event["type"] == "done" for event in events)

    conversation_id = conversation_event["conversation_id"]

    # Retrieve persisted messages from the database.
    messages_response = await client.get(
        f"/repos/{rid}/conversations/{conversation_id}/messages"
    )

    assert messages_response.status_code == 200

    messages = messages_response.json()

    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Where are payments handled?"

    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == (
        "Payments are handled in shop/payments.py."
    )
    assert messages[1]["status"] == "completed"


# ---------------------------------------------------------------- source viewer: every error path

async def _github_repo(client, git_repo, *, token="gho_testtoken"):
    """An indexed repo that claims to live on GitHub, owned by a user with (or without) a saved token."""
    from app.core.security import encrypt_token
    rid = await index(client, git_repo)
    async with SessionLocal() as session:
        repo = await session.get(Repository, rid)
        repo.url = "https://github.com/owner/shop"
        user = await session.get(type(client.user), client.user.id)
        user.encrypted_access_token = encrypt_token(token) if token else None
        await session.commit()
    gh = FakeGitHub()
    gh.branches["owner/shop"] = ["main"]
    app.dependency_overrides[deps.get_github_client] = gh.client
    return rid, gh


async def test_source_viewer_rejects_what_it_cannot_serve(client, git_repo):
    rid = await index(client, git_repo)                        # a local path, not a GitHub URL
    local = await client.get(f"/repos/{rid}/source/shop/payments.py")
    assert local.status_code == 422 and "GitHub" in local.json()["detail"]

    rid, _ = await _github_repo(client, git_repo)
    async with SessionLocal() as session:
        await session.execute(Repository.__table__.update().where(Repository.id == rid).values(commit_sha=None))
        await session.commit()
    assert (await client.get(f"/repos/{rid}/source/shop/payments.py")).status_code == 409      # nothing to pin to

    async with SessionLocal() as session:
        from app.models import File
        await session.execute(File.__table__.update().where(File.repo_id == rid, File.path == "shop/payments.py")
                              .values(size=900_000))
        await session.commit()
    big = await client.get(f"/repos/{rid}/source/shop/payments.py")
    assert big.status_code == 413


async def test_source_viewer_reports_github_problems_with_the_shared_error_codes(client, git_repo):
    rid, gh = await _github_repo(client, git_repo)
    gh.valid_token = "gho_someone_else"                         # GitHub now rejects the saved token (revoked)
    revoked = await client.get(f"/repos/{rid}/source/shop/payments.py")
    assert revoked.status_code == 403 and revoked.json()["detail"]["code"] == "github_reauth_required"

    gh.valid_token = "gho_testtoken"
    gh.force_status = 404
    assert (await client.get(f"/repos/{rid}/source/shop/payments.py")).status_code == 404
    gh.force_status = 429
    assert (await client.get(f"/repos/{rid}/source/shop/payments.py")).status_code == 429


async def test_source_viewer_needs_a_saved_github_token(client, git_repo):
    rid, _ = await _github_repo(client, git_repo, token=None)
    response = await client.get(f"/repos/{rid}/source/shop/payments.py")
    assert response.status_code == 403 and response.json()["detail"]["code"] == "github_reauth_required"


async def test_source_viewer_is_private_to_the_repository_owner(client, git_repo, make_user):
    rid, _ = await _github_repo(client, git_repo)
    _, other = await make_user(github_id=2, login="other", token="gho_testtoken")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=other) as c:
        assert (await c.get(f"/repos/{rid}/source/shop/payments.py")).status_code == 404


# ---------------------------------------------------------------- Q&A conversations

class RecordingLLM:
    """Streams a fixed answer and remembers the messages it was sent."""
    def __init__(self, answer="Payments are handled in shop/payments.py."):
        self.answer, self.sent = answer, []

    async def astream(self, messages):
        self.sent.append(list(messages))
        yield SimpleNamespace(content=self.answer)


class BrokenLLM:
    """Writes part of an answer, then fails."""
    async def astream(self, messages):
        yield SimpleNamespace(content="Payments are ")
        raise RuntimeError("model overloaded")


class NeverEndingLLM:
    async def astream(self, messages):
        while True:
            yield SimpleNamespace(content="more ")


def _sse(response):
    return [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")]


async def _ask(client, rid, question, conversation_id=None):
    body = {"question": question}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    return await client.post(f"/repos/{rid}/ask/stream", json=body)


async def _messages(client, rid, conversation_id):
    return (await client.get(f"/repos/{rid}/conversations/{conversation_id}/messages")).json()


async def test_empty_conversations_are_reused_instead_of_piling_up(client, git_repo):
    rid = await index(client, git_repo)
    first = (await client.post(f"/repos/{rid}/conversations", json={})).json()
    again = (await client.post(f"/repos/{rid}/conversations", json={"title": "   "})).json()
    assert again["id"] == first["id"] and first["title"] == "New conversation"       # still empty: same one

    named = (await client.post(f"/repos/{rid}/conversations", json={"title": "Payments"})).json()
    assert named["id"] == first["id"] and named["title"] == "Payments"                # an empty one can be renamed

    app.dependency_overrides[deps.get_llm_dep] = lambda: RecordingLLM()
    await _ask(client, rid, "Where are payments handled?", first["id"])
    fresh = (await client.post(f"/repos/{rid}/conversations", json={})).json()
    assert fresh["id"] != first["id"]                                                  # the first one has messages now
    assert len((await client.get(f"/repos/{rid}/conversations")).json()) == 2


async def test_conversation_title_must_be_valid(client, git_repo):
    rid = await index(client, git_repo)
    assert (await client.post(f"/repos/{rid}/conversations", json={"title": ""})).status_code == 422
    assert (await client.post(f"/repos/{rid}/conversations", json={"title": "x" * 201})).status_code == 422


async def test_first_question_titles_the_conversation_and_activity_orders_the_list(client, git_repo):
    rid = await index(client, git_repo)
    app.dependency_overrides[deps.get_llm_dep] = lambda: RecordingLLM()
    first = (await client.post(f"/repos/{rid}/conversations", json={})).json()
    await _ask(client, rid, "Where are payments handled?", first["id"])
    second = (await client.post(f"/repos/{rid}/conversations", json={})).json()
    await _ask(client, rid, "What does checkout do?", second["id"])

    listed = (await client.get(f"/repos/{rid}/conversations")).json()
    assert [c["id"] for c in listed] == [second["id"], first["id"]]                   # most recently active first
    assert {c["title"] for c in listed} == {"Where are payments handled?", "What does checkout do?"}

    await _ask(client, rid, "And refunds?", first["id"])                               # new activity in the older one
    listed = (await client.get(f"/repos/{rid}/conversations")).json()
    assert listed[0]["id"] == first["id"]
    assert listed[0]["title"] == "Where are payments handled?"                         # the title is not overwritten


async def test_follow_up_sends_earlier_turns_but_never_failed_or_empty_ones(client, git_repo):
    rid = await index(client, git_repo)
    llm = RecordingLLM()
    app.dependency_overrides[deps.get_llm_dep] = lambda: llm
    conversation = (await client.post(f"/repos/{rid}/conversations", json={})).json()["id"]
    await _ask(client, rid, "Where are payments handled?", conversation)

    async with SessionLocal() as session:                      # an interrupted turn and a failed one, saved earlier
        session.add_all([
            ConversationMessage(conversation_id=conversation, role="user", content="INTERRUPTED QUESTION", status="completed"),
            ConversationMessage(conversation_id=conversation, role="assistant", content="", status="pending"),
            ConversationMessage(conversation_id=conversation, role="user", content="FAILED QUESTION", status="completed"),
            ConversationMessage(conversation_id=conversation, role="assistant", content="partial text", status="failed"),
        ])
        await session.commit()

    await _ask(client, rid, "And refunds?", conversation)
    sent = llm.sent[-1]
    texts = [m.content for m in sent]
    assert any("Where are payments handled?" in t for t in texts)                      # the good turn is remembered
    assert any("Payments are handled in shop/payments.py." == t for t in texts)
    assert not any("INTERRUPTED" in t or "FAILED QUESTION" in t or t == "partial text" for t in texts)
    assert all(t.strip() for t in texts)                                                # no empty message reaches the model


async def test_a_failing_model_leaves_a_failed_message_with_the_partial_answer(client, git_repo):
    rid = await index(client, git_repo)
    app.dependency_overrides[deps.get_llm_dep] = lambda: BrokenLLM()
    events = _sse(await _ask(client, rid, "Where are payments handled?"))
    assert events[-1]["type"] == "error" and "model overloaded" in events[-1]["message"]
    conversation = next(e for e in events if e["type"] == "conversation")["conversation_id"]
    saved = await _messages(client, rid, conversation)
    assert [m["role"] for m in saved] == ["user", "assistant"]
    assert saved[1]["status"] == "failed" and saved[1]["content"] == "Payments are "


async def test_missing_llm_is_saved_as_a_failed_answer(client, git_repo):
    rid = await index(client, git_repo)
    app.dependency_overrides[deps.get_llm_dep] = lambda: None
    events = _sse(await _ask(client, rid, "Where are payments handled?"))
    assert events[-1]["type"] == "error" and "LLM is not configured" in events[-1]["message"]
    conversation = next(e for e in events if e["type"] == "conversation")["conversation_id"]
    assert (await _messages(client, rid, conversation))[1]["status"] == "failed"


async def test_a_closed_connection_does_not_leave_the_answer_pending(client, git_repo):
    from app.api.repos import ask_stream
    from app.schemas import AskStreamIn
    rid = await index(client, git_repo)
    async with SessionLocal() as session:
        repo = await session.get(Repository, rid)
        response = await ask_stream(AskStreamIn(question="Where are payments handled?"), repo, session,
                                    get_embedder(), NeverEndingLLM())
        stream = response.body_iterator
        started = json.loads((await stream.__anext__()).removeprefix("data: "))
        await stream.__anext__()                                # sources
        await stream.__anext__()                                # the first token
        await stream.aclose()                                   # the browser tab was closed here
    saved = await _messages(client, rid, started["conversation_id"])
    assert saved[1]["status"] == "failed" and saved[1]["content"].startswith("more")


async def test_conversations_cannot_be_used_across_repositories_or_users(client, git_repo, make_user):
    rid = await index(client, git_repo)
    app.dependency_overrides[deps.get_llm_dep] = lambda: RecordingLLM()
    assert (await _ask(client, rid, "Where are payments handled?", 999_999)).status_code == 404

    conversation = (await client.post(f"/repos/{rid}/conversations", json={})).json()["id"]
    _, other = await make_user(github_id=2, login="other")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=other) as c:
        assert (await c.get(f"/repos/{rid}/conversations")).status_code == 404            # not their repository
        assert (await c.post(f"/repos/{rid}/ask/stream",
                             json={"question": "hi", "conversation_id": conversation})).status_code == 404


async def test_conversations_are_deleted_with_their_repository(client, git_repo):
    rid = await index(client, git_repo)
    app.dependency_overrides[deps.get_llm_dep] = lambda: RecordingLLM()
    events = _sse(await _ask(client, rid, "Where are payments handled?"))
    conversation = next(e for e in events if e["type"] == "conversation")["conversation_id"]
    assert (await client.delete(f"/repos/{rid}")).status_code == 204
    from app.models import Conversation
    async with SessionLocal() as session:
        assert await session.get(Conversation, conversation) is None
        assert (await session.scalar(select(func.count()).select_from(ConversationMessage))) == 0
