from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_api_key
from src.infrastructure.database.models import User
from src.infrastructure.database.repositories.user_repo import SQLAlchemyUserRepository
from src.infrastructure.database.session import get_session

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

DBSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: DBSession,
    api_key: str | None = Security(api_key_header),
) -> User:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required. Pass it via X-API-Key header.",
        )
    key_hash = hash_api_key(api_key)
    repo = SQLAlchemyUserRepository(session)
    user = await repo.get_by_api_key_hash(key_hash)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
