"""导出 Word 时收集正文中的图片。

Pandoc 以 --sandbox 运行（不读本地文件、不联网），图片由这里预先取好，再通过 Lua 过滤器
（underleaf.lua）按地址替换：
- 站内图片 /uploads/...：直接从磁盘读取（只允许 UPLOAD_DIR 之内的文件）
- http(s) 图片：下载。只拒绝解析到内网 / 本机 / 云服务器元数据等非公网地址的链接，
  防止借导出读取服务器内部信息；其余公网图片都会下载
- 其他地址（本地文件路径等）：不处理，Word 中显示为图片说明文字
"""

import asyncio
import ipaddress
import json
import logging
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import Settings
from app.services.images import detect_image, local_path_for_url

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 3
USER_AGENT = "Mozilla/5.0 (compatible; Underleaf-Export/1.0)"


@dataclass
class FetchedImage:
    data: bytes
    ext: str


def collect_image_urls(pandoc_json: str) -> list[str]:
    """从 Pandoc 的 JSON AST 中按出现顺序收集图片地址（去重）。"""
    urls: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("t") == "Image":
                # Image: [attr, inlines, [url, title]]
                target = node["c"][2]
                if target[0] not in urls:
                    urls.append(target[0])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(json.loads(pandoc_json))
    return urls


def _image_ext(data: bytes, content_type: str) -> str | None:
    detected = detect_image(data)
    if detected:
        return detected[1]
    head = data[:256].lstrip().lower()
    if "svg" in content_type or head.startswith((b"<svg", b"<?xml")):
        return "svg"  # Word 可以显示 SVG，且其中的脚本不会执行
    return None


async def _is_public_host(host: str) -> bool:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)


async def _download(client: httpx.AsyncClient, url: str, limit: int) -> FetchedImage | None:
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return None
        if not await _is_public_host(parts.hostname):
            logger.info("跳过非公网地址的图片：%s", url)
            return None
        async with client.stream("GET", url) as res:
            if res.is_redirect and "location" in res.headers:
                url = urljoin(url, res.headers["location"])  # 跳转后的地址同样要检查
                continue
            if res.status_code != 200:
                return None
            data = bytearray()
            async for chunk in res.aiter_bytes():
                data += chunk
                if len(data) > limit:
                    return None
            ext = _image_ext(bytes(data), res.headers.get("content-type", ""))
            return FetchedImage(bytes(data), ext) if ext else None
    return None


async def fetch_images(urls: list[str], settings: Settings) -> dict[str, FetchedImage]:
    """取回能处理的图片，返回 {原地址: 图片}。取不到的不在结果中（Word 中显示说明文字）。"""
    result: dict[str, FetchedImage] = {}
    remote: list[str] = []
    for url in urls[: settings.export_image_max_count]:
        local = local_path_for_url(settings.upload_dir, url)
        if local is not None:
            data = await asyncio.to_thread(local.read_bytes)
            ext = _image_ext(data, "")
            if ext:
                result[url] = FetchedImage(data, ext)
        elif url.startswith(("http://", "https://")):
            remote.append(url)

    if remote:
        limits = asyncio.Semaphore(4)
        async with httpx.AsyncClient(
            timeout=settings.export_image_timeout_seconds,
            follow_redirects=False,  # 手动跟随跳转，每一跳都检查是否为公网地址
            trust_env=False,  # 不使用系统代理：经代理访问会绕过上面的地址检查
            headers={"User-Agent": USER_AGENT},
        ) as client:

            async def one(url: str) -> None:
                async with limits:
                    try:
                        image = await _download(client, url, settings.export_image_max_bytes)
                    except (httpx.HTTPError, ValueError) as e:
                        logger.info("下载图片失败 %s：%s", url, e)
                        return
                    if image:
                        result[url] = image

            # 总耗时有上限：超时的图片放弃（Word 中显示说明文字），已下载的照常使用
            tasks = [asyncio.create_task(one(u)) for u in remote]
            _, pending = await asyncio.wait(tasks, timeout=settings.export_timeout_seconds / 2)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    return result


def write_image_map(directory: Path, images: dict[str, FetchedImage]) -> Path:
    """把图片写入临时目录，并生成 Lua 过滤器读取的映射文件 {地址: 文件路径}。"""
    mapping: dict[str, str] = {}
    for i, (url, image) in enumerate(images.items()):
        path = directory / f"image-{i}.{image.ext}"
        path.write_bytes(image.data)
        mapping[url] = str(path)
    map_file = directory / "images.json"
    map_file.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    return map_file
