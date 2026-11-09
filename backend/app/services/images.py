"""图片上传：校验、保存到本地磁盘、生成站内地址。

- 只接受 PNG / JPEG / GIF / WebP，按文件头判断（不信任扩展名和 Content-Type）；
  不接受 SVG：SVG 中可以嵌入脚本
- 文件名为随机字符串，按年月分目录：images/2026/11/<32 位十六进制>.png
- Markdown 中写站内相对地址 /uploads/images/...，不包含域名，换服务器、换域名后无需修改笔记
  （迁移流程见 docs/images.md）
"""

import secrets
from datetime import UTC, datetime
from pathlib import Path

URL_PREFIX = "/uploads/"

# (文件头特征, MIME, 扩展名)
_SIGNATURES: list[tuple[bytes, int, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", 0, "image/png", "png"),
    (b"\xff\xd8\xff", 0, "image/jpeg", "jpg"),
    (b"GIF87a", 0, "image/gif", "gif"),
    (b"GIF89a", 0, "image/gif", "gif"),
    (b"WEBP", 8, "image/webp", "webp"),  # RIFF....WEBP
]


def detect_image(data: bytes) -> tuple[str, str] | None:
    """按文件头识别图片格式，返回 (MIME, 扩展名)；不是支持的格式时返回 None。"""
    for magic, offset, mime, ext in _SIGNATURES:
        if data[offset : offset + len(magic)] == magic:
            if mime == "image/webp" and not data.startswith(b"RIFF"):
                continue
            return mime, ext
    return None


def new_image_path(ext: str) -> str:
    now = datetime.now(UTC)
    return f"images/{now:%Y}/{now:%m}/{secrets.token_hex(16)}.{ext}"


def save_file(upload_dir: Path, path: str, data: bytes) -> None:
    target = upload_dir / path
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)  # 先写临时文件再改名，避免中途失败留下残缺文件


def url_for(path: str) -> str:
    return URL_PREFIX + path


def local_path_for_url(upload_dir: Path, url: str) -> Path | None:
    """把站内图片地址 /uploads/... 转为磁盘路径；不是站内地址或试图越出上传目录时返回 None。"""
    if not url.startswith(URL_PREFIX):
        return None
    root = upload_dir.resolve()
    target = (root / url.removeprefix(URL_PREFIX).split("?")[0].split("#")[0]).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return None
    return target
