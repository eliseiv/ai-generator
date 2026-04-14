import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class BalanceResponse(BaseModel):
    balance: Decimal


class CheckoutRequest(BaseModel):
    amount_usd: Decimal = Field(..., gt=0, le=10000, description="Amount in USD")


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class TransactionResponse(BaseModel):
    id: uuid.UUID
    type: str
    amount: Decimal
    task_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
