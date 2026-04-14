import logging
import time
from typing import Any

from src.core.config import settings
from src.domain.interfaces.generation_provider import GenerationProvider, GenerationResult

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Simple circuit breaker: tracks consecutive failures and switches state."""

    def __init__(
        self,
        failure_threshold: int = settings.circuit_breaker_failure_threshold,
        recovery_timeout: int = settings.circuit_breaker_recovery_timeout,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._is_open = False

    @property
    def is_open(self) -> bool:
        if self._is_open and self._last_failure_time:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                logger.info("Circuit breaker half-open, allowing probe request")
                self._is_open = False
                self._failure_count = 0
                return False
        return self._is_open

    def record_success(self) -> None:
        self._failure_count = 0
        self._is_open = False

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._is_open = True
            logger.warning(
                "Circuit breaker OPEN after %d consecutive failures",
                self._failure_count,
            )


class FallbackProvider(GenerationProvider):
    """Wraps a primary and fallback provider with circuit breaker logic."""

    def __init__(
        self,
        primary: GenerationProvider,
        fallback: GenerationProvider,
    ):
        self.primary = primary
        self.fallback = fallback
        self.circuit_breaker = CircuitBreaker()

    def _active_provider(self) -> GenerationProvider:
        if self.circuit_breaker.is_open:
            logger.info("Using fallback provider (circuit breaker open)")
            return self.fallback
        return self.primary

    async def submit(
        self,
        generation_type: str,
        prompt: str,
        params: dict[str, Any] | None = None,
        webhook_url: str | None = None,
    ) -> str:
        provider = self._active_provider()
        try:
            result = await provider.submit(generation_type, prompt, params, webhook_url)
            self.circuit_breaker.record_success()
            return result
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error("Provider submit failed: %s", e)
            if provider is self.primary and self.circuit_breaker.is_open:
                logger.info("Retrying with fallback provider")
                return await self.fallback.submit(generation_type, prompt, params, webhook_url)
            raise

    async def get_status(self, generation_type: str, request_id: str) -> GenerationResult:
        provider = self._active_provider()
        return await provider.get_status(generation_type, request_id)

    async def get_result(self, generation_type: str, request_id: str) -> GenerationResult:
        provider = self._active_provider()
        return await provider.get_result(generation_type, request_id)
