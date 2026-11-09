"""图片上传。请求体直接是图片的二进制内容（不用 multipart），返回站内地址。"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.models import Image
from app.schemas.base import Schema
from app.services.images import detect_image, new_image_path, save_file, url_for

router = APIRouter(prefix="/images", tags=["images"])


class ImageOut(Schema):
    url: str
    mime: str
    size: int


async def read_limited(request: Request, limit: int) -> bytes:
    """读取请求体，超过 limit 时立即中止，避免大文件占满内存。"""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise _too_large(limit)
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise _too_large(limit)
        chunks.append(chunk)
    return b"".join(chunks)


def _too_large(limit: int) -> AppError:
    return AppError(413, "image_too_large", f"图片不能超过 {limit // 1024 // 1024}MB")


@router.post(
    "",
    response_model=ImageOut,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"image/*": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def upload_image(
    request: Request,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ImageOut:
    """上传一张图片（PNG / JPEG / GIF / WebP），请求体为图片的二进制内容。"""
    await rate_limit(f"upload:{user.id}", 60, 60, "上传太频繁，请稍后再试")
    settings = get_settings()
    data = await read_limited(request, settings.upload_max_bytes)
    if not data:
        raise AppError(422, "image_empty", "没有收到图片内容")
    detected = detect_image(data)
    if detected is None:
        raise AppError(415, "image_unsupported", "只支持 PNG、JPG、GIF、WebP 格式的图片")
    mime, ext = detected

    path = new_image_path(ext)
    await asyncio.to_thread(save_file, settings.upload_dir, path, data)
    session.add(Image(user_id=user.id, path=path, mime=mime, size=len(data)))
    await session.commit()
    return ImageOut(url=url_for(path), mime=mime, size=len(data))
