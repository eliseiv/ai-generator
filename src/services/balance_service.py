import logging
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import TransactionType
from src.infrastructure.database.repositories.transaction_repo import (
    SQLAlchemyTransactionRepository,
)
from src.infrastructure.database.repositories.user_repo import SQLAlchemyUserRepository

logger = logging.getLogger(__name__)


async def topup_balance(session: AsyncSession, external_user_id: str, amount: Decimal) -> Decimal:
    user_repo = SQLAlchemyUserRepository(session)
    tx_repo = SQLAlchemyTransactionRepository(session)

    user = await user_repo.get_by_external_id(external_user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with external_user_id '{external_user_id}' not found.",
        )

    user = await user_repo.update_balance(user.id, amount)
    await tx_repo.create(user.id, TransactionType.TOPUP, amount)

    logger.info(
        "Balance topped up",
        extra={"user_id": str(user.id), "amount": str(amount), "new_balance": str(user.balance)},
    )
    return user.balance


async def charge_balance(
    session: AsyncSession, user_id: UUID, amount: Decimal, task_id: UUID
) -> None:
    user_repo = SQLAlchemyUserRepository(session)
    tx_repo = SQLAlchemyTransactionRepository(session)

    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.balance < amount:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient balance. Required: {amount}, available: {user.balance}",
        )

    await user_repo.update_balance(user_id, -amount)
    await tx_repo.create(user_id, TransactionType.CHARGE, amount, task_id=task_id)
    logger.info("Balance charged", extra={"user_id": str(user_id), "amount": str(amount)})


async def refund_balance(
    session: AsyncSession, user_id: UUID, amount: Decimal, task_id: UUID
) -> None:
    user_repo = SQLAlchemyUserRepository(session)
    tx_repo = SQLAlchemyTransactionRepository(session)

    await user_repo.update_balance(user_id, amount)
    await tx_repo.create(user_id, TransactionType.REFUND, amount, task_id=task_id)
    logger.info("Balance refunded", extra={"user_id": str(user_id), "amount": str(amount)})
