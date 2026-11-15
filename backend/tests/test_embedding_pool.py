"""The indexer always closes an embedder's streaming iterator (if it has one), even when saving fails."""
from ai_pipeline.embeddings import HashEmbeddings


async def test_indexer_closes_the_embedding_iterator_when_it_fails(db, make_user, git_repo, monkeypatch):
    """If anything raises mid-embedding, the embedder's generator is closed."""
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
