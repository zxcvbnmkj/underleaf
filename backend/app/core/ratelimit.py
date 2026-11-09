"""基于 Redis 的简单限流：固定时间窗口内计数，超过上限返回 429。"""

from app.core.errors import AppError
from app.core.redis import redis

PREFIX = "underleaf:rate:"


async def rate_limit(
    key: str, max_count: int, window_seconds: int, message: str = "操作太频繁，请稍后再试"
) -> None:
    full_key = PREFIX + key
    count = await redis.incr(full_key)
    if count == 1:
        await redis.expire(full_key, window_seconds)
    if count > max_count:
        ttl = await redis.ttl(full_key)
        raise AppError(429, "too_many_requests", message, {"retryAfter": max(ttl, 1)})
