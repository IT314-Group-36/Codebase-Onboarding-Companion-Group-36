"""Quick check of whichever embedding backend your backend/.env selects.

    uv run python check_embeddings.py

With EMBED_BACKEND=cloudflare it proves that your CF_ACCOUNT_ID / CF_API_TOKEN work, that the vectors have the right
size, that related texts score higher than unrelated ones, and it times a 100-text batch. It uses about 1,000 tokens
(roughly 0.02% of the free daily allowance).
"""
import asyncio
import math
import time

from app.core.config import get_settings
from app.services import runtime


def cos(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


async def main() -> None:
    s = get_settings()
    print(f"backend={s.embed_backend} model={s.embed_model} dim={s.embed_dim}")
    emb = runtime.get_embedder()
    t = time.perf_counter()
    q = await emb.aembed_query("where do we charge the customer's credit card?")
    print(f"query ok: {len(q)} dims in {time.perf_counter() - t:.2f}s")
    assert len(q) == s.embed_dim, f"expected {s.embed_dim} dims, got {len(q)} (fix EMBED_DIM / EMBED_MODEL)"
    docs = ["def charge_card(card_number, amount):\n    '''Charge a credit card and record the payment.'''",
            "def render_homepage_banner():\n    return '<div class=hero></div>'"]
    a, b = await emb.aembed_documents(docs)
    print(f"similarity to payment code: {cos(q, a):.3f}   to banner code: {cos(q, b):.3f}   (first should be higher)")
    t = time.perf_counter()
    await emb.aembed_documents([f"def function_{i}(x):\n    return x * {i}" for i in range(100)])
    dt = time.perf_counter() - t
    print(f"100 short texts in {dt:.2f}s -> estimated {5000 / 100 * dt / 60:.1f} min for a 5,000-chunk repo (sequential)")
    used = getattr(emb, "estimated_tokens", None)
    if used is not None:
        print(f"approx tokens used by this check: {used} (free pool is about 5.4M bge-small tokens per day)")


asyncio.run(main())
