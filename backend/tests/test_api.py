"""End-to-end: real Postgres + pgvector via the Alembic migration, real git clone of a local repo,
real tree-sitter/NetworkX, hash embedder, fake LLM, FastAPI app through httpx."""
import re

import httpx
import pytest
from sqlalchemy import func, select

from langchain_core.runnables import RunnableLambda

from ai_pipeline.module_map import EntryPoint, ModuleInfo, ModuleMap
from ai_pipeline.summary import RepoSummary
from app.api import deps
from app.db.session import SessionLocal
from app.main import app
from app.models import Chunk, Edge, Repository, Symbol
from app.services.indexing import run_indexing
from app.services.qa import Answer, Citation, ImpactExplanation
from app.services.retrieval import PgHybridRetriever
from app.services.runtime import get_embedder
from tests.conftest import FakeQueue


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
                Citation(path="invented.py", start_line=1, end_line=2)])
        if schema is ImpactExplanation:
            return ImpactExplanation(explanation="Callers may break.", suggested_checks=["run checkout tests"])
        raise AssertionError(schema)


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
