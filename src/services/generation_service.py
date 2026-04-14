import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import GenerationType, TaskStatus
from src.infrastructure.database.repositories.task_repo import SQLAlchemyTaskRepository
from src.infrastructure.database.repositories.user_repo import SQLAlchemyUserRepository
from src.infrastructure.metrics import generation_cost_total, generation_requests_total
from src.services.balance_service import charge_balance, refund_balance
from src.services.pricing_service import get_generation_cost

logger = logging.getLogger(__name__)


@dataclass
class GenerationRequest:
    user_id: UUID
    generation_type: GenerationType
    prompt: str
    params: dict[str, Any] | None = None
    callback_url: str | None = None


async def create_generation_task(
    session: AsyncSession,
    request: GenerationRequest,
) -> dict[str, Any]:
    cost = await get_generation_cost(session, request.generation_type)

    user_repo = SQLAlchemyUserRepository(session)
    user = await user_repo.get_by_id(request.user_id)
    if user is None:
        raise ValueError("User not found")
    if user.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient balance. Required: {cost}, available: {user.balance}",
        )

    task_repo = SQLAlchemyTaskRepository(session)
    task = await task_repo.create(
        user_id=request.user_id,
        type=request.generation_type,
        status=TaskStatus.CREATED,
        prompt=request.prompt,
        params=request.params,
        cost=cost,
        callback_url=request.callback_url,
    )

    await charge_balance(session, request.user_id, cost, task.id)

    generation_requests_total.labels(type=request.generation_type.value, status="created").inc()
    generation_cost_total.labels(type=request.generation_type.value).inc(float(cost))

    logger.info(
        "Generation task created",
        extra={
            "task_id": str(task.id),
            "type": request.generation_type.value,
            "cost": str(cost),
        },
    )

    return {
        "task_id": str(task.id),
        "status": task.status.value,
        "type": request.generation_type.value,
        "cost": cost,
    }


async def handle_fal_webhook(session: AsyncSession, task_id: str, payload: dict[str, Any]) -> None:
    """Process incoming webhook from Fal.ai with generation results."""
    task_repo = SQLAlchemyTaskRepository(session)
    task = await task_repo.get_by_id(UUID(task_id))
    if task is None:
        logger.warning("Fal webhook for unknown task", extra={"task_id": task_id})
        return

    result_url = None
    result_metadata = payload

    if "video" in payload and isinstance(payload["video"], dict):
        result_url = payload["video"].get("url")
    elif "images" in payload and isinstance(payload["images"], list) and payload["images"]:
        result_url = payload["images"][0].get("url")

    error = payload.get("error")
    if error:
        await task_repo.update(
            task.id,
            status=TaskStatus.FAILED,
            error_message=str(error),
            result_metadata=result_metadata,
        )
        await refund_balance(session, task.user_id, task.cost, task.id)
        generation_requests_total.labels(type=task.type.value, status="failed").inc()
        logger.error("Generation failed via webhook", extra={"task_id": task_id, "error": error})
    else:
        await task_repo.update(
            task.id,
            status=TaskStatus.COMPLETED,
            result_url=result_url,
            result_metadata=result_metadata,
        )
        generation_requests_total.labels(type=task.type.value, status="completed").inc()
        logger.info(
            "Generation completed via webhook",
            extra={"task_id": task_id, "result_url": result_url},
        )

    if task.callback_url:
        from src.workers.webhook_tasks import deliver_webhook

        deliver_webhook.delay(str(task.id))
