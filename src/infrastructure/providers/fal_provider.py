import logging
import os
from typing import Any

import fal_client

from src.core.config import settings
from src.domain.interfaces.generation_provider import GenerationProvider, GenerationResult
from src.infrastructure.database.models import GenerationType

logger = logging.getLogger(__name__)

FAL_MODEL_MAP: dict[str, str] = {
    GenerationType.TEXT_TO_IMAGE: "fal-ai/wan-25-preview/text-to-image",
    GenerationType.IMAGE_TO_IMAGE: "fal-ai/wan-25-preview/image-to-image",
    GenerationType.TEXT_TO_VIDEO: "fal-ai/wan-25-preview/text-to-video",
    GenerationType.IMAGE_TO_VIDEO: "fal-ai/wan-25-preview/image-to-video",
}


class FalProvider(GenerationProvider):
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or settings.fal_key

    def _apply_key(self) -> None:
        os.environ["FAL_KEY"] = self._api_key

    @staticmethod
    def _get_model_id(generation_type: str) -> str:
        model_id = FAL_MODEL_MAP.get(generation_type)
        if not model_id:
            raise ValueError(f"Unknown generation type: {generation_type}")
        return model_id

    @staticmethod
    def _build_arguments(
        generation_type: str, prompt: str, params: dict[str, Any] | None
    ) -> dict[str, Any]:
        args: dict[str, Any] = {"prompt": prompt}
        if params:
            args.update(params)
        args.setdefault("enable_safety_checker", True)
        return args

    async def submit(
        self,
        generation_type: str,
        prompt: str,
        params: dict[str, Any] | None = None,
        webhook_url: str | None = None,
    ) -> str:
        self._apply_key()
        model_id = self._get_model_id(generation_type)
        arguments = self._build_arguments(generation_type, prompt, params)

        logger.info(
            "Submitting to Fal.ai",
            extra={"model_id": model_id, "prompt": prompt[:100]},
        )

        kwargs: dict[str, Any] = {
            "arguments": arguments,
        }
        if webhook_url:
            kwargs["webhook_url"] = webhook_url

        handler = await fal_client.submit_async(model_id, **kwargs)
        request_id = handler.request_id

        logger.info("Fal.ai request submitted", extra={"request_id": request_id})
        return request_id

    async def get_status(self, generation_type: str, request_id: str) -> GenerationResult:
        self._apply_key()
        model_id = self._get_model_id(generation_type)
        status_obj = await fal_client.status_async(model_id, request_id, with_logs=True)

        status_str = "processing"
        if hasattr(status_obj, "status"):
            status_str = str(status_obj.status).lower()

        return GenerationResult(
            request_id=request_id,
            status=status_str,
        )

    async def get_result(self, generation_type: str, request_id: str) -> GenerationResult:
        self._apply_key()
        model_id = self._get_model_id(generation_type)
        result = await fal_client.result_async(model_id, request_id)

        result_url = None
        result_metadata = {}

        if isinstance(result, dict):
            if "video" in result and isinstance(result["video"], dict):
                result_url = result["video"].get("url")
                result_metadata = result["video"]
            elif "images" in result and isinstance(result["images"], list) and result["images"]:
                result_url = result["images"][0].get("url")
                result_metadata = {"images": result["images"]}

            if "seed" in result:
                result_metadata["seed"] = result["seed"]
            if "seeds" in result:
                result_metadata["seeds"] = result["seeds"]
            if "actual_prompt" in result:
                result_metadata["actual_prompt"] = result["actual_prompt"]

        return GenerationResult(
            request_id=request_id,
            status="completed",
            result_url=result_url,
            result_metadata=result_metadata,
        )
