import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass
class TaskEntity:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_id: uuid.UUID | None = None
    type: str = ""
    status: str = "created"
    prompt: str = ""
    params: dict[str, Any] | None = None
    fal_request_id: str | None = None
    result_url: str | None = None
    result_metadata: dict[str, Any] | None = None
    cost: Decimal = Decimal("0.00")
    callback_url: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
