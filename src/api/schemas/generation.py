import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class TextToImageRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    negative_prompt: str | None = Field(None, max_length=500)
    num_images: int = Field(1, ge=1, le=4)
    image_size: str | dict[str, int] = Field("square")
    callback_url: str | None = None


class ImageToImageRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    image_urls: list[str] = Field(..., min_length=1, max_length=2)
    negative_prompt: str | None = Field(None, max_length=500)
    num_images: int = Field(1, ge=1, le=4)
    image_size: str | dict[str, int] = Field("square")
    callback_url: str | None = None


class TextToVideoRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=800)
    negative_prompt: str | None = Field(None, max_length=500)
    aspect_ratio: str = Field("16:9")
    resolution: str = Field("1080p")
    duration: str = Field("5")
    callback_url: str | None = None


class ImageToVideoRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=800)
    image_url: str = Field(..., min_length=1)
    negative_prompt: str | None = Field(None, max_length=500)
    resolution: str = Field("1080p")
    duration: str = Field("5")
    callback_url: str | None = None


class GenerationTaskResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    type: str
    cost: Decimal

    model_config = {"from_attributes": True}


class TaskStatusResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    type: str
    prompt: str
    cost: Decimal
    result_url: str | None = None
    result_metadata: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    items: list[TaskStatusResponse]
