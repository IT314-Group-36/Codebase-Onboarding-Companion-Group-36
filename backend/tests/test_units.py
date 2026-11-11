import os

import pytest

from ai_pipeline.chunker import chunk_file
from ai_pipeline.graph import build_graphs, impact, rank_files
from ai_pipeline.parser import parse_file
from ai_pipeline.pipeline import analyze_checkout
from ai_pipeline.repo import clone_repo, is_sensitive, scan_files, validate_branch, validate_repo_url
from ai_pipeline.secrets import REDACTED, redact_secrets

PY = '''import os.path as p
from .core import cfg as c, thing
from . import util

@decorator
class Svc(Base):
    def run(self, x):
        self.helper(x)
        return thing(x) + util.go()

    def helper(self, y):
        return c(y)

def top():
    def inner():
        return 1
    return inner()
'''


def test_python_symbols_imports_calls():
    pf = parse_file("pkg/svc.py", PY)
    uids = {s.uid: s for s in pf.symbols}
    assert set(uids) == {"pkg/svc.py::Svc", "pkg/svc.py::Svc.run", "pkg/svc.py::Svc.helper",
                         "pkg/svc.py::top", "pkg/svc.py::top.inner"}
    assert uids["pkg/svc.py::Svc"].start_line == 5            # decorator line included
    assert uids["pkg/svc.py::Svc.run"].kind == "method"
    assert ("helper", "self") in uids["pkg/svc.py::Svc.run"].calls and ("go", "util") in uids["pkg/svc.py::Svc.run"].calls
    assert {".core", ".", ".util", "os.path"} <= set(pf.imports)


def test_js_ts_symbols_and_imports():
    js = ("import {f as g} from './b';\nconst dep = require('./dep');\nexport * from './re';\n"
          "export const a = async (x) => { g(x); };\nexport class K { m() { this.n(); } n() {} }\n"
          "const App = () => <Foo/>;\n")
    pf = parse_file("src/x.jsx", js)
    assert {s.uid for s in pf.symbols} == {"src/x.jsx::a", "src/x.jsx::K", "src/x.jsx::K.m", "src/x.jsx::K.n", "src/x.jsx::App"}
    assert pf.imports == ["./b", "./dep", "./re"]
    assert pf.bindings["g"] == ("./b", "f")
    ts = parse_file("a.ts", "export default function f(a: number): void { g(a) }\n")
    assert ts.symbols[0].name == "f" and ("g", None) in ts.symbols[0].calls
    assert parse_file("a.go", "package main") is None


def _sample_graph():
    files = {
        "pkg/__init__.py": "", "pkg/core.py": "def cfg(x):\n    return x\n\ndef thing(y):\n    return cfg(y)\n",
        "pkg/util.py": "def go():\n    return 1\n",
        "pkg/svc.py": "from .core import cfg as c, thing\nfrom . import util\n\nclass Svc:\n    def run(self, x):\n        self.helper(x)\n        return thing(x) + util.go()\n    def helper(self, y):\n        return c(y)\n",
        "web/a.js": "import {f} from './b';\nexport function a(){ return f(); }\n", "web/b.js": "export function f(){ return 1; }\n"}
    parsed = {p: parse_file(p, t) for p, t in files.items() if p.endswith((".py", ".js"))}
    return files, parsed, *build_graphs(parsed, list(files))


def test_graph_edges_and_impact():
    files, parsed, fg, sg = _sample_graph()
    assert ("pkg/svc.py", "pkg/core.py") in fg.edges and ("web/a.js", "web/b.js") in fg.edges
    assert ("pkg/svc.py::Svc.helper", "pkg/core.py::cfg") in sg.edges      # alias import: cfg as c
    assert ("pkg/svc.py::Svc.run", "pkg/svc.py::Svc.helper") in sg.edges   # self.helper()
    assert ("pkg/svc.py::Svc.run", "pkg/util.py::go") in sg.edges          # module alias util.go()
    r = impact(sg, fg, ["pkg/core.py::cfg"], [], depth=3)
    d = {s["uid"]: s["distance"] for s in r["affected_symbols"]}
    assert d == {"pkg/core.py::thing": 1, "pkg/svc.py::Svc.helper": 1, "pkg/svc.py::Svc.run": 2}
    assert impact(sg, fg, ["pkg/core.py::cfg"], [], depth=1)["affected_symbols"][-1]["distance"] == 1
    fr = impact(sg, fg, [], ["pkg/core.py"], depth=2)
    assert [f["path"] for f in fr["affected_files"]] == ["pkg/svc.py"]


def test_chunks_cover_symbols_and_have_exact_lines():
    files, parsed, *_ = _sample_graph()
    text = files["pkg/svc.py"]
    chunks = chunk_file("pkg/svc.py", text, parsed["pkg/svc.py"])
    lines = text.split("\n")
    for c in chunks:
        assert c.page_content == "\n".join(lines[c.metadata["start_line"] - 1:c.metadata["end_line"]])
    labels = {c.metadata["label"] for c in chunks}
    assert {"Svc.run", "Svc.helper", "module-level"} <= labels
    big = "def huge():\n" + "\n".join(f"    x{i} = {i} * 2  # filler filler filler" for i in range(300)) + "\n"
    parts = chunk_file("big.py", big, parse_file("big.py", big))
    assert len(parts) > 1 and all(len(c.page_content) <= 1900 for c in parts)
    plain = chunk_file("notes.md", "line\n" * 200, None)
    assert plain and all(c.metadata["symbol_uid"] is None for c in plain)


def test_secret_redaction_keeps_line_numbers_and_ignores_placeholders():
    text = ('KEY = "AKIAABCDEFGHIJKLMNOP"\nGOOD = "your_api_key_here_please"\n'
            'token = "n8Qx2LmZp0aVb7RtYc3Kd9"\n-----BEGIN RSA PRIVATE KEY-----\nabc\ndef\n-----END RSA PRIVATE KEY-----\nlast = 1\n')
    out, n = redact_secrets(text)
    assert n == 3 and "AKIA" not in out and "n8Qx2" not in out and "abc" not in out
    assert "your_api_key_here_please" in out
    assert out.count("\n") == text.count("\n") and out.split("\n")[-2] == "last = 1"
    assert REDACTED in out


def test_url_and_branch_validation():
    assert validate_repo_url("https://github.com/tiangolo/fastapi.git/") == "https://github.com/tiangolo/fastapi"
    for bad in ["file:///etc/passwd", "--upload-pack=x", "ssh://git@github.com/a/b", "https://evil.com/a/b",
                "https://github.com/a/b/tree/main", "/tmp"]:
        with pytest.raises(ValueError):
            validate_repo_url(bad)
    assert validate_branch("feature/x-1") == "feature/x-1" and validate_branch("") == ""
    for bad in ["--exec=x", "a..b", "-x", "a b"]:
        with pytest.raises(ValueError):
            validate_branch(bad)


def test_scan_skips_symlinks_and_flags_sensitive(tmp_path):
    (tmp_path / "a.py").write_text("x=1")
    (tmp_path / ".env").write_text("S=1")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "m.js").write_text("1")
    os.symlink("/etc/passwd", tmp_path / "link.txt")
    all_files, safe = scan_files(tmp_path)
    assert all_files == [".env", "a.py"] and safe == ["a.py"] and is_sensitive(".env")


def test_clone_local_returns_sha_and_failure_is_readable(git_repo, tmp_path):
    sha = clone_repo(str(git_repo), "", tmp_path / "c1")
    assert len(sha) == 40 and (tmp_path / "c1" / "README.md").exists()
    with pytest.raises(RuntimeError, match="Could not clone"):
        clone_repo(str(tmp_path / "nope"), "", tmp_path / "c2")
    with pytest.raises(RuntimeError, match="Could not clone"):
        clone_repo(str(git_repo), "no-such-branch", tmp_path / "c3")


def test_analysis_budget_keeps_important_files_not_random(git_repo):
    a = analyze_checkout(git_repo, max_chunks=100)
    assert a.report["secrets_redacted"] == 1 and a.report["sensitive_files"] == 1
    assert all("AKIA" not in c.page_content and "supersecret" not in c.page_content for c in a.chunks)
    assert a.report["import_edges"] >= 3 and a.report["call_edges"] >= 3
    small = analyze_checkout(git_repo, max_chunks=3)
    kept = {c.metadata["file_path"] for c in small.chunks}
    assert "README.md" in kept and small.report["files_dropped_by_budget"] > 0
    scores = rank_files(list(a.parsed) + ["README.md", "tests/test_x.py"], a.file_graph)
    assert scores["shop/db.py"] > scores["tests/test_x.py"]
