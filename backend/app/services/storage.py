"""Short, database-serialized reservations for storage-controlled writes."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Transaction-scoped, shared by all API processes; released by commit/rollback.
# Never hold this lock while waiting for Git, embeddings or an AI provider.
STORAGE_LOCK_KEY = 73636001


async def lock_storage(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": STORAGE_LOCK_KEY})
