import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class UserEntity:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    external_user_id: str = ""
    api_key_hash: str = ""
    balance: Decimal = Decimal("0.00")
    created_at: datetime | None = None
    updated_at: datetime | None = None
