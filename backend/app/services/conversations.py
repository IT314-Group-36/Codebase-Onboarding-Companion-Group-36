"""Bounded chat persistence. Reserve storage in short transactions before AI work."""
import json
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import Text, case, cast, exists, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Conversation, ConversationMessage, Repository
from app.services.storage import (
    CONVERSATION_BYTES,
    check_storage_budget,
    lock_storage,
    message_reservation_bytes,
)

DEFAULT_TITLE = "New conversation"
CONTEXT_ROWS = 24


def bounded_text(text: str, byte_limit: int) -> str:
    return text.encode("utf-8")[:byte_limit].decode("utf-8", errors="ignore")


def bounded_citations(citations: list) -> list[dict]:
    """Keep a bounded JSON payload without inventing/truncating citation paths."""
    if not isinstance(citations, list):
        return []
    result = []
    for item in citations[:32]:
        if not isinstance(item, dict):
            continue
        path, start, end = item.get("path"), item.get("start_line"), item.get("end_line")
        if not isinstance(path, str) or len(path) > 1000:
            continue
        if start is None and end is None:  # Older persisted answers may cite a path without lines.
            citation = {"path": path}
        elif isinstance(start, int) and isinstance(end, int) and 1 <= start <= end:
            citation = {"path": path, "start_line": start, "end_line": end}
        else:
            continue
        if len(json.dumps([*result, citation], ensure_ascii=False).encode("utf-8")) > get_settings().max_message_citations_bytes:
            break
        result.append(citation)
    return result


async def _check_conversation_slots(session: AsyncSession, repo: Repository) -> None:
    cfg = get_settings()
    per_repo = await session.scalar(select(func.count()).select_from(Conversation).where(Conversation.repo_id == repo.id))
    per_user = await session.scalar(select(func.count()).select_from(Conversation).where(
        Conversation.user_id == repo.owner_id))
    total = await session.scalar(select(func.count()).select_from(Conversation))
    if per_repo >= cfg.max_conversations_per_repo or per_user >= cfg.max_conversations_per_user:
        raise HTTPException(403, "Your conversation limit is reached. Delete an old chat before starting a new one.")
    if total >= cfg.max_total_conversations:
        raise HTTPException(503, "The server's conversation storage is full.")


async def create_chat(session: AsyncSession, repo: Repository, title: str) -> Conversation:
    await lock_storage(session)
    empty = await session.scalar(select(Conversation).where(
        Conversation.repo_id == repo.id, Conversation.user_id == repo.owner_id,
        ~exists().where(ConversationMessage.conversation_id == Conversation.id),
    ).order_by(Conversation.id.desc()).limit(1))
    if empty is not None:
        if title != DEFAULT_TITLE:
            empty.title = title
        await session.commit()
        await session.refresh(empty)
        return empty
    await _check_conversation_slots(session, repo)
    await check_storage_budget(session, CONVERSATION_BYTES)
    conversation = Conversation(user_id=repo.owner_id, repo_id=repo.id, title=title)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def message_page(session: AsyncSession, conversation_id: int, limit: int, offset: int = 0):
    """Bound SQL payloads too, so large legacy messages cannot create huge responses."""
    cfg = get_settings()
    rows = (await session.execute(select(
        ConversationMessage.id, ConversationMessage.role, ConversationMessage.status, ConversationMessage.created_at,
        func.left(ConversationMessage.content, cfg.max_message_content_bytes).label("content"),
        (func.octet_length(ConversationMessage.content) > cfg.max_message_content_bytes).label("truncated"),
        case((func.octet_length(cast(ConversationMessage.citations, Text)) <= cfg.max_message_citations_bytes,
              ConversationMessage.citations), else_=cast("[]", JSONB)).label("citations"),
    ).where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
        .limit(limit).offset(offset))).all()
    return [SimpleNamespace(id=row.id, role=row.role, status=row.status, created_at=row.created_at,
                            content=bounded_text(row.content, cfg.max_message_content_bytes),
                            citations=bounded_citations(row.citations), truncated=row.truncated)
            for row in reversed(rows)]


async def reserve_turn(session: AsyncSession, repo: Repository, question: str, conversation_id: int | None):
    """Atomically reserve parent/turn rows; release the lock BEFORE provider work."""
    cfg = get_settings()
    if len(question.encode("utf-8")) > cfg.max_message_content_bytes:
        raise HTTPException(413, "This question exceeds the configured message byte limit.")
    await lock_storage(session)
    conversation = None
    if conversation_id is not None:
        conversation = await session.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.repo_id == repo.id,
            Conversation.user_id == repo.owner_id,
        ))
        if conversation is None:
            raise HTTPException(404, "Conversation not found")
    else:
        await _check_conversation_slots(session, repo)

    per_chat = 0 if conversation is None else await session.scalar(select(func.count()).select_from(
        ConversationMessage).where(ConversationMessage.conversation_id == conversation.id))
    per_user = await session.scalar(select(func.count()).select_from(ConversationMessage).join(Conversation).where(
        Conversation.user_id == repo.owner_id))
    total = await session.scalar(select(func.count()).select_from(ConversationMessage))
    if per_chat + 2 > cfg.max_messages_per_conversation or per_user + 2 > cfg.max_messages_per_user:
        raise HTTPException(403, "Your message limit is reached. Delete an old chat or start a new one if this chat is full.")
    if total + 2 > cfg.max_total_messages:
        raise HTTPException(503, "The server's message storage is full.")
    await check_storage_budget(session, 2 * message_reservation_bytes()
                               + (CONVERSATION_BYTES if conversation is None else 0))
    if conversation is None:
        conversation = Conversation(user_id=repo.owner_id, repo_id=repo.id,
                                    title=question.strip()[:200] or DEFAULT_TITLE)
        session.add(conversation)
        await session.flush()

    previous = await message_page(session, conversation.id, CONTEXT_ROWS)
    conversation.updated_at = func.now()
    if conversation.title == DEFAULT_TITLE and not previous:
        conversation.title = question.strip()[:200] or DEFAULT_TITLE
    user_message = ConversationMessage(conversation_id=conversation.id, role="user", content=question, status="completed")
    assistant_message = ConversationMessage(conversation_id=conversation.id, role="assistant", content="", status="pending")
    session.add_all([user_message, assistant_message])
    await session.commit()
    return conversation, user_message, assistant_message, previous


async def delete_chat(session: AsyncSession, repo: Repository, conversation_id: int) -> None:
    await lock_storage(session)
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == conversation_id, Conversation.repo_id == repo.id, Conversation.user_id == repo.owner_id,
    ))
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    pending = await session.scalar(select(ConversationMessage.id).where(
        ConversationMessage.conversation_id == conversation_id, ConversationMessage.status == "pending",
    ).limit(1))
    if pending is not None:
        raise HTTPException(409, "Wait for the current answer to finish before deleting this chat.")
    await session.delete(conversation)  # FK cascade removes all its messages and releases reservations.
    await session.commit()
