"""Short, database-serialized reservations for storage-controlled writes."""
from fastapi import HTTPException
from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Chunk, Conversation, ConversationMessage, TaskProgress

PROGRESS_BYTES = 1024
CONVERSATION_BYTES = 2048
MESSAGE_OVERHEAD_BYTES = 1024
# Transaction-scoped, shared by all API processes; released by commit/rollback.
# Never hold this lock while waiting for Git, embeddings or an AI provider.
STORAGE_LOCK_KEY = 73636001


async def lock_storage(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": STORAGE_LOCK_KEY})


def message_reservation_bytes() -> int:
    cfg = get_settings()
    return cfg.max_message_content_bytes + cfg.max_message_citations_bytes + MESSAGE_OVERHEAD_BYTES


def chunk_reservation_bytes(content: str) -> int:
    cfg = get_settings()
    return max(cfg.storage_chunk_bytes, len(content.encode("utf-8")) + cfg.embed_dim * 4 + 1024)


async def chunk_storage_bytes(session: AsyncSession, repo_id: int | None = None) -> int:
    cfg = get_settings()
    stmt = select(func.coalesce(func.sum(func.greatest(
        cfg.storage_chunk_bytes, func.octet_length(Chunk.content) + cfg.embed_dim * 4 + 1024,
    )), 0))
    if repo_id is not None:
        stmt = stmt.where(Chunk.repo_id == repo_id)
    return int(await session.scalar(stmt))


async def storage_usage_bytes(session: AsyncSession) -> int:
    """Planning estimate, not PostgreSQL physical disk usage.

    Reserve a full bounded payload for EVERY message, including pending/failed
    answers, so completing concurrent streams cannot outgrow their reservations.
    Larger legacy records are counted at their actual payload size instead.
    """
    chunks = await chunk_storage_bytes(session)
    progress = await session.scalar(select(func.count()).select_from(TaskProgress))
    conversations = await session.scalar(select(func.count()).select_from(Conversation))
    messages = await session.scalar(select(func.coalesce(func.sum(func.greatest(
        message_reservation_bytes(),
        func.octet_length(ConversationMessage.content)
        + func.octet_length(cast(ConversationMessage.citations, Text)) + MESSAGE_OVERHEAD_BYTES,
    )), 0)))
    return chunks + progress * PROGRESS_BYTES + conversations * CONVERSATION_BYTES + int(messages)


async def check_storage_budget(session: AsyncSession, extra_bytes: int, *,
                               replace_chunk_repo: int | None = None) -> None:
    """Check new reservations under lock_storage, before writing or generating.

    Read-only preflight may also use this; writers must recheck under the lock.
    Existing records are never silently purged when a limit is lowered.
    """
    if replace_chunk_repo is not None:
        extra_bytes -= await chunk_storage_bytes(session, replace_chunk_repo)
    if extra_bytes <= 0:
        return  # Allow updates/deletions/reindexes that do not increase reservations.
    if await storage_usage_bytes(session) + extra_bytes > get_settings().storage_budget_bytes:
        raise HTTPException(503, "The server's storage planning budget is full. Delete an old chat or repository "
                                 "or reset task progress to free capacity.")
