"""导出接口：参数校验、大小限制、文件名、Word 转换内容。

Chromium 用假的渲染器代替；Word 转换使用真实的 Pandoc（pypandoc-binary 自带）。
"""

import io
import struct
import zipfile
import zlib
from collections.abc import AsyncIterator
from urllib.parse import unquote

import httpx
import pytest

from app.api.deps import current_user
from app.api.v1.export import DOCX_MEDIA_TYPE, export_filename, get_renderer
from app.core.config import get_settings
from app.main import app
from app.services.browser import DiagramImage
from app.services.docx import has_mermaid
from tests.conftest import fake_user


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    raw = b"\x00\xff\x00\x00" * 1
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class FakeRenderer:
    def __init__(self) -> None:
        self.pdf_calls: list[tuple[str, str]] = []
        self.mermaid_calls = 0
        # 第二个图表模拟语法错误
        self.diagrams: list[DiagramImage | None] = [DiagramImage(tiny_png(), 320), None]

    async def pdf(self, title: str, content: str) -> bytes:
        self.pdf_calls.append((title, content))
        return b"%PDF-1.4 fake"

    async def mermaid_images(self, title: str, content: str) -> list[DiagramImage | None]:
        self.mermaid_calls += 1
        return self.diagrams


@pytest.fixture
async def client() -> AsyncIterator[tuple[httpx.AsyncClient, FakeRenderer]]:
    fake = FakeRenderer()
    app.dependency_overrides[get_renderer] = lambda: fake
    app.dependency_overrides[current_user] = lambda: fake_user()
    # 不经过 lifespan，手动准备 Word 转换器
    from app.services.docx import DocxConverter

    app.state.docx_converter = DocxConverter(get_settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, fake
    app.dependency_overrides.clear()


def docx_xml(data: bytes) -> tuple[str, list[str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        media = [n for n in z.namelist() if n.startswith("word/media/")]
        return z.read("word/document.xml").decode(), media


def docx_text(xml: str) -> str:
    """提取正文纯文本（Word 会把中英文拆成多个 run）。"""
    import html
    import re

    return html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)))


def filename_of(res: httpx.Response) -> str:
    return unquote(res.headers["content-disposition"].split("filename*=UTF-8''")[1])


# ---------- PDF ----------


async def test_export_pdf_returns_attachment(client: tuple[httpx.AsyncClient, FakeRenderer]):
    c, fake = client
    res = await c.post("/api/v1/export/pdf", json={"title": "读书笔记", "content": "# 你好"})

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    assert res.headers["content-disposition"].startswith("attachment;")
    assert filename_of(res) == "读书笔记.pdf"
    assert fake.pdf_calls == [("读书笔记", "# 你好")]


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
async def test_export_validates_title(client: tuple[httpx.AsyncClient, FakeRenderer], fmt: str):
    c, _ = client
    res = await c.post(f"/api/v1/export/{fmt}", json={"title": "", "content": "x"})
    assert res.status_code == 422
    assert res.json()["code"] == "validation_error"


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
async def test_export_rejects_large_content(
    client: tuple[httpx.AsyncClient, FakeRenderer], fmt: str
):
    c, fake = client
    too_large = "字" * (get_settings().export_max_content_bytes // 3 + 1)  # 每个汉字 3 字节
    res = await c.post(f"/api/v1/export/{fmt}", json={"title": "t", "content": too_large})

    assert res.status_code == 413
    assert res.json()["code"] == "content_too_large"
    assert fake.pdf_calls == []


# ---------- Word ----------

DOC = """# 标题

行内公式 $E = mc^2$。

$$
\\int_0^1 x\\,dx
$$

- [x] 完成
- [ ] 未完成

```python
print("hi")
```

<div>原始 HTML</div>

![外部图片](http://169.254.169.254/latest/meta-data)
"""


async def test_export_docx_content(client: tuple[httpx.AsyncClient, FakeRenderer]):
    c, fake = client
    res = await c.post("/api/v1/export/docx", json={"title": "笔记", "content": DOC})

    assert res.status_code == 200
    assert res.headers["content-type"] == DOCX_MEDIA_TYPE
    assert filename_of(res) == "笔记.docx"
    xml, media = docx_xml(res.content)
    assert "<m:oMath" in xml  # 公式转为 Word 原生公式
    assert "KeywordTok" in xml or "BuiltInTok" in xml  # 代码高亮
    assert "<div>原始 HTML</div>" in docx_text(xml)  # HTML 按文字保留，与网页一致
    assert "外部图片" in docx_text(xml) and media == []  # 沙箱：不下载外部图片，显示说明文字
    assert fake.mermaid_calls == 0  # 没有 Mermaid 时不启动 Chromium


async def test_export_docx_title_when_no_h1(client: tuple[httpx.AsyncClient, FakeRenderer]):
    c, _ = client
    res = await c.post("/api/v1/export/docx", json={"title": "true", "content": "正文"})
    xml, _ = docx_xml(res.content)
    assert 'w:val="Title"' in xml and "true" in docx_text(xml)  # 按纯文本处理，不会变成布尔值


async def test_export_docx_mermaid(client: tuple[httpx.AsyncClient, FakeRenderer]):
    c, fake = client
    content = "```mermaid\ngraph LR\nA-->B\n```\n\n```mermaid\n语法错误\n```\n"
    res = await c.post("/api/v1/export/docx", json={"title": "图", "content": content})

    xml, media = docx_xml(res.content)
    assert fake.mermaid_calls == 1
    assert len(media) == 1  # 第一个图表插入为图片
    assert "语法错误" in docx_text(xml)  # 渲染失败的图表保留为代码块
    assert "graph LR" not in docx_text(xml)


async def test_export_docx_mermaid_count_mismatch(client: tuple[httpx.AsyncClient, FakeRenderer]):
    """截图数量与代码块数量不一致时全部保留为代码块，避免图表错位。"""
    c, fake = client
    fake.diagrams = [DiagramImage(tiny_png(), 100)]
    content = "```mermaid\nA\n```\n\n```mermaid\nB\n```\n"
    res = await c.post("/api/v1/export/docx", json={"title": "图", "content": content})

    _, media = docx_xml(res.content)
    assert media == []


# ---------- 工具函数 ----------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("普通标题", "普通标题.pdf"),
        ('a/b\\c:d*e?f"g<h>i|j', "a_b_c_d_e_f_g_h_i_j.pdf"),
        ("  ..  ", "note.pdf"),
        ("末尾的点.", "末尾的点.pdf"),
    ],
)
def test_export_filename(title: str, expected: str) -> None:
    assert export_filename(title, "pdf") == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("```mermaid\ngraph LR\n```", True),
        ("文字\n\n~~~ mermaid\nx\n~~~", True),
        ("```python\nmermaid = 1\n```", False),
        ("提到 mermaid 这个词", False),
    ],
)
def test_has_mermaid(content: str, expected: bool) -> None:
    assert has_mermaid(content) is expected
