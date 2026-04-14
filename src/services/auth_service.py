import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import generate_api_key, hash_api_key
from src.infrastructure.database.repositories.user_repo import SQLAlchemyUserRepository

logger = logging.getLogger(__name__)


async def register_user(session: AsyncSession, external_user_id: str) -> str:
    """Register a new user and return the plain API key."""
    repo = SQLAlchemyUserRepository(session)

    existing = await repo.get_by_external_id(external_user_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this external_user_id already exists.",
        )

    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)
    user = await repo.create(external_user_id=external_user_id, api_key_hash=api_key_hash)

    logger.info(
        "User registered", extra={"user_id": str(user.id), "external_user_id": external_user_id}
    )
    return api_key
