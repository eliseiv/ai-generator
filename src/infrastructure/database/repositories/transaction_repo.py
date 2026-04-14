from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import Transaction, TransactionType


class SQLAlchemyTransactionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        user_id: UUID,
        tx_type: TransactionType,
        amount: Decimal,
        task_id: UUID | None = None,
    ) -> Transaction:
        tx = Transaction(
            user_id=user_id,
            type=tx_type,
            amount=amount,
            task_id=task_id,
        )
        self._session.add(tx)
        await self._session.flush()
        return tx

    async def list_by_user(
        self, user_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Transaction]:
        stmt = (
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
