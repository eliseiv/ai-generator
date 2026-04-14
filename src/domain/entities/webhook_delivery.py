import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class WebhookDeliveryEntity:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    task_id: uuid.UUID | None = None
    url: str = ""
    status: str = "pending"
    attempts: int = 0
    response_code: int | None = None
    last_attempt_at: datetime | None = None
    created_at: datetime | None = None
