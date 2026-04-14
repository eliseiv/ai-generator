import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class TransactionEntity:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_id: uuid.UUID | None = None
    type: str = ""
    amount: Decimal = Decimal("0.00")
    task_id: uuid.UUID | None = None
    created_at: datetime | None = None
