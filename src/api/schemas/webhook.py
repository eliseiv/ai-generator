from decimal import Decimal

from pydantic import BaseModel, Field


class PaymentWebhookRequest(BaseModel):
    external_user_id: str = Field(..., min_length=1, max_length=255)
    amount: Decimal = Field(..., gt=0, description="Amount in tokens to add")


class PaymentWebhookResponse(BaseModel):
    status: str = "ok"
    new_balance: Decimal
