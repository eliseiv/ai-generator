from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interfaces.task_repository import TaskRepository
from src.infrastructure.database.models import Task


class SQLAlchemyTaskRepository(TaskRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, **kwargs: Any) -> Task:
        task = Task(**kwargs)
        self._session.add(task)
        await self._session.flush()
        return task

    async def get_by_id(self, task_id: UUID) -> Task | None:
        return await self._session.get(Task, task_id)

    async def update(self, task_id: UUID, **kwargs: Any) -> Task:
        stmt = update(Task).where(Task.id == task_id).values(**kwargs).returning(Task)
        result = await self._session.execute(stmt)
        task = result.scalar_one()
        await self._session.flush()
        return task

    async def list_by_user(self, user_id: UUID, offset: int = 0, limit: int = 20) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .order_by(Task.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
