import logging
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import WebhookDeliveryStatus
from src.infrastructure.database.repositories.task_repo import SQLAlchemyTaskRepository
from src.infrastructure.database.repositories.webhook_delivery_repo import (
    SQLAlchemyWebhookDeliveryRepository,
)

logger = logging.getLogger(__name__)


async def send_webhook(
    session: AsyncSession,
    task_id: UUID,
) -> bool:
    """Attempt to deliver webhook notification to client. Returns True on success."""
    task_repo = SQLAlchemyTaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    if task is None or not task.callback_url:
        return False

    delivery_repo = SQLAlchemyWebhookDeliveryRepository(session)

    existing = None
    for d in task.webhook_deliveries:
        if d.url == task.callback_url:
            existing = d
            break

    if existing is None:
        existing = await delivery_repo.create(task_id=task.id, url=task.callback_url)

    payload = {
        "task_id": str(task.id),
        "status": task.status.value if hasattr(task.status, "value") else task.status,
        "type": task.type.value if hasattr(task.type, "value") else task.type,
        "result_url": task.result_url,
        "error_message": task.error_message,
    }
    if task.result_metadata:
        payload["result_metadata"] = task.result_metadata

    attempt = existing.attempts + 1

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(task.callback_url, json=payload)

        if 200 <= response.status_code < 300:
            await delivery_repo.update_attempt(
                existing.id,
                status=WebhookDeliveryStatus.DELIVERED,
                attempts=attempt,
                response_code=response.status_code,
            )
            logger.info("Webhook delivered", extra={"task_id": str(task_id), "attempt": attempt})
            return True

        await delivery_repo.update_attempt(
            existing.id,
            status=WebhookDeliveryStatus.PENDING,
            attempts=attempt,
            response_code=response.status_code,
        )
        logger.warning(
            "Webhook delivery failed",
            extra={
                "task_id": str(task_id),
                "attempt": attempt,
                "status_code": response.status_code,
            },
        )
        return False

    except (httpx.HTTPError, OSError) as e:
        await delivery_repo.update_attempt(
            existing.id,
            status=WebhookDeliveryStatus.PENDING,
            attempts=attempt,
        )
        logger.error(
            "Webhook delivery error",
            extra={"task_id": str(task_id), "attempt": attempt, "error": str(e)},
        )
        return False
