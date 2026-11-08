"""测试需要一个专用的 MySQL 库（会被清空重建），通过环境变量 TEST_DATABASE_URL 指定。

    TEST_DATABASE_URL=mysql+aiomysql://root@127.0.0.1:3306/underleaf_test pdm test

未设置时跳过所有依赖数据库的测试。
"""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import create_engine
from app.models import Base

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
