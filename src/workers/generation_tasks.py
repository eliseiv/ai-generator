import asyncio
import logging
import time
from uuid import UUID

from celery import shared_task

from src.core.config import settings
from src.infrastructure.database.models import GenerationType, TaskStatus
from src.infrastructure.metrics import (
    generation_duration_seconds,
    generation_errors_total,
    generation_requests_total,
)

logger = logging.getLogger(__name__)


def _get_provider():
    from src.infrastructure.providers.fal_provider import FalProvider
    from src.infrastructure.providers.fallback import FallbackProvider

    primary = FalProvider(api_key=settings.fal_key)
    fallback_key = settings.fal_key_fallback or settings.fal_key
    fallback = FalProvider(api_key=fallback_key)
    return FallbackProvider(primary, fallback)


async def _submit_to_provider(task_id: str) -> None:
    from src.infrastructure.database.repositories.task_repo import SQLAlchemyTaskRepository
    from src.infrastructure.database.session import get_session_factory
    from src.services.balance_service import refund_balance

    provider = _get_provider()
    factory = get_session_factory()

    async with factory() as session:
        task_repo = SQLAlchemyTaskRepository(session)
        task = await task_repo.get_by_id(UUID(task_id))
        if task is None:
            logger.error("Task not found for submission", extra={"task_id": task_id})
            return

        await task_repo.update(task.id, status=TaskStatus.QUEUED)
        await session.commit()

        generation_type = task.type.value if isinstance(task.type, GenerationType) else task.type
        webhook_url = f"{settings.fal_webhook_base_url}/webhooks/fal/{task_id}"

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                fal_request_id = await provider.submit(
                    generation_type=generation_type,
                    prompt=task.prompt,
                    params=task.params,
                    webhook_url=webhook_url,
                )
                await task_repo.update(
                    task.id,
                    status=TaskStatus.PROCESSING,
                    fal_request_id=fal_request_id,
                )
                await session.commit()

                generation_requests_total.labels(type=generation_type, status="processing").inc()
                logger.info(
                    "Task submitted to Fal.ai",
                    extra={
                        "task_id": task_id,
                        "fal_request_id": fal_request_id,
                        "attempt": attempt,
                    },
                )
                return
            except (OSError, ValueError, RuntimeError) as e:
                logger.error(
                    "Failed to submit to Fal.ai",
                    extra={"task_id": task_id, "attempt": attempt, "error": str(e)},
                )
                if attempt == max_retries:
                    await task_repo.update(
                        task.id,
                        status=TaskStatus.FAILED,
                        error_message=f"Failed to submit after {max_retries} retries: {e}",
                    )
                    await refund_balance(session, task.user_id, task.cost, task.id)
                    await session.commit()

                    generation_errors_total.labels(
                        type=generation_type, error_type="submit_failed"
                    ).inc()
                    return
                await asyncio.sleep(2**attempt)


@shared_task(name="generation.submit")
def submit_generation(task_id: str) -> None:
    asyncio.run(_submit_to_provider(task_id))


async def _poll_task_status(task_id: str) -> None:
    """Fallback: poll Fal.ai for task status if webhook wasn't received."""
    from src.infrastructure.database.repositories.task_repo import SQLAlchemyTaskRepository
    from src.infrastructure.database.session import get_session_factory
    from src.services.balance_service import refund_balance

    provider = _get_provider()
    factory = get_session_factory()

    async with factory() as session:
        task_repo = SQLAlchemyTaskRepository(session)
        task = await task_repo.get_by_id(UUID(task_id))
        if task is None:
            return

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return

        if not task.fal_request_id:
            return

        generation_type = task.type.value if isinstance(task.type, GenerationType) else task.type
        start = time.monotonic()

        try:
            result = await provider.get_result(generation_type, task.fal_request_id)

            if result.status == "completed" and result.result_url:
                elapsed = time.monotonic() - start
                await task_repo.update(
                    task.id,
                    status=TaskStatus.COMPLETED,
                    result_url=result.result_url,
                    result_metadata=result.result_metadata,
                )
                await session.commit()
                generation_duration_seconds.labels(type=generation_type).observe(elapsed)

                if task.callback_url:
                    from src.workers.webhook_tasks import deliver_webhook

                    deliver_webhook.delay(str(task.id))
            elif result.error:
                await task_repo.update(
                    task.id,
                    status=TaskStatus.FAILED,
                    error_message=result.error,
                )
                await refund_balance(session, task.user_id, task.cost, task.id)
                await session.commit()
                generation_errors_total.labels(
                    type=generation_type, error_type="generation_failed"
                ).inc()
        except (OSError, ValueError, RuntimeError) as e:
            logger.warning(
                "Poll status failed (task may still be processing)",
                extra={"task_id": task_id, "error": str(e)},
            )


@shared_task(name="generation.poll_status")
def poll_task_status(task_id: str) -> None:
    asyncio.run(_poll_task_status(task_id))
