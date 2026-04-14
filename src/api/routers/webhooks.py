import json
import logging
from typing import Any

import stripe
from fastapi import APIRouter, HTTPException, Request, status

from src.api.dependencies import DBSession
from src.api.schemas.webhook import PaymentWebhookRequest, PaymentWebhookResponse
from src.core.config import settings
from src.core.security import verify_webhook_signature
from src.services.balance_service import topup_balance

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/payment", response_model=PaymentWebhookResponse, status_code=status.HTTP_200_OK)
async def payment_webhook(request: Request, session: DBSession):
    raw_body = await request.body()

    if not settings.payment_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment webhook secret is not configured.",
        )

    signature = request.headers.get("x-webhook-signature", "")
    if not signature:
        logger.warning("Payment webhook: missing signature header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Webhook-Signature header.",
        )

    if not verify_webhook_signature(raw_body, signature, settings.payment_webhook_secret):
        logger.warning("Payment webhook: invalid signature")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature.",
        )

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON."
        ) from exc

    body = PaymentWebhookRequest(**data)
    new_balance = await topup_balance(session, body.external_user_id, body.amount)
    return PaymentWebhookResponse(new_balance=new_balance)


@router.post("/fal/{task_id}", status_code=status.HTTP_200_OK)
async def fal_webhook(task_id: str, session: DBSession, payload: dict[str, Any] | None = None):
    from src.services.generation_service import handle_fal_webhook

    await handle_fal_webhook(session, task_id, payload or {})
    return {"status": "ok"}


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, session: DBSession):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe webhook secret is not configured.",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.stripe_webhook_secret,
        )
    except ValueError as exc:
        logger.warning("Stripe webhook: invalid payload")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload."
        ) from exc
    except stripe.SignatureVerificationError as exc:
        logger.warning("Stripe webhook: invalid signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature."
        ) from exc

    from src.services.stripe_service import handle_stripe_event

    try:
        result = await handle_stripe_event(session, event)
    except ValueError as e:
        logger.error("Stripe webhook processing error: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return result
