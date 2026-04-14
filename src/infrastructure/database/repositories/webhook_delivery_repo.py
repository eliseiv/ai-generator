from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import WebhookDelivery, WebhookDeliveryStatus


class SQLAlchemyWebhookDeliveryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, task_id: UUID, url: str) -> WebhookDelivery:
        delivery = WebhookDelivery(task_id=task_id, url=url)
        self._session.add(delivery)
        await self._session.flush()
        return delivery

    async def get_by_id(self, delivery_id: UUID) -> WebhookDelivery | None:
        return await self._session.get(WebhookDelivery, delivery_id)

    async def update_attempt(
        self,
        delivery_id: UUID,
        status: WebhookDeliveryStatus,
        attempts: int,
        response_code: int | None = None,
    ) -> WebhookDelivery:
        stmt = (
            update(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .values(
                status=status,
                attempts=attempts,
                response_code=response_code,
                last_attempt_at=datetime.now(UTC),
            )
            .returning(WebhookDelivery)
        )
        result = await self._session.execute(stmt)
        delivery = result.scalar_one()
        await self._session.flush()
        return delivery
