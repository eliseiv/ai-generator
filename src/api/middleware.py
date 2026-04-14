import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.core.security import hash_api_key
from src.infrastructure.metrics import api_requests_total
from src.infrastructure.redis.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)

RATE_LIMIT_EXEMPT_PREFIXES = ("/auth", "/webhooks", "/health", "/metrics", "/docs", "/openapi.json")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.monotonic()

        logger.info(
            "Incoming request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )

        # Rate limiting
        if not any(request.url.path.startswith(p) for p in RATE_LIMIT_EXEMPT_PREFIXES):
            api_key = request.headers.get("x-api-key")
            if api_key:
                user_key = hash_api_key(api_key)
                try:
                    allowed, value = await check_rate_limit(user_key)
                    if not allowed:
                        logger.warning(
                            "Rate limit exceeded",
                            extra={"request_id": request_id, "retry_after": value},
                        )
                        return JSONResponse(
                            status_code=429,
                            content={
                                "detail": f"Rate limit exceeded. Retry after {value} seconds."
                            },
                            headers={"Retry-After": str(value)},
                        )
                except (ConnectionError, OSError, TimeoutError) as e:
                    logger.error("Rate limiter error: %s", e)

        response: Response = await call_next(request)

        duration = time.monotonic() - start_time
        api_requests_total.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
        ).inc()

        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_s": round(duration, 4),
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
