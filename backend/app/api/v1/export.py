"""导出：前端传入编辑器中当前的标题和正文（无需先保存），返回 PDF / Word 文件。"""

import re
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.schemas.base import Schema
from app.services.browser import ChromiumRenderer
from app.services.docx import DocxConverter, has_mermaid

router = APIRouter(prefix="/export", tags=["export"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# 文件名中不允许出现的字符（Windows 最严格），以及控制字符
_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class ExportRequest(Schema):
    title: str = Field(min_length=1, max_length=255)
    # 大小上限在接口中按字节校验（max_length 按字符计算）
    content: str


def get_renderer(request: Request) -> ChromiumRenderer:
    return request.app.state.renderer


def get_docx_converter(request: Request) -> DocxConverter:
    return request.app.state.docx_converter


def export_filename(title: str, ext: str) -> str:
    name = _ILLEGAL_FILENAME_CHARS.sub("_", title).strip(" .") or "note"
    return f"{name}.{ext}"


def content_disposition(filename: str) -> str:
    """filename* 携带 UTF-8 编码的中文文件名，filename 为不支持它的旧客户端兜底。"""
    ext = filename.rsplit(".", 1)[-1]
    return f"attachment; filename=\"note.{ext}\"; filename*=UTF-8''{quote(filename)}"


async def check_export(user_id: int, content: str) -> None:
    # 生成 PDF / Word 较耗资源，每人每分钟最多 20 次
    await rate_limit(f"export:{user_id}", 20, 60, "导出太频繁，请稍后再试")
    check_size(content)


def check_size(content: str) -> None:
    limit = get_settings().export_max_content_bytes
    if len(content.encode()) > limit:
        raise AppError(
            413, "content_too_large", f"笔记内容超过 {limit // 1024 // 1024}MB，无法导出"
        )


def file_response(data: bytes, media_type: str, title: str, ext: str) -> Response:
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": content_disposition(export_filename(title, ext))},
    )


@router.post(
    "/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF 文件"}},
)
async def export_pdf(
    body: ExportRequest,
    user: CurrentUser,
    renderer: Annotated[ChromiumRenderer, Depends(get_renderer)],
) -> Response:
    """导出为 PDF：由无头 Chromium 打印前端渲染页，排版与预览一致。"""
    await check_export(user.id, body.content)
    pdf = await renderer.pdf(body.title, body.content)
    return file_response(pdf, "application/pdf", body.title, "pdf")


@router.post(
    "/docx",
    response_class=Response,
    responses={200: {"content": {DOCX_MEDIA_TYPE: {}}, "description": "Word 文件"}},
)
async def export_docx(
    body: ExportRequest,
    user: CurrentUser,
    converter: Annotated[DocxConverter, Depends(get_docx_converter)],
    renderer: Annotated[ChromiumRenderer, Depends(get_renderer)],
) -> Response:
    """导出为 Word：Pandoc 转换，公式为 Word 原生公式；Mermaid 图表由 Chromium 截图后插入。"""
    await check_export(user.id, body.content)
    # 只有包含 Mermaid 时才需要启动 Chromium
    diagrams = (
        await renderer.mermaid_images(body.title, body.content)
        if has_mermaid(body.content)
        else None
    )
    docx = await converter.convert(body.title, body.content, diagrams)
    return file_response(docx, DOCX_MEDIA_TYPE, body.title, "docx")
