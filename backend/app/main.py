from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1 import auth, export, folders, git, images, notes, tokens
from app.core.config import get_settings
from app.core.db import engine
from app.core.errors import register_error_handlers
from app.core.redis import redis
from app.services.browser import ChromiumRenderer
from app.services.docx import DocxConverter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # Chromium 在首次导出时才启动，不导出就不占内存
    app.state.renderer = ChromiumRenderer(settings)
    app.state.docx_converter = DocxConverter(settings)
    yield
    await app.state.renderer.close()
    await redis.aclose()
    await engine.dispose()


app = FastAPI(
    title="Underleaf",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
register_error_handlers(app)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(folders.router, prefix="/api/v1")
app.include_router(notes.router, prefix="/api/v1")
app.include_router(notes.share_router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(images.router, prefix="/api/v1")
app.include_router(tokens.router, prefix="/api/v1")
app.include_router(git.router, prefix="/api/v1")

# 上传的图片。服务器上由 Nginx 直接提供 /uploads/（更快），这里主要供本地开发使用
_upload_dir = get_settings().upload_dir
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_upload_dir), name="uploads")


@app.get("/api/v1/health", tags=["system"])
async def health() -> dict[str, str]:
    """检查数据库和 Redis 是否可用。"""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await redis.ping()  # pyright: ignore[reportGeneralTypeIssues]
    return {"status": "ok"}
