"""图片上传，以及导出 Word 时图片的处理。"""

import io
import threading
import zipfile
from collections.abc import AsyncIterator, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.services import export_images
from app.services.docx import DocxConverter
from app.services.images import detect_image, local_path_for_url
from tests.conftest import fake_user
from tests.test_export import tiny_png

GIF = b"GIF89a" + b"\x00" * 20


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        pass


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    return tmp_path


@pytest.fixture
async def client(upload_dir: Path) -> AsyncIterator[tuple[httpx.AsyncClient, FakeSession]]:
    session = FakeSession()

    async def fake_session() -> AsyncIterator[FakeSession]:
        yield session

    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[current_user] = lambda: fake_user()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, session
    app.dependency_overrides.clear()


# ---------- 上传 ----------


async def test_upload_png(client: tuple[httpx.AsyncClient, FakeSession], upload_dir: Path):
    c, session = client
    res = await c.post("/api/v1/images", content=tiny_png(), headers={"Content-Type": "image/png"})

    assert res.status_code == 200
    body = res.json()
    assert body["url"].startswith("/uploads/images/") and body["url"].endswith(".png")
    assert body["mime"] == "image/png"
    saved = upload_dir / body["url"].removeprefix("/uploads/")
    assert saved.read_bytes() == tiny_png()
    assert len(session.added) == 1


async def test_upload_checks_content_not_header(client: tuple[httpx.AsyncClient, FakeSession]):
    """按文件头判断格式：声称是 PNG 的 SVG 会被拒绝。"""
    c, session = client
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    res = await c.post("/api/v1/images", content=svg, headers={"Content-Type": "image/png"})
    assert res.status_code == 415
    assert res.json()["code"] == "image_unsupported"
    assert session.added == []


async def test_upload_too_large(
    client: tuple[httpx.AsyncClient, FakeSession], monkeypatch: pytest.MonkeyPatch
):
    c, _ = client
    monkeypatch.setattr(get_settings(), "upload_max_bytes", 100)
    res = await c.post("/api/v1/images", content=tiny_png() + b"\x00" * 200)
    assert res.status_code == 413


async def test_upload_empty(client: tuple[httpx.AsyncClient, FakeSession]):
    c, _ = client
    res = await c.post("/api/v1/images", content=b"")
    assert res.status_code == 422


def test_detect_image() -> None:
    assert detect_image(tiny_png()) == ("image/png", "png")
    assert detect_image(b"\xff\xd8\xff\xe0" + b"\x00" * 10) == ("image/jpeg", "jpg")
    assert detect_image(GIF) == ("image/gif", "gif")
    assert detect_image(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ("image/webp", "webp")
    assert detect_image(b"<svg></svg>") is None


def test_local_path_cannot_escape_upload_dir(upload_dir: Path) -> None:
    (upload_dir / "images").mkdir()
    (upload_dir / "images" / "a.png").write_bytes(tiny_png())
    (upload_dir.parent / "secret.txt").write_text("secret")

    assert local_path_for_url(upload_dir, "/uploads/images/a.png") is not None
    assert local_path_for_url(upload_dir, "/uploads/../secret.txt") is None
    assert local_path_for_url(upload_dir, "/uploads/images/../../secret.txt") is None
    assert local_path_for_url(upload_dir, "/etc/passwd") is None


# ---------- 导出 Word 时的图片 ----------


@pytest.fixture
def image_server() -> Iterator[str]:
    """本地 HTTP 服务：/a.png 返回图片，/redirect 跳转到 /a.png，/text 返回非图片内容。"""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/a.png")
                self.end_headers()
                return
            body, ctype = (
                (tiny_png(), "image/png") if self.path == "/a.png" else (b"hi", "text/plain")
            )
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def media_of(docx: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        return [n for n in z.namelist() if n.startswith("word/media/")]


async def test_docx_embeds_local_upload(upload_dir: Path):
    (upload_dir / "images").mkdir()
    (upload_dir / "images" / "a.png").write_bytes(tiny_png())
    docx = await DocxConverter(get_settings()).convert("t", "![图](/uploads/images/a.png)")
    assert len(media_of(docx)) == 1


async def test_docx_downloads_public_images(
    upload_dir: Path, image_server: str, monkeypatch: pytest.MonkeyPatch
):
    # 测试服务器在 127.0.0.1，这里把它当作公网地址
    async def always_public(host: str) -> bool:
        return True

    monkeypatch.setattr(export_images, "_is_public_host", always_public)
    content = (
        f"![a]({image_server}/a.png)\n\n![b]({image_server}/redirect)\n\n![c]({image_server}/text)"
    )
    docx = await DocxConverter(get_settings()).convert("t", content)
    assert len(media_of(docx)) == 2  # 图片和跳转后的图片；非图片内容被忽略


async def test_docx_skips_private_addresses(upload_dir: Path, image_server: str):
    """解析到内网 / 本机地址的图片不下载，服务器文件也不会被读取。"""
    content = f"![内网]({image_server}/a.png)\n\n![文件](/etc/passwd)\n\n![越界](/uploads/../x.png)"
    docx = await DocxConverter(get_settings()).convert("t", content)
    assert media_of(docx) == []
