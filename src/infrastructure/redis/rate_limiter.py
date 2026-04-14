import logging
import time

import redis.asyncio as aioredis

from src.core.config import settings

logger = logging.getLogger(__name__)


class _RedisState:
    pool: aioredis.Redis | None = None


_state = _RedisState()


async def get_redis() -> aioredis.Redis:
    if _state.pool is None:
        _state.pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _state.pool


RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local block_key = KEYS[2]
local max_requests = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local block_duration = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

-- Check if user is blocked
local blocked_until = redis.call('GET', block_key)
if blocked_until and tonumber(blocked_until) > now then
    return {0, tonumber(blocked_until) - now}
end

-- Clean old entries outside the window
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current requests in window
local count = redis.call('ZCARD', key)

if count >= max_requests then
    -- Block the user
    local block_until = now + block_duration
    redis.call('SET', block_key, block_until, 'EX', block_duration)
    return {0, block_duration}
end

-- Add current request
redis.call('ZADD', key, now, now .. ':' .. math.random(1000000))
redis.call('EXPIRE', key, window)

return {1, max_requests - count - 1}
"""


async def check_rate_limit(user_id: str) -> tuple[bool, int]:
    """Check if user is within rate limit.

    Returns (allowed, remaining_or_retry_after).
    If allowed=True, second value is remaining requests.
    If allowed=False, second value is retry-after in seconds.
    """
    redis = await get_redis()
    key = f"rate_limit:{user_id}"
    block_key = f"rate_limit_block:{user_id}"
    now = time.time()

    result = await redis.eval(
        RATE_LIMIT_SCRIPT,
        2,
        key,
        block_key,
        settings.rate_limit_max_requests,
        settings.rate_limit_window_seconds,
        settings.rate_limit_block_seconds,
        now,
    )

    allowed = bool(result[0])
    value = int(result[1])
    return allowed, value
