import logging

import stripe
from fastapi import APIRouter, HTTPException, Query, status

from src.api.dependencies import CurrentUser, DBSession
from src.api.schemas.balance import (
    BalanceResponse,
    CheckoutRequest,
    CheckoutResponse,
    TransactionListResponse,
    TransactionResponse,
)
from src.core.config import settings
from src.infrastructure.database.repositories.transaction_repo import (
    SQLAlchemyTransactionRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=BalanceResponse)
async def get_balance(user: CurrentUser):
    return BalanceResponse(balance=user.balance)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(body: CheckoutRequest, user: CurrentUser):
    """Create a Stripe Checkout Session. Returns the URL to redirect the user to."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe is not configured.",
        )

    stripe.api_key = settings.stripe_secret_key
    amount_cents = int(body.amount_usd * 100)
    tokens = int(body.amount_usd * settings.stripe_tokens_per_dollar)

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"{tokens} AI Generation Tokens",
                            "description": f"Top up your balance with {tokens} tokens",
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            metadata={"external_user_id": user.external_user_id},
            success_url=f"{settings.fal_webhook_base_url}/?topup=success",
            cancel_url=f"{settings.fal_webhook_base_url}/?topup=cancelled",
        )
    except stripe.StripeError as e:
        logger.error("Stripe checkout creation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create payment session.",
        ) from e

    logger.info(
        "Stripe checkout session created",
        extra={
            "user_id": str(user.id),
            "amount_usd": str(body.amount_usd),
            "tokens": tokens,
        },
    )
    return CheckoutResponse(
        checkout_url=checkout_session.url,
        session_id=checkout_session.id,
    )


@router.get("/transactions", response_model=TransactionListResponse)
async def get_transactions(
    user: CurrentUser,
    session: DBSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    tx_repo = SQLAlchemyTransactionRepository(session)
    items = await tx_repo.list_by_user(user.id, offset=offset, limit=limit)
    return TransactionListResponse(items=[TransactionResponse.model_validate(tx) for tx in items])
