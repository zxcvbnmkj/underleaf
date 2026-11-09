"""测试需要一个专用的 MySQL 库（会被清空重建），通过环境变量 TEST_DATABASE_URL 指定。

    TEST_DATABASE_URL=mysql+aiomysql://root@127.0.0.1:3306/underleaf_test pdm test

未设置时跳过所有依赖数据库的测试。
"""

import os
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.db import create_engine, get_session
from app.core.redis import redis
from app.core.security import create_token
from app.main import app
from app.models import Base, User

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    if not TEST_DATABASE_URL:
        pytest.skip("未设置 TEST_DATABASE_URL")
    eng = create_engine(TEST_DATABASE_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """每个测试结束后清空所有表，测试之间互不影响。"""
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture(autouse=True)
async def clean_redis() -> AsyncIterator[None]:
    """清除限流计数和验证码，避免测试之间互相影响（使用 .env 中 REDIS_URL 指向的本地 Redis）。"""

    async def clear() -> None:
        for pattern in ("underleaf:rate:*", "underleaf:code:*", "underleaf:code-cooldown:*"):
            keys = [k async for k in redis.scan_iter(pattern)]
            if keys:
                await redis.delete(*keys)

    await clear()
    yield
    await clear()


def fake_user(user_id: int = 1) -> User:
    """不经过数据库的登录用户，用于只关心业务逻辑的接口测试。"""
    return User(id=user_id, email="tester@example.com", nickname="tester", password_hash="x")


@pytest.fixture
async def api(engine: AsyncEngine, session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    """接口客户端：数据库使用测试库（session 夹具负责在测试结束后清空数据）。"""
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def test_session() -> AsyncIterator[AsyncSession]:
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = test_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def login_as(
    client: httpx.AsyncClient, session: AsyncSession, nickname: str = "alice"
) -> User:
    """直接在数据库中创建用户，并把登录 Cookie 设置到客户端上（跳过注册流程）。"""
    user = User(email=f"{nickname}@example.com", nickname=nickname, password_hash="x")
    session.add(user)
    await session.commit()
    client.cookies.set(get_settings().session_cookie, create_token(user.id, user.token_version))
    return user
