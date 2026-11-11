"""Task 5: natural-language impact questions in the Ask box.

Unit tests: intent router, mention extraction, report/summary. API tests: real Postgres + indexing pipeline + fake LLM."""
import pytest

from ai_pipeline.graph import impact
from ai_pipeline.pipeline import analyze_checkout
from app.api import deps
from app.main import app
from app.services.impact_qa import (build_report, detect_impact_intent, extract_mentions, file_target, module_target,
                                    symbol_target)
from app.services.qa import ImpactExplanation
from tests.conftest import REPO_FILES, make_git_repo
from tests.test_api import FakeLLM, client, index  # noqa: F401  (client is a fixture)

TEST_FILE = {"tests/test_shop.py": "from shop.payments import charge_card\n\ndef test_charge():\n    assert charge_card('4111', 5)\n"}


class CapturingLLM(FakeLLM):
    """FakeLLM that records the prompts of impact narration."""

    def __init__(self, fail=False):
        super().__init__(fail)
        self.prompts = []

    def _respond(self, schema, prompt):
        if schema is ImpactExplanation:
            self.prompts.append(prompt)
        return super()._respond(schema, prompt)


def use_llm(llm):
    app.dependency_overrides[deps.get_llm_dep] = lambda: llm
    return llm


async def ask(client, rid, question, **extra):
    return await client.post(f"/repos/{rid}/ask", json={"question": question, **extra})


@pytest.fixture
def graphs(tmp_path):
    a = analyze_checkout(make_git_repo(tmp_path / "r", {**REPO_FILES, **TEST_FILE}))
    return a.file_graph, a.symbol_graph


# ----------------------------------------------------------------------------- intent router
IMPACT_QUESTIONS = [
    "What would break if I change charge_card?",
    "what will break if I modify the checkout function",
    "What breaks if I delete shop/db.py?",
    "If I rename save_order, what else needs to change?",
    "What happens if I change `save_order`?",
    "What happens if we remove refund_payment?",
    "Is it safe to remove refund_payment?",
    "Can I safely change charge_card?",
    "Who calls charge_card?",
    "What calls save_order?",
    "Which functions call save_order?",
    "What depends on shop/db.py?",
    "Where is save_order used?",
    "What is affected if I refactor charge_card",
    "What's the blast radius of changing save_order?",
    "What would be impacted by updating the cart module?",
    "What would I break by editing get_cart?",
    "If I change charge_card will the tests fail?",
    "What are the callers of save_order?",
    "What is the impact of deleting web/cart.js?",
    "what files import shop/db.py",
]
NOT_IMPACT_QUESTIONS = [
    "What does this project do?",
    "Where is the payment logic handled?",
    "How does charge_card work?",
    "What does checkout call?",                         # forward dependencies, not impact
    "What does charge_card depend on?",
    "How do I change the database password?",           # a how-to, not an impact question
    "What happens when the payment fails?",
    "Explain the project structure",
    "How do I run the tests?",
    "Which framework does this use?",
]


@pytest.mark.parametrize("q", IMPACT_QUESTIONS)
def test_impact_questions_are_detected(q):
    assert detect_impact_intent(q)[0], q


@pytest.mark.parametrize("q", NOT_IMPACT_QUESTIONS)
def test_other_questions_are_left_to_normal_qa(q):
    assert not detect_impact_intent(q)[0], q


def test_change_flag_distinguishes_vague_change_questions_from_vague_usage_questions():
    assert detect_impact_intent("What would break if I change the payment logic?") == (True, True)
    assert detect_impact_intent("Who uses this?") == (True, False)


# ----------------------------------------------------------------------------- mention extraction
def texts(q):
    return [(m.text, m.is_path) for m in extract_mentions(q)]


def test_mentions_cover_backticks_paths_dotted_names_and_skip_noise():
    assert texts("What would break if I change `charge_card`?") == [("charge_card", False)]
    assert texts("what breaks if I delete shop/db.py?") == [("shop/db.py", True)]                 # trailing '?' trimmed
    assert texts("What depends on cart.js.") == [("cart.js", True)]                                # trailing '.' trimmed
    assert texts("who calls Serializer.dumps?") == [("Serializer.dumps", False)]                  # a method, NOT a file called '.dumps'
    assert extract_mentions("who calls Serializer.dumps?")[0].names == ["Serializer.dumps", "dumps"]
    assert texts("change `Serializer.dumps` now") == [("Serializer.dumps", False)]
    assert texts("change `shop/payments.py::charge_card`") == [("shop/payments.py::charge_card", False)]   # a uid is a symbol
    assert texts("What would happen to the tests if I change everything?") == []                  # only stop words / verbs
    assert texts("Is `utils.py` safe to touch in src/app/")[0:2] == [("utils.py", True), ("src/app/", True)]
    assert [m.text for m in extract_mentions("What if I change charge_card and checkout")] == ["charge_card", "checkout"]


# ----------------------------------------------------------------------------- graph paths + report
def test_impact_with_paths_gives_the_chain_and_default_output_is_unchanged(graphs):
    fg, sg = graphs
    plain = impact(sg, fg, ["shop/db.py::save_order"], [], depth=3)
    assert all("via" not in s for s in plain["affected_symbols"]) and all("via" not in f for f in plain["affected_files"])
    rich = impact(sg, fg, ["shop/db.py::save_order"], [], depth=3, with_paths=True)
    assert [{k: v for k, v in s.items() if k != "via"} for s in rich["affected_symbols"]] == plain["affected_symbols"]
    top = {s["uid"]: s for s in rich["affected_symbols"]}["shop/api.py::checkout"]
    assert top["distance"] == 2 and top["via"] == ["shop/api.py::checkout", "shop/payments.py::charge_card", "shop/db.py::save_order"]
    fr = impact(sg, fg, [], ["shop/db.py"], depth=3, with_paths=True)
    assert {f["path"]: f["via"] for f in fr["affected_files"]}["shop/api.py"] == ["shop/api.py", "shop/payments.py", "shop/db.py"]


def test_report_for_a_function(graphs):
    fg, sg = graphs
    r = build_report(sg, fg, symbol_target(sg, "shop/db.py::save_order"), 3)
    assert r["target"] == "shop/db.py::save_order" and r["totals"] == {"symbols": 4, "files": 3, "tests": 1}
    by = {s["qualname"]: s for s in r["affected_symbols"]}
    assert by["charge_card"]["reason"] == "calls `save_order` directly"
    assert by["checkout"]["chain"] == ["checkout", "charge_card", "save_order"]
    assert by["checkout"]["reason"] == "reaches `save_order` through `charge_card` (2 steps away)"
    assert by["test_charge"]["is_test"] and r["affected_tests"][0]["path"] == "tests/test_shop.py"
    assert r["dependencies"] == {"calls": [], "imports": []}                                       # save_order calls nothing
    assert r["summary"].splitlines()[0] == ("Changing `save_order` (shop/db.py:1) is likely to affect 4 functions and 3 files "
                                            "(following calls and imports up to 3 steps).")
    assert "Directly affected (2):" in r["summary"] and "Tests that reach it: `tests/test_shop.py`." in r["summary"]
    dep = build_report(sg, fg, symbol_target(sg, "shop/payments.py::charge_card"), 3)["dependencies"]
    assert [c["qualname"] for c in dep["calls"]] == ["save_order"]                                 # what it relies on


def test_report_for_a_file_and_a_folder(graphs):
    fg, sg = graphs
    f = build_report(sg, fg, file_target(sg, "shop/db.py"), 3)
    files = {x["path"]: x for x in f["affected_files"]}
    assert files["shop/payments.py"]["reason"] == "imports `shop/db.py` directly"
    assert files["shop/api.py"]["reason"] == "imports `shop/payments.py`, which leads to `shop/db.py` (2 steps away)"
    m = build_report(sg, fg, module_target(fg, sg, "shop/"), 3)                                    # trailing slash tolerated
    assert m["target"] == "shop" and m["target_info"]["files"] == 5
    assert [s["qualname"] for s in m["affected_symbols"]] == ["test_charge"]                      # only code OUTSIDE the folder
    assert m["summary"].startswith("Changing the `shop` folder (5 files)")


def test_report_when_nothing_depends_on_the_target(graphs):
    fg, sg = graphs
    r = build_report(sg, fg, symbol_target(sg, "shop/api.py::checkout"), 3)
    assert r["totals"]["symbols"] == 0 and "Nothing else in this repository calls it" in r["summary"]
    assert "entry point" in r["summary"] and r["dependencies"]["calls"][0]["qualname"] == "charge_card"
    assert "For context, it relies on: `charge_card` (shop/payments.py)." in r["summary"]


def test_long_lists_are_shortened_in_text_but_complete_in_json():
    import networkx as nx
    sg, fg = nx.DiGraph(), nx.DiGraph()
    sg.add_node("core.py::f", path="core.py", name="f", qualname="f", kind="function", start_line=1, end_line=2)
    for i in range(12):
        uid = f"u{i}.py::g{i}"
        sg.add_node(uid, path=f"u{i}.py", name=f"g{i}", qualname=f"g{i}", kind="function", start_line=1, end_line=2)
        sg.add_edge(uid, "core.py::f")
    r = build_report(sg, fg, symbol_target(sg, "core.py::f"), 3)
    assert r["totals"]["symbols"] == 12 and len(r["affected_symbols"]) == 12
    assert "... and 4 more (see the full list in the response)" in r["summary"]


# ----------------------------------------------------------------------------- /ask end to end
async def test_ask_answers_what_would_break_from_the_graph(client, git_repo):
    rid = await index(client, git_repo)
    llm = use_llm(CapturingLLM())
    r = await ask(client, rid, "What would break if I change save_order?")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["intent"] == "impact" and d["needs_clarification"] is False and d["candidates"] == []
    assert d["impact"]["target"] == "shop/db.py::save_order" and d["impact"]["target_info"]["file_path"] == "shop/db.py"
    assert {s["qualname"]: s["distance"] for s in d["impact"]["affected_symbols"]} == {"charge_card": 1, "refund_payment": 1, "checkout": 2}
    assert {f["path"] for f in d["impact"]["affected_files"]} == {"shop/payments.py", "shop/api.py"}
    assert d["answer"].startswith("Callers may break.") and "Suggested checks" in d["answer"]    # LLM narration of the same facts
    assert "Static analysis" in d["caveat"] and d["warnings"] == []
    assert d["citations"][0] == {"path": "shop/db.py", "start_line": 1, "end_line": 2}             # target first, then direct callers
    assert {c["path"] for c in d["citations"][1:]} == {"shop/payments.py"} and d["sources"] == []
    p = llm.prompts[0]                                                                              # the LLM was given facts, not asked to guess
    assert "What would break if I change save_order?" in p and "`checkout`" in p and "`charge_card`" in p and "directly" in p


async def test_ask_without_llm_still_answers_impact_questions_but_not_general_ones(client, git_repo):
    rid = await index(client, git_repo)
    use_llm(None)
    r = await ask(client, rid, "Who calls save_order?")
    assert r.status_code == 200
    d = r.json()
    assert d["impact"]["totals"]["symbols"] == 3 and "`charge_card`" in d["answer"] and d["answer"] == d["impact"]["summary"]
    assert any("LLM_API_KEY" in w for w in d["warnings"])
    assert (await ask(client, rid, "What does this project do?")).status_code == 503              # Sprint 1 behaviour preserved


async def test_llm_failure_on_an_impact_question_degrades_instead_of_failing(client, git_repo):
    rid = await index(client, git_repo)
    use_llm(FakeLLM(fail=True))
    d = (await ask(client, rid, "What would break if I change save_order?")).json()
    assert d["answer"] == d["impact"]["summary"] and any("LLM explanation is unavailable" in w for w in d["warnings"])
    r = await ask(client, rid, "where is the payment logic handled?")                              # normal questions: still a clear 502
    assert r.status_code == 502


async def test_ask_resolves_files_folders_methods_and_case_insensitive_names(tmp_path, client):
    repo = make_git_repo(tmp_path / "zoo", {
        "core/base.py": "class Animal:\n    def speak(self):\n        return '?'\n",
        "core/cat.py": "from .base import Animal\n\nclass Cat(Animal):\n    def speak(self):\n        return 'meow'\n",
        "app/main.py": "from core.base import Animal\n\ndef run(a):\n    return a.speak()\n\ndef go():\n    return Animal().speak()\n",
        "web/app.js": "import { getCart } from './cart';\nexport function render() { return getCart(); }\n",
        "web/cart.js": "export function getCart() { return []; }\n"})
    rid = await index(client, repo)
    use_llm(None)
    f = (await ask(client, rid, "What would break if I delete core/base.py?")).json()
    assert f["impact"]["target_info"]["kind"] == "file" and "app/main.py" in {x["path"] for x in f["impact"]["affected_files"]}
    js = (await ask(client, rid, "what depends on cart.js")).json()                                  # unique file name, no directory
    assert js["impact"]["target"] == "web/cart.js" and [s["qualname"] for s in js["impact"]["affected_symbols"]] == ["render"]
    folder = (await ask(client, rid, "What would break if I change the core/ folder?")).json()
    assert folder["impact"]["target_info"] == {"kind": "module", "path": "core", "name": "core", "files": 2}
    assert {s["qualname"] for s in folder["impact"]["affected_symbols"]} == {"run", "go"}
    amb = (await ask(client, rid, "What would break if I change speak?")).json()                   # two methods are called speak
    assert amb["needs_clarification"] is True and amb["impact"] is None
    assert {c["uid"] for c in amb["candidates"]} == {"core/base.py::Animal.speak", "core/cat.py::Cat.speak"}
    one = (await ask(client, rid, "What would break if I change Animal.speak?")).json()
    assert one["impact"]["target"] == "core/base.py::Animal.speak"
    low = (await ask(client, rid, "who calls animal.speak")).json()
    assert low["impact"]["target"] == "core/base.py::Animal.speak"                                  # case-insensitive
    narrowed = (await ask(client, rid, "what breaks if I change speak in core/cat.py")).json()      # the file narrows the ambiguity
    assert narrowed["impact"]["target"] == "core/cat.py::Cat.speak"


async def test_vague_change_question_asks_which_one_and_the_followup_works(client, git_repo):
    rid = await index(client, git_repo)
    use_llm(None)
    d = (await ask(client, rid, "What would break if I change the payment logic?")).json()
    assert d["intent"] == "impact" and d["needs_clarification"] is True and d["impact"] is None
    uids = [c["uid"] for c in d["candidates"]]
    assert "shop/payments.py::charge_card" in uids and "Which one do you mean?" in d["answer"]
    followup = (await ask(client, rid, "What would break if I change the payment logic?", symbol="shop/payments.py::charge_card")).json()
    assert followup["needs_clarification"] is False and followup["impact"]["target"] == "shop/payments.py::charge_card"
    assert [s["qualname"] for s in followup["impact"]["affected_symbols"]] == ["checkout"]


async def test_hints_depth_and_errors(client, git_repo):
    rid = await index(client, git_repo)
    use_llm(None)
    q = "What would break if I change this function?"
    d = (await ask(client, rid, q, symbol="shop/db.py::save_order")).json()                         # UI passes the selected symbol
    assert d["impact"]["target"] == "shop/db.py::save_order" and d["impact"]["depth"] == 3
    shallow = (await ask(client, rid, q, symbol="save_order", depth=1)).json()
    assert {s["qualname"] for s in shallow["impact"]["affected_symbols"]} == {"charge_card", "refund_payment"}
    direct = (await ask(client, rid, "What would break directly if I change save_order?")).json()
    assert direct["impact"]["depth"] == 1
    fh = (await ask(client, rid, "what breaks if I change this file?", file="shop/db.py")).json()
    assert fh["impact"]["target_info"]["kind"] == "file"
    assert (await ask(client, rid, q, symbol="no_such_thing")).status_code == 404
    assert (await ask(client, rid, q, file="nope.py")).status_code == 404
    assert (await ask(client, rid, q, depth=9)).status_code == 422
    cand = (await ask(client, rid, q, symbol="c")).json()                                            # hint matches several symbols
    assert cand["needs_clarification"] is True and len(cand["candidates"]) >= 2
    other = (await ask(client, rid, "What does this project do?", symbol="save_order"))              # hints only matter for impact questions
    assert other.status_code == 503


async def test_other_mentions_are_reported_and_normal_questions_are_unchanged(client, git_repo):
    rid = await index(client, git_repo)
    use_llm(FakeLLM())
    d = (await ask(client, rid, "What breaks if I change charge_card, and would checkout still work?")).json()
    assert d["impact"]["target"] == "shop/payments.py::charge_card"
    assert any("checkout" in w for w in d["warnings"])
    n = (await ask(client, rid, "where is the payment logic handled?")).json()                       # Sprint 1 contract + the new intent key
    assert n["intent"] == "question" and n["answer"].startswith("Payments") and n["citations"] and n["sources"]
    vague = (await ask(client, rid, "Who uses this project?")).json()                               # usage wording, nothing named: plain Q&A
    assert vague["intent"] == "question"


async def test_impact_endpoint_keeps_old_fields_and_adds_the_new_ones(client, git_repo):
    rid = await index(client, git_repo)
    use_llm(FakeLLM())
    r = (await client.get(f"/repos/{rid}/impact", params={"symbol": "save_order", "explain": True})).json()
    for key in ("target", "depth", "affected_symbols", "affected_files", "caveat", "explanation"):      # Sprint 1 keys
        assert key in r
    assert r["target"] == "shop/db.py::save_order" and r["explanation"].startswith("Callers")
    assert {"summary", "affected_tests", "dependencies", "totals", "target_info"} <= set(r)
    assert r["affected_symbols"][-1]["chain"] == ["checkout", "charge_card", "save_order"] and "reason" in r["affected_symbols"][0]
    assert (await client.get(f"/repos/{rid}/impact", params={"symbol": "Class.nope"})).status_code == 404
    f = (await client.get(f"/repos/{rid}/impact", params={"file": "shop/db.py"})).json()
    assert f["target"] == "shop/db.py" and {x["path"] for x in f["affected_files"]} == {"shop/payments.py", "shop/api.py"}


# ----------------------------------------------------------------------------- regressions found on a real repository (pallets/itsdangerous)
SERIALIZER_REPO = {
    "src/ser/serializer.py": "class Serializer:\n    def dumps(self, obj):\n        return str(obj)\n",
    "src/ser/app.py": "from .serializer import Serializer\n\ndef save(obj):\n    return Serializer().dumps(obj)\n",
    "tests/test_serializer.py": "import pytest\n\nclass TestSerializer:\n    @pytest.fixture\n    def serializer(self):\n        return 1\n\n"
                                "    def test_a(self, serializer):\n        return serializer\n",
}


async def test_a_lowercase_word_never_silently_wins_over_the_class_it_probably_means(tmp_path, client):
    """'the serializer' exactly matched a pytest fixture called `serializer`, so the answer was about the fixture and the
    real `Serializer` class never competed. Now the user is asked, with production code listed first."""
    rid = await index(client, make_git_repo(tmp_path / "ser", SERIALIZER_REPO))
    use_llm(None)
    d = (await ask(client, rid, "What would break if I change the serializer?")).json()
    assert d["needs_clarification"] is True and d["impact"] is None
    assert [c["uid"] for c in d["candidates"]] == ["src/ser/serializer.py::Serializer", "tests/test_serializer.py::TestSerializer.serializer"]
    cap = (await ask(client, rid, "What would break if I change Serializer?")).json()               # deliberate capital: the class
    assert cap["impact"]["target"] == "src/ser/serializer.py::Serializer"
    tick = (await ask(client, rid, "What would break if I change `serializer`?")).json()            # explicit identifier: exact name wins
    assert tick["impact"]["target"] == "tests/test_serializer.py::TestSerializer.serializer"
    picked = (await ask(client, rid, "What would break if I change the serializer?", symbol=d["candidates"][0]["uid"])).json()
    assert picked["impact"]["target"] == "src/ser/serializer.py::Serializer"                         # the follow-up the UI sends


def test_summary_lists_production_callers_and_only_counts_test_functions(tmp_path):
    files = {"core.py": "def core():\n    return 1\n", "app.py": "from core import core\n\ndef run():\n    return core()\n",
             "tests/test_core.py": "from core import core\n\n" + "".join(f"def test_{i}():\n    assert core()\n\n" for i in range(10))}
    a = analyze_checkout(make_git_repo(tmp_path / "r", files))
    r = build_report(a.symbol_graph, a.file_graph, symbol_target(a.symbol_graph, "core.py::core"), 3)
    assert r["totals"]["symbols"] == 11                                                              # JSON keeps every test function
    assert "Directly affected (1, plus 10 test functions):" in r["summary"] and "`run` (app.py:3) calls `core` directly" in r["summary"]
    assert "test_3" not in r["summary"] and "Tests that reach it: `tests/test_core.py`." in r["summary"]
    assert sum(s["is_test"] for s in r["affected_symbols"]) == 10


def test_only_tests_depend_on_it():
    import networkx as nx
    sg, fg = nx.DiGraph(), nx.DiGraph()
    for uid, path in (("a.py::f", "a.py"), ("tests/test_a.py::test_f", "tests/test_a.py")):
        sg.add_node(uid, path=path, name=uid.split("::")[1], qualname=uid.split("::")[1], kind="function", start_line=1, end_line=2)
    sg.add_edge("tests/test_a.py::test_f", "a.py::f")
    fg.add_edge("tests/test_a.py", "a.py")
    r = build_report(sg, fg, symbol_target(sg, "a.py::f"), 3)
    assert "Directly affected: only 1 test function." in r["summary"] and "Tests that reach it: `tests/test_a.py`." in r["summary"]


def test_call_chains_are_deterministic_when_two_routes_are_equally_short():
    import networkx as nx
    def make(order):
        g = nx.DiGraph()
        for n in "atbc":
            g.add_node(n, path=n, name=n, qualname=n, kind="function", start_line=1, end_line=1)
        for edge in order:
            g.add_edge(*edge)
        return g
    routes = [("a", "b"), ("b", "t"), ("a", "c"), ("c", "t")]
    chains = {tuple(next(s for s in impact(make(o), nx.DiGraph(), ["t"], [], 3, with_paths=True)["affected_symbols"] if s["uid"] == "a")["via"])
              for o in (routes, routes[::-1], routes[1:] + routes[:1])}
    assert chains == {("a", "b", "t")}                                                               # alphabetical tie-break, same every run


def test_hostile_questions_are_cheap():
    import time
    start = time.perf_counter()
    for q in ("what " * 200, "a/" * 480, "if I change " + "x." * 300, "who " + "calls " * 160, "/" * 900, "if i " + "change and " * 80):
        detect_impact_intent(q[:1000])
        extract_mentions(q[:1000])
    assert time.perf_counter() - start < 1.0
