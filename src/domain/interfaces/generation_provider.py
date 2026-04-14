from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class GenerationResult:
    request_id: str
    status: str
    result_url: str | None = None
    result_metadata: dict[str, Any] | None = None
    error: str | None = None


class GenerationProvider(ABC):
    @abstractmethod
    async def submit(
        self,
        generation_type: str,
        prompt: str,
        params: dict[str, Any] | None = None,
        webhook_url: str | None = None,
    ) -> str:
        """Submit a generation request. Returns external request_id."""

    @abstractmethod
    async def get_status(self, generation_type: str, request_id: str) -> GenerationResult:
        """Check the status of a generation request."""

    @abstractmethod
    async def get_result(self, generation_type: str, request_id: str) -> GenerationResult:
        """Fetch the result of a completed generation."""
