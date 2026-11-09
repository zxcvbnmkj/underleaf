"""无头 Chromium：打开前端渲染页，生成 PDF，或截取 Mermaid 图表。

排版完全复用前端（MarkdownPreview + markdown.css），后端不参与渲染，因此预览、PDF、
Word 中的图表始终一致。渲染页的约定见 frontend/src/views/ExportRenderView.vue：
- 页面加载前，内容通过 window.__UNDERLEAF_EXPORT__ = { title, content } 注入
- 渲染（含 Mermaid、字体）全部完成后，<html data-export-ready="true">；失败为 "error"
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from playwright.async_api import Browser, Page, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError

from app.core.config import Settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

RENDER_PATH = "/export/render"


@dataclass
class DiagramImage:
    png: bytes
    # 页面上的显示宽度（CSS 像素），Word 中按此宽度插入
    width: int


class ChromiumRenderer:
    """进程内共享一个 Chromium，首次使用时启动；每次任务使用独立的浏览器上下文。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._launch_lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(settings.export_concurrency)

    async def pdf(self, title: str, content: str) -> bytes:
        async with self._task("生成 PDF"), self._render_page(title, content) as page:
            # 纸张大小和页边距由 markdown.css 中的 @page 决定
            return await page.pdf(prefer_css_page_size=True, print_background=True)

    async def mermaid_images(self, title: str, content: str) -> list[DiagramImage | None]:
        """按文档顺序截取每个 Mermaid 图表；渲染失败（语法错误等）的位置为 None。"""
        async with (
            self._task("渲染图表"),
            self._render_page(title, content, scale=2) as page,
        ):
            images: list[DiagramImage | None] = []
            for block in await page.query_selector_all(".markdown-body pre.mermaid"):
                svg = await block.query_selector("svg")
                box = await svg.bounding_box() if svg else None
                if svg is None or box is None:
                    images.append(None)
                    continue
                png = await svg.screenshot(type="png")
                images.append(DiagramImage(png=png, width=round(box["width"])))
            return images

    @asynccontextmanager
    async def _task(self, action: str) -> AsyncIterator[None]:
        """限制并发数和总耗时（含排队），并把底层错误转换为用户能看懂的提示。"""
        try:
            async with asyncio.timeout(self._settings.export_timeout_seconds), self._slots:
                yield
        except TimeoutError as e:
            raise AppError(504, "export_timeout", f"{action}超时，请稍后重试") from e
        except PlaywrightError as e:
            logger.exception("%s失败", action)
            raise AppError(500, "export_failed", f"{action}失败，请稍后重试") from e

    @asynccontextmanager
    async def _render_page(self, title: str, content: str, scale: float = 1) -> AsyncIterator[Page]:
        browser = await self._get_browser()
        context = await browser.new_context(locale="zh-CN", device_scale_factor=scale)
        try:
            page = await context.new_page()
            # json.dumps 默认转义非 ASCII 字符，结果可以安全地嵌入 JS
            payload = json.dumps({"title": title, "content": content})
            await page.add_init_script(script=f"window.__UNDERLEAF_EXPORT__ = {payload};")
            await page.goto(
                self._settings.export_render_url.rstrip("/") + RENDER_PATH,
                wait_until="domcontentloaded",
            )
            await page.wait_for_function(
                "() => document.documentElement.dataset.exportReady", timeout=0
            )
            state = await page.evaluate("() => document.documentElement.dataset.exportReady")
            if state != "true":
                raise AppError(500, "export_render_failed", "渲染笔记失败，无法导出")
            yield page
        finally:
            await context.close()

    async def _get_browser(self) -> Browser:
        async with self._launch_lock:
            if self._browser and self._browser.is_connected():
                return self._browser
            # 首次启动，或 Chromium 意外退出后重新启动
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                channel=self._settings.export_browser_channel or None,
                # 服务器 /dev/shm 较小时 Chromium 容易崩溃，改用 /tmp
                args=["--disable-dev-shm-usage"],
            )
            logger.info("Chromium 已启动")
            return self._browser

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
