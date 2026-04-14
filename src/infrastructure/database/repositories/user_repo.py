from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interfaces.user_repository import UserRepository
from src.infrastructure.database.models import User


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, external_user_id: str, api_key_hash: str) -> User:
        user = User(external_user_id=external_user_id, api_key_hash=api_key_hash)
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_api_key_hash(self, api_key_hash: str) -> User | None:
        stmt = select(User).where(User.api_key_hash == api_key_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_user_id: str) -> User | None:
        stmt = select(User).where(User.external_user_id == external_user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_balance(self, user_id: UUID, delta: Decimal) -> User:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(balance=User.balance + delta)
            .returning(User)
        )
        result = await self._session.execute(stmt)
        user = result.scalar_one()
        await self._session.flush()
        return user
