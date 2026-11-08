from redis.asyncio import Redis

from app.core.config import get_settings

# 存放验证码、发送冷却等短期数据，依靠 TTL 自动过期
redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
