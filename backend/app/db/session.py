from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings

_s = get_settings()
engine = create_async_engine(
    _s.database_url,
    pool_pre_ping=True,                         # test a pooled connection before use (it may have been closed while idle)
    pool_size=_s.db_pool_size,
    max_overflow=_s.db_max_overflow,
    pool_recycle=_s.db_pool_recycle_seconds,
    connect_args={"connect_timeout": _s.db_connect_timeout_seconds},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with SessionLocal() as session:
        yield session
