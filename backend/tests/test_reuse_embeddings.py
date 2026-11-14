"""Re-indexing reuses the stored vector of every chunk whose text did not change, and embeds only the rest."""
import subprocess

from sqlalchemy import select, update

from ai_pipeline.embeddings import HashEmbeddings
from app.db.session import SessionLocal
from app.models import Chunk, Repository
from app.services import indexing
from app.services.indexing import _assemble_vectors, _content_hash, _plan_embeddings, run_indexing
from tests.test_api import FakeLLM

KEY = "hash:test-model:384"


# ---------- pure logic ----------
def test_hash_depends_on_both_the_text_and_the_embedder():
    assert _content_hash("def f(): pass", KEY) == _content_hash("def f(): pass", KEY)
    assert _content_hash("def f(): pass", KEY) != _content_hash("def f(): pass ", KEY)
    assert _content_hash("def f(): pass", KEY) != _content_hash("def f(): pass", "fastembed:other-model:384")


def test_plan_skips_cached_texts_and_embeds_duplicates_once():
    texts = ["a", "b", "a", "c", "b", "d"]
    cached = {_content_hash("b", KEY): [2.0]}
    hashes, todo_texts, todo_hashes = _plan_embeddings(texts, cached, KEY)
    assert todo_texts == ["a", "c", "d"]                               # "b" is cached, "a" appears twice but is embedded once
    assert todo_hashes == [_content_hash(t, KEY) for t in todo_texts]
    assert hashes == [_content_hash(t, KEY) for t in texts]


def test_assemble_puts_every_vector_back_in_chunk_order():
    texts = ["a", "b", "a", "c", "b", "d"]
    cached = {_content_hash("b", KEY): [2.0]}
    hashes, todo_texts, todo_hashes = _plan_embeddings(texts, cached, KEY)
    fresh = {h: [float(ord(t))] for h, t in zip(todo_hashes, todo_texts, strict=True)}
    out = _assemble_vectors(hashes, cached, fresh)
    assert out == [[97.0], [2.0], [97.0], [99.0], [2.0], [100.0]]


# ---------- end to end, real Postgres ----------
class CountingEmbedder(HashEmbeddings):
    """A deterministic embedder that records every text it is asked to embed."""

    def __init__(self, dim=384):
        super().__init__(dim)
        self.seen: list[str] = []

    def iter_embed_documents(self, texts):
        for t in texts:
            self.seen.append(t)
            yield self._vec(t)


async def _new_repo(make_user, git_repo) -> int:
    user, _ = await make_user(token="gho_x")
    async with SessionLocal() as s:
        r = Repository(owner_id=user.id, url=str(git_repo), branch="", status="queued")
        s.add(r)
        await s.commit()
        return r.id


async def _index(rid) -> CountingEmbedder:
    emb = CountingEmbedder()
    await run_indexing(rid, None, llm=FakeLLM(), embedder=emb)
    return emb


async def _repo(rid) -> Repository:
    async with SessionLocal() as s:
        return await s.get(Repository, rid)


async def _vectors_by_location(rid) -> dict:
    async with SessionLocal() as s:
        rows = (await s.execute(select(Chunk.file_path, Chunk.start_line, Chunk.embedding, Chunk.content_hash)
                                .where(Chunk.repo_id == rid))).all()
    return {(f, line): ([float(x) for x in v], h) for f, line, v, h in rows}


def _commit(root, rel, new_text):
    (root / rel).write_text(new_text)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": __import__("os").environ["PATH"]}
    for cmd in (["git", "add", "-A"], ["git", "commit", "-q", "-m", "change"]):
        subprocess.run(cmd, cwd=root, check=True, env=env, capture_output=True)


async def test_first_index_embeds_everything_and_stores_hashes(db, make_user, git_repo):
    rid = await _new_repo(make_user, git_repo)
    emb = await _index(rid)
    repo = await _repo(rid)
    chunks = await _vectors_by_location(rid)
    assert repo.status == "ready" and chunks
    assert all(h for _, h in chunks.values())                          # every chunk has a hash
    assert repo.index_report["reused_chunks"] == 0
    assert repo.index_report["embedded_chunks"] == len(set(emb.seen)) <= len(chunks)


async def test_reindexing_an_unchanged_repo_embeds_nothing_and_keeps_identical_vectors(db, make_user, git_repo):
    rid = await _new_repo(make_user, git_repo)
    await _index(rid)
    before = await _vectors_by_location(rid)
    second = await _index(rid)
    after = await _vectors_by_location(rid)
    repo = await _repo(rid)
    assert second.seen == []                                           # nothing went to the embedder
    assert repo.status == "ready"
    assert repo.index_report["embedded_chunks"] == 0
    assert repo.index_report["reused_chunks"] == len(after)
    assert after == before                                             # same rows, same vectors, same hashes
    assert "timings" in repo.index_report


async def test_changing_one_file_embeds_only_that_files_chunks(db, make_user, git_repo):
    rid = await _new_repo(make_user, git_repo)
    await _index(rid)
    before = await _vectors_by_location(rid)
    _commit(git_repo, "shop/db.py", "def save_order(order):\n    print(order)\n    return order\n")
    third = await _index(rid)
    after = await _vectors_by_location(rid)
    assert third.seen, "the edited file must be re-embedded"
    assert all("shop/db.py" in t for t in third.seen)                  # and nothing else
    unchanged = [k for k in before if k[0] != "shop/db.py" and k in after]
    assert unchanged and all(after[k] == before[k] for k in unchanged)
    repo = await _repo(rid)
    assert repo.index_report["embedded_chunks"] == len(set(third.seen))
    assert repo.index_report["reused_chunks"] > 0


async def test_rows_from_before_the_migration_have_no_hash_and_get_a_full_reembed(db, make_user, git_repo):
    rid = await _new_repo(make_user, git_repo)
    first = await _index(rid)
    async with SessionLocal() as s:
        await s.execute(update(Chunk).where(Chunk.repo_id == rid).values(content_hash=None))
        await s.commit()
    again = await _index(rid)
    assert set(again.seen) == set(first.seen)                          # everything embedded once more
    chunks = await _vectors_by_location(rid)
    assert all(h for _, h in chunks.values())                          # ...and hashes are filled in for next time


async def test_changing_the_embedding_model_invalidates_every_stored_vector(db, make_user, git_repo, monkeypatch):
    rid = await _new_repo(make_user, git_repo)
    first = await _index(rid)
    settings = indexing.get_settings()
    monkeypatch.setattr(settings, "embed_model", "some/other-model", raising=False)
    again = await _index(rid)
    assert set(again.seen) == set(first.seen)


async def test_failed_reindex_keeps_the_previous_index(db, make_user, git_repo, monkeypatch):
    rid = await _new_repo(make_user, git_repo)
    await _index(rid)
    before = await _vectors_by_location(rid)

    async def fail_save(*a, **k):
        raise RuntimeError("save failed")
    monkeypatch.setattr(indexing, "_save", fail_save)
    await _index(rid)
    assert (await _repo(rid)).status == "failed"
    assert await _vectors_by_location(rid) == before                   # the old index is untouched, hashes included
