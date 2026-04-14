from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings


class _SessionState:
    engine: AsyncEngine | None = None
    factory: async_sessionmaker[AsyncSession] | None = None


_state = _SessionState()


def get_engine() -> AsyncEngine:
    if _state.engine is None:
        _state.engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_size=20,
            max_overflow=10,
        )
    return _state.engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _state.factory is None:
        _state.factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _state.factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
