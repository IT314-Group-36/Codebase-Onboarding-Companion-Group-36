"""Task 3: plain-English file / function explanations.

Unit tests cover the deterministic parts (relationships, sentences, source stitching, module enrichment).
API tests run against real Postgres + the full indexing pipeline with a fake LLM."""
import pytest
from sqlalchemy import func, select, update

from ai_pipeline.pipeline import analyze_checkout
from app.api import deps
from app.db.session import SessionLocal
from app.main import app
from app.models import Explanation, Repository
from app.services.explain import (assemble_source, enrich_modules, file_relationships, file_sentence,
                                  symbol_relationships, symbol_sentence)
from app.services.indexing import run_indexing
from app.services.qa import FileExplanation, SymbolExplanation, SymbolNote
from app.services.runtime import get_embedder
from tests.test_api import FakeLLM, client, index  # noqa: F401  (client is a fixture)


class ExplainLLM(FakeLLM):
    """FakeLLM that also answers the explanation schemas, and remembers prompts so tests can check grounding."""

    def __init__(self, fail=False):
        super().__init__(fail)
        self.prompts = []

    def _respond(self, schema, prompt):
        if schema in (FileExplanation, SymbolExplanation):
            self.calls.append(schema.__name__)
            self.prompts.append(prompt)
            if self.fail:
                raise RuntimeError("rate limited")
            if schema is FileExplanation:
                return FileExplanation(
                    summary="Takes card payments.", explanation="Charges cards and refunds payments.",
                    key_symbols=[SymbolNote(name="charge_card", note="Charges a card."),
                                 SymbolNote(name="charge_card", note="duplicate"),
                                 SymbolNote(name="invented_fn", note="does not exist")],
                    how_it_fits="Saves receipts through db.py; checkout in api.py calls it.")
            return SymbolExplanation(summary="Charges a card.", explanation="Builds a receipt and saves it.",
                                     inputs_outputs="Takes a card number and amount, returns a receipt.",
                                     how_it_fits="Called by checkout, calls save_order.")
        return super()._respond(schema, prompt)


def use_llm(llm):
    app.dependency_overrides[deps.get_llm_dep] = lambda: llm
    return llm


async def explain(client, rid, **params):
    return await client.get(f"/repos/{rid}/explain", params=params)


# ----------------------------------------------------------------------------- pure unit tests
@pytest.fixture
def graphs(git_repo):
    a = analyze_checkout(git_repo)
    return a.file_graph, a.symbol_graph


def test_file_relationships_and_sentence(graphs):
    fg, sg = graphs
    rel = file_relationships("shop/payments.py", fg, sg)
    assert rel["uses"] == ["shop/db.py"] and rel["used_by"] == ["shop/api.py"]
    assert rel["calls_into"] == [{"path": "shop/db.py", "calls": [{"from": "charge_card", "to": "save_order"},
                                                                  {"from": "refund_payment", "to": "save_order"}]}]
    assert rel["called_from"][0]["path"] == "shop/api.py"
    assert [s["qualname"] for s in rel["symbols"]] == ["charge_card", "refund_payment"]
    assert file_sentence("shop/payments.py", rel) == "`shop/payments.py` uses `shop/db.py`, and is used by `shop/api.py`."


def test_file_sentence_covers_isolated_and_entry_files(graphs):
    fg, sg = graphs
    leaf = file_sentence("shop/db.py", file_relationships("shop/db.py", fg, sg))
    assert leaf.startswith("`shop/db.py` does not import any other file") and "is used by `shop/payments.py`" in leaf
    top = file_sentence("shop/api.py", file_relationships("shop/api.py", fg, sg))
    assert "uses `shop/payments.py`" in top and "is not imported by any other file we could detect" in top
    assert file_relationships("nope.py", fg, sg)["uses"] == []                       # unknown path never crashes


def test_symbol_relationships_and_sentence(graphs):
    _, sg = graphs
    rel = symbol_relationships("shop/payments.py::charge_card", sg)
    assert [c["qualname"] for c in rel["calls"]] == ["save_order"] and [c["qualname"] for c in rel["called_by"]] == ["checkout"]
    assert symbol_sentence("charge_card", rel) == (
        "`charge_card` calls `save_order` (shop/db.py), and is called by `checkout` (shop/api.py).")
    top = symbol_sentence("checkout", symbol_relationships("shop/api.py::checkout", sg))
    assert "is not called by any other function we could detect" in top


def test_sentences_shorten_long_lists():
    import networkx as nx
    fg = nx.DiGraph()
    for i in range(8):
        fg.add_edge(f"user{i}.py", "core.py")
    rel = file_relationships("core.py", fg, nx.DiGraph())
    s = file_sentence("core.py", rel)
    assert "`user0.py`, `user1.py`, `user2.py`, `user3.py`, `user4.py` and 3 more" in s


def test_assemble_source_dedupes_overlap_marks_gaps_and_truncates():
    rows = [(1, 3, "a\nb\nc"), (3, 5, "c\nd\ne"), (9, 10, "i\nj")]          # overlap at line 3, gap 6-8
    assert assemble_source(rows, None, None, 1000).split("\n") == ["a", "b", "c", "d", "e", "...", "i", "j"]
    assert assemble_source(rows, 2, 4, 1000) == "b\nc\nd"                      # restricted to a symbol's line range
    assert assemble_source(rows, None, None, 4).endswith("... (truncated)")
    assert assemble_source([], None, None, 100) == ""


def test_enrich_modules_adds_relationships_without_touching_existing_keys():
    modules = [{"name": "Shop", "path": "shop", "purpose": "Orders", "key_files": ["shop/a.py"]},
               {"name": "Web", "path": "web/", "purpose": "UI", "key_files": []},
               {"name": "Lone", "path": "lone", "purpose": "x", "key_files": []}]
    graph = {"nodes": [{"id": "shop", "label": "Shop"}, {"id": "web", "label": "Web"}, {"id": "lone", "label": "Lone"}],
             "edges": [{"source": "web", "target": "shop", "weight": 3}]}
    shop, web, lone = enrich_modules(modules, graph)
    assert shop["purpose"] == "Orders" and shop["key_files"] == ["shop/a.py"]                  # additive only
    assert shop["used_by"] == [{"path": "web", "name": "Web", "links": 3}] and shop["depends_on"] == []
    assert web["depends_on"][0]["name"] == "Shop"
    assert shop["relationship_summary"] == "The Shop module does not depend on any other module, and is used by Web."
    assert web["relationship_summary"] == "The Web module uses Shop, and is not used by any other module."
    assert "does not depend on any other module, and is not used" in lone["relationship_summary"]


# ----------------------------------------------------------------------------- API tests
async def test_explain_file_is_grounded_validated_and_cached(client, git_repo):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    r = await explain(client, rid, file="shop/payments.py")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "file" and d["source"] == "llm" and d["language"] == "Python"
    assert d["relationship_summary"] == "`shop/payments.py` uses `shop/db.py`, and is used by `shop/api.py`."
    assert d["relationships"]["uses"] == ["shop/db.py"] and d["relationships"]["used_by"] == ["shop/api.py"]
    assert d["module"]["name"] == "Shop"                                                        # module context attached
    ex = d["explanation"]
    assert ex["summary"] and ex["how_it_fits"]
    assert [k["name"] for k in ex["key_symbols"]] == ["charge_card"]                            # invented + duplicate removed
    assert ex["key_symbols"][0]["uid"] == "shop/payments.py::charge_card"
    assert any("dropped 1 unknown symbol" in w for w in d["warnings"]) and "static analysis" in d["caveat"]
    prompt = llm.prompts[0]                                                                     # the LLM saw the facts, not just names
    assert "def charge_card" in prompt and "shop/db.py" in prompt and "Orders and payments" in prompt
    assert "AKIA" not in prompt                                                                 # redaction survived end to end

    again = (await explain(client, rid, file="shop/payments.py")).json()
    assert again["source"] == "cache" and again["explanation"] == ex and len(llm.calls) == 1
    forced = (await explain(client, rid, file="shop/payments.py", refresh="true")).json()
    assert forced["source"] == "llm" and len(llm.calls) == 2


async def test_explain_symbol_by_name_and_uid(client, git_repo):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    d = (await explain(client, rid, symbol="charge_card")).json()
    assert d["kind"] == "symbol" and d["uid"] == "shop/payments.py::charge_card" and d["source"] == "llm"
    assert d["relationship_summary"] == "`charge_card` calls `save_order` (shop/db.py), and is called by `checkout` (shop/api.py)."
    assert d["relationships"]["calls"][0]["uid"] == "shop/db.py::save_order"
    assert d["explanation"]["inputs_outputs"] and d["start_line"] < d["end_line"]
    assert "def charge_card" in llm.prompts[0] and "def refund_payment" not in llm.prompts[0]   # only the symbol's own lines
    by_uid = (await explain(client, rid, symbol="shop/payments.py::charge_card")).json()
    assert by_uid["source"] == "cache"                                                          # name and uid share one cache entry


async def test_explain_errors_are_clear(client, git_repo):
    rid = await index(client, git_repo)
    assert (await explain(client, rid)).status_code == 422
    assert (await explain(client, rid, file="a.py", symbol="b")).status_code == 422
    assert (await explain(client, rid, file="nope.py")).status_code == 404
    assert (await explain(client, rid, symbol="zzzz")).status_code == 404
    amb = await explain(client, rid, symbol="c")
    assert amb.status_code == 409 and amb.json()["detail"]["candidates"]
    assert (await client.get("/repos/999/explain", params={"file": "a"})).status_code == 404
    pending = await client.post("/repos", json={"url": str(git_repo), "branch": "other"})
    assert (await explain(client, pending.json()["id"], file="x")).status_code == 409           # not ready


async def test_without_llm_relationships_still_work_and_cache_is_still_served(client, git_repo):
    rid = await index(client, git_repo)
    use_llm(None)
    d = (await explain(client, rid, file="shop/payments.py")).json()
    assert d["explanation"] is None and d["source"] == "none" and d["relationships"]["uses"] == ["shop/db.py"]
    assert any("LLM_API_KEY" in w for w in d["warnings"]) and d["relationship_summary"]
    use_llm(ExplainLLM())
    await explain(client, rid, symbol="charge_card")
    use_llm(None)                                                                               # key removed later
    assert (await explain(client, rid, symbol="charge_card")).json()["source"] == "cache"


async def test_sensitive_files_are_never_sent_to_the_llm(client, git_repo):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    d = (await explain(client, rid, file=".env")).json()
    assert d["explanation"] is None and any("sensitive" in w for w in d["warnings"]) and llm.calls == []


async def test_llm_failure_is_a_502_and_nothing_is_cached(client, git_repo):
    rid = await index(client, git_repo)
    use_llm(ExplainLLM(fail=True))
    r = await explain(client, rid, file="shop/payments.py")
    assert r.status_code == 502 and "LLM call failed" in r.json()["detail"]
    async with SessionLocal() as s:
        assert (await s.execute(select(func.count()).select_from(Explanation))).scalar_one() == 0
    use_llm(ExplainLLM())
    assert (await explain(client, rid, file="shop/payments.py")).json()["source"] == "llm"       # recovers on retry


async def test_reindex_and_stale_commit_invalidate_the_cache(client, git_repo):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    await explain(client, rid, file="shop/payments.py")
    async with SessionLocal() as s:                                                              # cache row from an older commit
        await s.execute(update(Explanation).values(commit_sha="0" * 40))
        await s.commit()
    assert (await explain(client, rid, file="shop/payments.py")).json()["source"] == "llm"
    assert len(llm.calls) == 2
    await run_indexing(rid, None, llm=FakeLLM(), embedder=get_embedder())                         # reindex drops the cache
    async with SessionLocal() as s:
        assert (await s.execute(select(func.count()).select_from(Explanation))).scalar_one() == 0
        assert (await s.get(Repository, rid)).status == "ready"
    assert (await explain(client, rid, file="shop/payments.py")).json()["source"] == "llm"


async def test_map_modules_carry_relationship_fields(client, git_repo):
    rid = await index(client, git_repo)
    m = (await client.get(f"/repos/{rid}/map")).json()
    shop = m["modules"][0]
    assert shop["name"] == "Shop" and shop["key_files"] == ["shop/payments.py"]                   # Sprint 1 fields unchanged
    assert shop["depends_on"] == [] and shop["used_by"] == []
    assert shop["relationship_summary"] == "The Shop module does not depend on any other module, and is not used by any other module."


async def test_class_method_qualname_resolves_but_shared_method_name_is_ambiguous(client, tmp_path):
    from tests.conftest import make_git_repo
    repo = make_git_repo(tmp_path / "zoo", {
        "zoo.py": "class Cat:\n    def speak(self):\n        return 'meow'\n\nclass Dog:\n    def speak(self):\n        return 'woof'\n"})
    rid = await index(client, repo)
    use_llm(None)
    ok = await explain(client, rid, symbol="Cat.speak")
    assert ok.status_code == 200 and ok.json()["uid"] == "zoo.py::Cat.speak"
    amb = await explain(client, rid, symbol="speak")
    assert amb.status_code == 409 and {c["uid"] for c in amb.json()["detail"]["candidates"]} == {"zoo.py::Cat.speak", "zoo.py::Dog.speak"}
