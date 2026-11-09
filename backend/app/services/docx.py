"""Markdown → Word：调用 Pandoc（pypandoc-binary 自带，无需另外安装）。

- 输入格式与前端 markdown-it 对齐：GFM（表格、任务列表、删除线）+ $ / $$ 公式
- 公式转为 Word 原生公式（可在 Word 中编辑），代码块保留语法高亮
- Mermaid 图表由 Chromium 截图后插入（见 underleaf.lua）
- 图片：站内图片从磁盘读取，公网图片下载后插入（见 export_images.py）
- --sandbox：Pandoc 本身不读取任何本地文件、不访问网络，图片都由后端预先取好再交给它，
  避免正文中的 ![](/etc/passwd) 之类的地址读到服务器上的文件
"""

import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path

import pypandoc

from app.core.config import Settings
from app.core.errors import AppError
from app.services.browser import DiagramImage
from app.services.export_images import collect_image_urls, fetch_images, write_image_map

logger = logging.getLogger(__name__)

LUA_FILTER = Path(__file__).parent / "pandoc" / "underleaf.lua"
INPUT_FORMAT = "gfm+tex_math_dollars"

_MERMAID_FENCE = re.compile(r"^ {0,3}(```|~~~)\s*mermaid\b", re.MULTILINE)
_H1_AT_START = re.compile(r"^\s*#\s")


def has_mermaid(content: str) -> bool:
    return bool(_MERMAID_FENCE.search(content))


def _write_diagrams(directory: str, diagrams: list[DiagramImage | None]) -> None:
    for i, image in enumerate(diagrams):
        if image:
            Path(directory, f"mermaid-{i}.png").write_bytes(image.png)


class DocxConverter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pandoc = pypandoc.get_pandoc_path()
        self._slots = asyncio.Semaphore(settings.export_concurrency)

    async def convert(
        self, title: str, content: str, diagrams: list[DiagramImage | None] | None = None
    ) -> bytes:
        args = [
            "-f", INPUT_FORMAT, "-t", "docx", "-o", "-",
            "--sandbox",
            "--lua-filter", str(LUA_FILTER),
            "-M", "lang=zh-CN",
        ]  # fmt: skip
        # 第一遍：解析出正文中的图片地址，由后端取回
        ast = await self._run(
            ["-f", INPUT_FORMAT, "-t", "json", "--sandbox"], content, dict(os.environ)
        )
        images = await fetch_images(collect_image_urls(ast.decode()), self._settings)

        with tempfile.TemporaryDirectory(prefix="underleaf-docx-") as tmp:
            env = dict(os.environ)
            if images:
                map_file = await asyncio.to_thread(write_image_map, Path(tmp), images)
                env["UNDERLEAF_IMAGE_MAP"] = str(map_file)
            # 与网页一致：正文不以一级标题开头时，用笔记标题作为文档标题。
            # 不用 -M title=...：Pandoc 会按 YAML 解析，标题为 true / yes 等时会变成布尔值
            if not _H1_AT_START.match(content):
                env["UNDERLEAF_TITLE"] = title
            if diagrams:
                await asyncio.to_thread(_write_diagrams, tmp, diagrams)
                env["UNDERLEAF_MERMAID_DIR"] = tmp
                env["UNDERLEAF_MERMAID_WIDTHS"] = ",".join(
                    str(image.width if image else 0) for image in diagrams
                )
            return await self._run(args, content, env)

    async def _run(self, args: list[str], content: str, env: dict[str, str]) -> bytes:
        async with self._slots:
            proc = await asyncio.create_subprocess_exec(
                self._pandoc,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                async with asyncio.timeout(self._settings.export_timeout_seconds):
                    stdout, stderr = await proc.communicate(content.encode())
            except TimeoutError as e:
                proc.kill()
                await proc.wait()
                raise AppError(504, "export_timeout", "生成 Word 超时，请稍后重试") from e

        if proc.returncode != 0:
            logger.error("Pandoc 转换失败：%s", stderr.decode(errors="replace"))
            raise AppError(500, "export_failed", "生成 Word 失败，请稍后重试")
        if stderr:
            # 例如正文引用了外部图片：沙箱中不会下载，Pandoc 给出警告
            logger.info("Pandoc：%s", stderr.decode(errors="replace").strip())
        return stdout
