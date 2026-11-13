"""The FastEmbed worker pool is only used for big corpora, and is always shut down by the indexer."""
import pytest

from ai_pipeline.embeddings import FastEmbedEmbeddings, HashEmbeddings


class _Vec(list):
    def tolist(self):
        return list(self)


class _FakeModel:
    def __init__(self):
        self.parallel_seen = []

    def passage_embed(self, texts, batch_size, parallel):
        self.parallel_seen.append(parallel)
        for _ in texts:
            yield _Vec([0.0, 1.0])


def _embedder(parallelism, min_chunks):
    e = FastEmbedEmbeddings.__new__(FastEmbedEmbeddings)          # skip downloading the real model
    e._model, e.dim, e.batch_size = _FakeModel(), 2, 64
    e.parallelism, e.parallel_min_chunks = parallelism, min_chunks
    return e


@pytest.mark.parametrize("parallelism,count,expected", [(4, 10, None), (4, 2000, 4), (1, 5000, None), (2, 1999, None)])
def test_pool_only_for_large_corpora(parallelism, count, expected):
    e = _embedder(parallelism, 2000)
    assert len(e.embed_documents(["x"] * count)) == count
    assert e._model.parallel_seen == [expected]


async def test_indexer_closes_the_embedding_iterator_when_it_fails(db, make_user, git_repo, monkeypatch):
    """If anything raises mid-embedding, the generator (and with it FastEmbed's worker pool) is closed."""
    from app.db.session import SessionLocal
    from app.models import Repository
    from app.services import indexing
    from tests.test_api import FakeLLM

    state = {"closed": False, "n": 0}

    class Boom(HashEmbeddings):
        def iter_embed_documents(self, texts):
            try:
                for t in texts:
                    state["n"] += 1
                    yield self._vec(t)
            finally:
                state["closed"] = True

    async def fail_save(*a, **k):
        raise RuntimeError("save failed")
    monkeypatch.setattr(indexing, "_save", fail_save)
    user, _ = await make_user(token="gho_x")
    async with SessionLocal() as s:
        r = Repository(owner_id=user.id, url=str(git_repo), branch="", status="queued")
        s.add(r)
        await s.commit()
        rid = r.id
    await indexing.run_indexing(rid, None, llm=FakeLLM(), embedder=Boom(384))
    async with SessionLocal() as s:
        repo = await s.get(Repository, rid)
    assert state["n"] > 0 and state["closed"] is True
    assert repo.status == "failed"
