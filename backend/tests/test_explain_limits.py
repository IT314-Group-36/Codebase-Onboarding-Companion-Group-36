"""Explanation cache misses must spend the same per-user AI quota as Q&A."""
import asyncio

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.ratelimit import enforce_llm
from app.db.session import SessionLocal
from app.models import Explanation
from tests.conftest import api_client
from tests.test_api import client, index  # noqa: F401 (shared fixture)
from tests.test_explain import ExplainLLM, explain, use_llm


@pytest.mark.parametrize("first, second", [
    ({"file": "shop/payments.py"}, {"file": "shop/db.py"}),
    ({"symbol": "charge_card"}, {"symbol": "save_order"}),
])
@pytest.mark.parametrize("limit_name", ["rate_limit_llm_per_minute", "rate_limit_llm_per_hour"])
async def test_cache_misses_use_ai_quota_but_cache_hits_remain_available(
    client, git_repo, monkeypatch, first, second, limit_name,
):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), limit_name, 1)

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


@pytest.mark.parametrize("endpoint", ["ask", "ask/stream"])
async def test_explanation_generation_spends_the_shared_qa_budget(client, git_repo, monkeypatch, endpoint):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 200

    response = await client.post(f"/repos/{rid}/{endpoint}", json={"question": "Where are payments handled?"})
    assert response.status_code == 429 and "AI requests" in response.json()["detail"]
    assert "Retry-After" in response.headers and len(llm.calls) == 1


async def test_explanations_cannot_bypass_an_exhausted_qa_budget(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    question = await client.post(f"/repos/{rid}/ask", json={"question": "Where are payments handled?"})
    assert question.status_code == 200
    response = await explain(client, rid, symbol="charge_card")
    assert response.status_code == 429 and len(llm.calls) == 1


async def test_refresh_cannot_bypass_ai_quota_or_replace_cached_explanation(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    first = await explain(client, rid, file="shop/payments.py")
    assert first.status_code == 200
    refreshed = await explain(client, rid, file="shop/payments.py", refresh="true")
    assert refreshed.status_code == 429 and "AI requests" in refreshed.json()["detail"]
    assert len(llm.calls) == 1
    cached = await explain(client, rid, file="shop/payments.py")
    assert cached.status_code == 200 and cached.json()["source"] == "cache"
    assert cached.json()["explanation"] == first.json()["explanation"]


async def test_refresh_consumes_exactly_one_ai_slot_and_retains_its_extra_limit(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 3)
    monkeypatch.setattr(get_settings(), "rate_limit_refresh_per_hour", 1)
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 200
    assert (await explain(client, rid, file="shop/payments.py", refresh="true")).status_code == 200
    refused_refresh = await explain(client, rid, file="shop/payments.py", refresh="true")
    assert refused_refresh.status_code == 429 and "refresh" in refused_refresh.json()["detail"]
    assert (await explain(client, rid, file="shop/db.py")).status_code == 200
    assert (await explain(client, rid, symbol="charge_card")).status_code == 429
    assert len(llm.calls) == 3  # Normal + refreshed + another target, not double-charged.


async def test_relationship_only_responses_and_cache_hits_work_without_ai_quota(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 200
    for path in (".env", "shop/__init__.py"):  # Sensitive and no indexed text.
        response = await explain(client, rid, file=path)
        assert response.status_code == 200 and response.json()["source"] == "none"
    assert len(llm.calls) == 1

    use_llm(None)
    uncached = await explain(client, rid, file="shop/db.py")
    assert uncached.status_code == 200 and uncached.json()["source"] == "none"
    cached = await explain(client, rid, file="shop/payments.py")
    assert cached.status_code == 200 and cached.json()["source"] == "cache"


async def test_invalid_targets_do_not_consume_ai_quota(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    assert (await explain(client, rid)).status_code == 422
    assert (await explain(client, rid, file="missing.py")).status_code == 404
    assert (await explain(client, rid, symbol="c")).status_code == 409
    assert (await explain(client, rid, symbol="charge_card")).status_code == 200


async def test_cache_hits_do_not_charge_ai_quota_but_still_obey_read_limit(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_read_per_minute", 2)
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 200
    cached = await explain(client, rid, file="shop/payments.py")
    assert cached.status_code == 200 and cached.json()["source"] == "cache"
    refused = await explain(client, rid, file="shop/payments.py")
    assert refused.status_code == 429 and "AI requests" not in refused.json()["detail"]
    assert len(llm.calls) == 1


async def test_provider_failure_still_consumes_ai_quota(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM(fail=True))
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 502
    llm.fail = False
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 429
    assert len(llm.calls) == 1
    async with SessionLocal() as session:
        assert (await session.execute(select(Explanation).where(Explanation.repo_id == rid))).first() is None


async def test_stale_cache_is_a_quota_checked_miss(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 200
    async with SessionLocal() as session:
        await session.execute(update(Explanation).where(Explanation.repo_id == rid).values(commit_sha="0" * 40))
        await session.commit()
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 429
    assert len(llm.calls) == 1


async def test_ai_budget_is_per_user_not_per_repository(client, git_repo, monkeypatch, make_user):
    rid = await index(client, git_repo)
    second_repo = await index(client, git_repo, branch="main")
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 200
    assert (await explain(client, second_repo, file="shop/payments.py")).status_code == 429
    _, headers = await make_user(github_id=2, login="other")
    async with api_client(headers) as other:
        other_repo = await index(other, git_repo)
        assert (await explain(other, other_repo, file="shop/payments.py")).status_code == 200
    assert len(llm.calls) == 2


async def test_concurrent_misses_cannot_exceed_one_ai_slot(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    responses = await asyncio.gather(
        explain(client, rid, file="shop/payments.py"),
        explain(client, rid, symbol="save_order"),
    )
    assert sorted(response.status_code for response in responses) == [200, 429]
    assert len(llm.calls) == 1


async def test_disabling_rate_limits_also_disables_explanation_ai_limit(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    llm = use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 1)
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 200
    assert (await explain(client, rid, symbol="save_order")).status_code == 200
    assert len(llm.calls) == 2


async def test_cache_reads_do_not_use_up_remaining_ai_slots(client, git_repo, monkeypatch):
    rid = await index(client, git_repo)
    use_llm(ExplainLLM())
    monkeypatch.setattr(get_settings(), "rate_limit_llm_per_minute", 2)
    assert (await explain(client, rid, file="shop/payments.py")).status_code == 200
    assert (await explain(client, rid, file="shop/payments.py")).json()["source"] == "cache"
    enforce_llm(client.user.id)  # The cache read must leave the second shared slot available.
    assert (await explain(client, rid, symbol="save_order")).status_code == 429
