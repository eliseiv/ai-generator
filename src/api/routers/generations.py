import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from src.api.dependencies import CurrentUser, DBSession
from src.api.schemas.generation import (
    GenerationTaskResponse,
    ImageToImageRequest,
    ImageToVideoRequest,
    TaskListResponse,
    TaskStatusResponse,
    TextToImageRequest,
    TextToVideoRequest,
)
from src.core.config import settings
from src.infrastructure.database.models import GenerationType
from src.infrastructure.database.repositories.task_repo import SQLAlchemyTaskRepository
from src.services.generation_service import GenerationRequest, create_generation_task
from src.workers.generation_tasks import submit_generation


def _dispatch_generation(task_id: str) -> None:
    if not settings.dry_run:
        submit_generation.delay(task_id)


logger = logging.getLogger(__name__)
router = APIRouter()


def _task_to_status_response(task) -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=task.id,
        status=task.status.value if hasattr(task.status, "value") else task.status,
        type=task.type.value if hasattr(task.type, "value") else task.type,
        prompt=task.prompt,
        cost=task.cost,
        result_url=task.result_url,
        result_metadata=task.result_metadata,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _build_response(result: dict) -> GenerationTaskResponse:
    return GenerationTaskResponse(
        task_id=UUID(result["task_id"]),
        status=result["status"],
        type=result["type"],
        cost=result["cost"],
    )


@router.post(
    "/text-to-image",
    response_model=GenerationTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_text_to_image(body: TextToImageRequest, user: CurrentUser, session: DBSession):
    params = {
        "negative_prompt": body.negative_prompt,
        "num_images": body.num_images,
        "image_size": body.image_size,
    }
    params = {k: v for k, v in params.items() if v is not None}

    result = await create_generation_task(
        session,
        GenerationRequest(
            user_id=user.id,
            generation_type=GenerationType.TEXT_TO_IMAGE,
            prompt=body.prompt,
            params=params,
            callback_url=body.callback_url,
        ),
    )
    _dispatch_generation(result["task_id"])
    return _build_response(result)


@router.post(
    "/image-to-image",
    response_model=GenerationTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_image_to_image(body: ImageToImageRequest, user: CurrentUser, session: DBSession):
    params = {
        "image_urls": body.image_urls,
        "negative_prompt": body.negative_prompt,
        "num_images": body.num_images,
        "image_size": body.image_size,
    }
    params = {k: v for k, v in params.items() if v is not None}

    result = await create_generation_task(
        session,
        GenerationRequest(
            user_id=user.id,
            generation_type=GenerationType.IMAGE_TO_IMAGE,
            prompt=body.prompt,
            params=params,
            callback_url=body.callback_url,
        ),
    )
    _dispatch_generation(result["task_id"])
    return _build_response(result)


@router.post(
    "/text-to-video",
    response_model=GenerationTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_text_to_video(body: TextToVideoRequest, user: CurrentUser, session: DBSession):
    params = {
        "negative_prompt": body.negative_prompt,
        "aspect_ratio": body.aspect_ratio,
        "resolution": body.resolution,
        "duration": body.duration,
    }
    params = {k: v for k, v in params.items() if v is not None}

    result = await create_generation_task(
        session,
        GenerationRequest(
            user_id=user.id,
            generation_type=GenerationType.TEXT_TO_VIDEO,
            prompt=body.prompt,
            params=params,
            callback_url=body.callback_url,
        ),
    )
    _dispatch_generation(result["task_id"])
    return _build_response(result)


@router.post(
    "/image-to-video",
    response_model=GenerationTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_image_to_video(body: ImageToVideoRequest, user: CurrentUser, session: DBSession):
    params = {
        "image_url": body.image_url,
        "negative_prompt": body.negative_prompt,
        "resolution": body.resolution,
        "duration": body.duration,
    }
    params = {k: v for k, v in params.items() if v is not None}

    result = await create_generation_task(
        session,
        GenerationRequest(
            user_id=user.id,
            generation_type=GenerationType.IMAGE_TO_VIDEO,
            prompt=body.prompt,
            params=params,
            callback_url=body.callback_url,
        ),
    )
    _dispatch_generation(result["task_id"])
    return _build_response(result)


@router.get("", response_model=TaskListResponse)
async def list_generations(
    user: CurrentUser,
    session: DBSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    task_repo = SQLAlchemyTaskRepository(session)
    tasks = await task_repo.list_by_user(user.id, offset=offset, limit=limit)
    return TaskListResponse(items=[_task_to_status_response(t) for t in tasks])


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_generation_status(task_id: UUID, user: CurrentUser, session: DBSession):
    task_repo = SQLAlchemyTaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return _task_to_status_response(task)


@router.get("/{task_id}/download")
async def download_result(task_id: UUID, user: CurrentUser, session: DBSession):
    task_repo = SQLAlchemyTaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    if not task.result_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not available yet.",
        )

    async def _stream():
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:  # noqa: SIM117
            async with client.stream("GET", task.result_url) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    yield chunk

    content_type = "application/octet-stream"
    if task.result_metadata:
        ct = task.result_metadata.get("content_type")
        if ct:
            content_type = ct
        elif "images" in task.result_metadata:
            content_type = "image/png"
    elif task.type in (GenerationType.TEXT_TO_VIDEO, GenerationType.IMAGE_TO_VIDEO):
        content_type = "video/mp4"
    elif task.type in (GenerationType.TEXT_TO_IMAGE, GenerationType.IMAGE_TO_IMAGE):
        content_type = "image/png"

    ext = "mp4" if "video" in content_type else "png"
    filename = f"generation_{task_id}.{ext}"

    return StreamingResponse(
        _stream(),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
