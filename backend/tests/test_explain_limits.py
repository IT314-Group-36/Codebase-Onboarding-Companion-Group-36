"""Explanation cache misses must spend the same per-user AI quota as Q&A."""
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Explanation
from tests.test_api import client, index  # noqa: F401 (shared fixture)
from tests.test_explain import ExplainLLM, explain, use_llm


@pytest.mark.parametrize("first, second", [
    ({"file": "shop/payments.py"}, {"file": "shop/db.py"}),
    ({"symbol": "charge_card"}, {"symbol": "save_order"}),
])
async def test_cache_misses_use_ai_quota_but_cache_hits_remain_available(
    client, git_repo, monkeypatch, first, second,
):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)

    generated = await explain(client, rid, **first)
    assert generated.status_code == 200 and generated.json()["source"] == "llm"
    refused = await explain(client, rid, **second)
    assert refused.status_code == 429 and "AI requests" in refused.json()["detail"]
    assert int(refused.headers["Retry-After"]) >= 1
    assert len(llm.calls) == 1  # Rejection happens before the model is invoked.

    cached = await explain(client, rid, **first)
    assert cached.status_code == 200 and cached.json()["source"] == "cache"
    assert cached.json()["explanation"] == generated.json()["explanation"]
    assert len(llm.calls) == 1
    async with SessionLocal() as session:
        rows = (await session.execute(select(Explanation).where(Explanation.repo_id == rid))).scalars().all()
    assert len(rows) == 1  # No cache entry was created for the rejected target.
