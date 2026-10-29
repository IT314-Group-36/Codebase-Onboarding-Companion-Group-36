"""Offline tests (no Gemini, no embedding model needed). Run: pytest -q"""
import json
from pathlib import Path

from ai_pipeline import chunk_text, detect_tech_stack, validate_paths
from ai_pipeline.module_map import EntryPoint, ModuleInfo, ModuleMap
from ai_pipeline.repo import is_sensitive, scan_files


def make_repo(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "1", "express": "1"}}))
    (tmp_path / "requirements.txt").write_text("flask==3.0\nrequests\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("\n".join(f"def f{i}():\n    return {i}\n" for i in range(200)))
    (tmp_path / ".env").write_text("SECRET=1")
    return tmp_path


def test_stack_detection(tmp_path):
    root = make_repo(tmp_path)
    all_files, _ = scan_files(root)
    s = detect_tech_stack(root, all_files)
    assert {"React", "Express", "Flask"} <= set(s["frameworks"])
    assert {"npm", "pip"} <= set(s["package_managers"])


def test_sensitive_files_never_in_safe_list(tmp_path):
    root = make_repo(tmp_path)
    all_files, safe = scan_files(root)
    assert ".env" in all_files and ".env" not in safe
    assert is_sensitive("id_rsa") and is_sensitive("prod.tfvars")


def test_chunk_line_numbers_are_correct(tmp_path):
    text = "\n".join(f"def f{i}():\n    return {i}\n" for i in range(200))
    docs = chunk_text(text, "src/app.py")
    lines = text.split("\n")
    assert len(docs) > 1
    for d in docs:
        s, e = d.metadata["start_line"], d.metadata["end_line"]
        assert 1 <= s <= e <= len(lines)
        assert d.page_content.split("\n")[0].strip() == lines[s - 1].strip()


def test_invented_paths_are_removed():
    mm = ModuleMap(project_summary="x",
                   modules=[ModuleInfo(name="Real", path="src", purpose="p", key_files=["src/app.py", "src/ghost.py"]),
                            ModuleInfo(name="Fake", path="nope", purpose="p", key_files=[])],
                   entry_points=[EntryPoint(path="src/app.py", reason="r"), EntryPoint(path="main.py", reason="r")])
    clean, warnings = validate_paths(mm, ["src/app.py", "README.md"])
    assert [m.name for m in clean.modules] == ["Real"]
    assert clean.modules[0].key_files == ["src/app.py"]
    assert [e.path for e in clean.entry_points] == ["src/app.py"]
    assert len(warnings) == 3


def test_file_tree_saved(tmp_path):
    from ai_pipeline.repo import save_file_tree
    root = make_repo(tmp_path / "r") if (tmp_path / "r").mkdir() is None else None
    all_files, safe = scan_files(root)
    out = tmp_path / "out"; out.mkdir()
    info = save_file_tree(root, all_files, safe, out)
    data = json.loads((out / "file_tree.json").read_text())
    assert info["folders"] == 1 and "src" in data["folders"]
    assert [f["sensitive"] for f in data["files"] if f["path"] == ".env"] == [True]


def test_index_search_and_summary_context(tmp_path):
    from langchain_core.embeddings import DeterministicFakeEmbedding
    from ai_pipeline import index_repo, open_store
    from ai_pipeline.summary import _PROMPT, gather_context
    root = tmp_path / "r"; root.mkdir(); make_repo(root)
    _, safe = scan_files(root)
    emb = DeterministicFakeEmbedding(size=32)
    rep = index_repo(root, safe, "demo", persist_dir=str(tmp_path / "vs"), embeddings=emb)
    assert rep["chunks_stored"] > 0 and ".env" not in str(rep)
    store = open_store(str(tmp_path / "vs"), "demo", embeddings=emb)   # re-open from disk
    hits = store.similarity_search("def f1", k=2)
    assert hits and {"source", "start_line", "end_line"} <= set(hits[0].metadata)
    assert all(h.metadata["source"] != ".env" for h in store.similarity_search("SECRET", k=10))
    ctx = gather_context(store)
    assert "src/app.py" in ctx
    _PROMPT.invoke({"tech_stack": "{}", "readme": "r", "tree": "t", "context": ctx})
