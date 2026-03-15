from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.core.db.schema import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(database_url: str) -> AsyncEngine:
    global _engine, _session_factory
    _engine = create_async_engine(
        database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("DB engine not initialized. Call create_engine() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Session factory not initialized. Call create_engine() first.")
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends용 세션 제공자."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def create_tables() -> None:
    """개발용 — 테이블 자동 생성. 프로덕션은 Alembic 사용."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    """Graceful shutdown 시 DB 연결 풀 종료."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
