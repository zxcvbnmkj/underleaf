from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.core.db import engine
from app.core.redis import redis


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await redis.aclose()
    await engine.dispose()


app = FastAPI(
    title="Underleaf",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.get("/api/v1/health", tags=["system"])
async def health() -> dict[str, str]:
    """检查数据库和 Redis 是否可用。"""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await redis.ping()  # pyright: ignore[reportGeneralTypeIssues]
    return {"status": "ok"}
