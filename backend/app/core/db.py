from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def build_database_url(raw: str) -> URL:
    """统一使用 utf8mb4，否则 emoji 等 4 字节字符无法存储。"""
    return make_url(raw).update_query_dict({"charset": "utf8mb4"})


def create_engine(raw_url: str, **kwargs: Any) -> AsyncEngine:
    """应用和 Alembic 共用的引擎配置。"""
    kwargs.setdefault("pool_pre_ping", True)
    # MySQL 默认 8 小时断开空闲连接，提前回收
    kwargs.setdefault("pool_recycle", 3600)
    return create_async_engine(
        build_database_url(raw_url),
        # 会话时区固定为 UTC：CURRENT_TIMESTAMP 生成的时间与服务器所在时区无关
        connect_args={"init_command": "SET time_zone = '+00:00'"},
        **kwargs,
    )


_settings = get_settings()
engine = create_engine(_settings.database_url, echo=_settings.database_echo)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每个请求一个会话。"""
    async with SessionLocal() as session:
        yield session
