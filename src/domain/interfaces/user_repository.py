from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID

from src.infrastructure.database.models import User


class UserRepository(ABC):
    @abstractmethod
    async def create(self, external_user_id: str, api_key_hash: str) -> User: ...

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def get_by_api_key_hash(self, api_key_hash: str) -> User | None: ...

    @abstractmethod
    async def get_by_external_id(self, external_user_id: str) -> User | None: ...

    @abstractmethod
    async def update_balance(self, user_id: UUID, delta: Decimal) -> User: ...
