import logging
from decimal import Decimal

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.infrastructure.database.models import TransactionType
from src.infrastructure.database.repositories.transaction_repo import (
    SQLAlchemyTransactionRepository,
)
from src.infrastructure.database.repositories.user_repo import SQLAlchemyUserRepository

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_secret_key


async def handle_stripe_event(
    session: AsyncSession,
    event: stripe.Event,
) -> dict:
    """Process a verified Stripe webhook event and return a status dict."""
    event_type = event["type"]

    if event_type == "checkout.session.completed":
        return await _handle_checkout_completed(session, event["data"]["object"])

    if event_type == "payment_intent.succeeded":
        return await _handle_payment_succeeded(session, event["data"]["object"])

    logger.info("Unhandled Stripe event type: %s", event_type)
    return {"status": "ignored", "event_type": event_type}


async def _handle_checkout_completed(
    session: AsyncSession,
    checkout_session: dict,
) -> dict:
    external_user_id = (checkout_session.get("metadata") or {}).get("external_user_id")
    if not external_user_id:
        logger.warning("Stripe checkout.session.completed without external_user_id in metadata")
        return {"status": "skipped", "reason": "no external_user_id in metadata"}

    amount_total = checkout_session.get("amount_total", 0)
    currency = checkout_session.get("currency", "usd")

    tokens = _cents_to_tokens(amount_total, currency)
    new_balance = await _topup_user(session, external_user_id, tokens)

    logger.info(
        "Stripe checkout completed",
        extra={
            "external_user_id": external_user_id,
            "amount_cents": amount_total,
            "tokens": str(tokens),
        },
    )
    return {
        "status": "processed",
        "external_user_id": external_user_id,
        "tokens_added": str(tokens),
        "new_balance": str(new_balance),
    }


async def _handle_payment_succeeded(
    session: AsyncSession,
    payment_intent: dict,
) -> dict:
    external_user_id = (payment_intent.get("metadata") or {}).get("external_user_id")
    if not external_user_id:
        logger.warning("Stripe payment_intent.succeeded without external_user_id in metadata")
        return {"status": "skipped", "reason": "no external_user_id in metadata"}

    amount = payment_intent.get("amount", 0)
    currency = payment_intent.get("currency", "usd")

    tokens = _cents_to_tokens(amount, currency)
    new_balance = await _topup_user(session, external_user_id, tokens)

    logger.info(
        "Stripe payment succeeded",
        extra={
            "external_user_id": external_user_id,
            "amount_cents": amount,
            "tokens": str(tokens),
        },
    )
    return {
        "status": "processed",
        "external_user_id": external_user_id,
        "tokens_added": str(tokens),
        "new_balance": str(new_balance),
    }


def _cents_to_tokens(amount_cents: int, currency: str) -> Decimal:
    """Convert payment amount (in smallest currency unit) to tokens.

    Uses STRIPE_TOKENS_PER_DOLLAR setting.
    For USD: $1.00 = 100 cents → tokens_per_dollar tokens.
    """
    dollars = Decimal(amount_cents) / Decimal(100)
    return dollars * Decimal(settings.stripe_tokens_per_dollar)


async def _topup_user(
    session: AsyncSession,
    external_user_id: str,
    tokens: Decimal,
) -> Decimal:
    user_repo = SQLAlchemyUserRepository(session)
    tx_repo = SQLAlchemyTransactionRepository(session)

    user = await user_repo.get_by_external_id(external_user_id)
    if user is None:
        logger.error(
            "Stripe payment for unknown user",
            extra={"external_user_id": external_user_id},
        )
        raise ValueError(f"User with external_user_id '{external_user_id}' not found")

    user = await user_repo.update_balance(user.id, tokens)
    await tx_repo.create(user.id, TransactionType.TOPUP, tokens)
    return user.balance
