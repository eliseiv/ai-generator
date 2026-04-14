import asyncio
import logging
from uuid import UUID

from src.core.config import settings
from src.infrastructure.database.models import WebhookDeliveryStatus
from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class WebhookDeliveryError(RuntimeError):
    """Raised when a webhook delivery attempt fails."""


async def _deliver_webhook(task_id: str) -> None:
    from src.infrastructure.database.session import get_session_factory
    from src.services.webhook_service import send_webhook

    factory = get_session_factory()
    async with factory() as session:
        success = await send_webhook(session, UUID(task_id))
        await session.commit()

        if not success:
            raise WebhookDeliveryError(f"Webhook delivery failed for task {task_id}")


@celery_app.task(
    name="webhook.deliver",
    bind=True,
    max_retries=settings.webhook_max_retries,
    default_retry_delay=settings.webhook_retry_interval_seconds,
)
def deliver_webhook(self, task_id: str) -> None:
    try:
        asyncio.run(_deliver_webhook(task_id))
    except WebhookDeliveryError as exc:
        retries_left = self.max_retries - self.request.retries
        logger.warning(
            "Webhook delivery attempt failed, retries left: %d",
            retries_left,
            extra={"task_id": task_id},
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc) from exc

        logger.error(
            "Webhook delivery exhausted all retries",
            extra={"task_id": task_id},
        )
        asyncio.run(_mark_webhook_failed(task_id))


async def _mark_webhook_failed(task_id: str) -> None:
    from src.infrastructure.database.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        from src.infrastructure.database.repositories.task_repo import (
            SQLAlchemyTaskRepository,
        )

        task_repo = SQLAlchemyTaskRepository(session)
        task = await task_repo.get_by_id(UUID(task_id))
        if task:
            from src.infrastructure.database.repositories.webhook_delivery_repo import (
                SQLAlchemyWebhookDeliveryRepository,
            )

            wd_repo = SQLAlchemyWebhookDeliveryRepository(session)
            for delivery in task.webhook_deliveries:
                if delivery.status != WebhookDeliveryStatus.DELIVERED:
                    await wd_repo.update_attempt(
                        delivery.id,
                        status=WebhookDeliveryStatus.FAILED,
                        attempts=delivery.attempts,
                    )
        await session.commit()
