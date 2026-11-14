"""_embed_all sorts texts by length for faster batching, but must hand vectors back in the ORIGINAL order."""
import asyncio
import threading

import pytest

from app.services.indexing import _embed_all

TEXTS = ["a" * n + str(i) for i, n in enumerate([5, 300, 20, 1800, 7, 7, 900, 1, 450, 60, 33])]


def _vec(text: str) -> list[float]:
    return [float(len(text)), float(sum(map(ord, text)) % 997)]      # encodes the text, so a mix-up is detectable


class _IterEmbedder:                      # shaped like FastEmbedEmbeddings
    def __init__(self):
        self.closed = threading.Event()

    def iter_embed_documents(self, texts):
        try:
            for t in texts:
                yield _vec(t)
        finally:
            self.closed.set()


class _AsyncEmbedder:                     # shaped like any other LangChain Embeddings class
    async def aembed_documents(self, texts):
        return [_vec(t) for t in texts]


@pytest.mark.parametrize("factory", [_IterEmbedder, _AsyncEmbedder])
@pytest.mark.parametrize("batch_size", [1, 3, 4, 128])
async def test_vectors_come_back_in_original_order(factory, batch_size):
    progress = []

    async def on_progress(done, total):
        progress.append((done, total))

    embedder = factory()
    out = await _embed_all(TEXTS, embedder, batch_size, on_progress)
    assert out == [_vec(t) for t in TEXTS]
    assert progress[-1] == (len(TEXTS), len(TEXTS))
    assert [d for d, _ in progress] == sorted(d for d, _ in progress)      # progress never goes backwards
    if factory is _IterEmbedder:
        assert await asyncio.to_thread(embedder.closed.wait, 5)


async def test_empty_input():
    async def on_progress(done, total):
        pass
    assert await _embed_all([], _IterEmbedder(), 8, on_progress) == []


async def test_iterator_is_closed_when_progress_reporting_fails():
    embedder = _IterEmbedder()

    async def boom(done, total):
        raise RuntimeError("db down")

    with pytest.raises(RuntimeError):
        await _embed_all(TEXTS, embedder, 2, boom)
    assert await asyncio.to_thread(embedder.closed.wait, 5)      # close runs in the background; keeps the pool from leaking


async def test_cancelling_mid_batch_is_a_clean_cancel_and_closes_the_iterator():
    """Regression: cancelling while a batch ran in a thread used to raise 'generator already executing', which the
    indexer then saved as the repo's error. It must stay a CancelledError, and the generator must still be closed."""
    import time

    closed = threading.Event()

    class SlowEmbedder:
        def iter_embed_documents(self, texts):
            try:
                for _ in texts:
                    time.sleep(0.3)
                    yield [1.0]
            finally:
                closed.set()

    async def on_progress(done, total):
        pass

    task = asyncio.create_task(_embed_all(["x"] * 10, SlowEmbedder(), 2, on_progress))
    await asyncio.sleep(0.15)                   # a batch is running in its thread right now
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(closed.wait, 5)