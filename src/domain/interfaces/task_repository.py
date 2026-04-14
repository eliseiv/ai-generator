from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from src.infrastructure.database.models import Task


class TaskRepository(ABC):
    @abstractmethod
    async def create(self, **kwargs: Any) -> Task: ...

    @abstractmethod
    async def get_by_id(self, task_id: UUID) -> Task | None: ...

    @abstractmethod
    async def update(self, task_id: UUID, **kwargs: Any) -> Task: ...

    @abstractmethod
    async def list_by_user(self, user_id: UUID, offset: int = 0, limit: int = 20) -> list[Task]: ...
