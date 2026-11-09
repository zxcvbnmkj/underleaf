"""清理没有被任何笔记引用的图片（手动执行）。

用法（在 backend 目录下）：

    pdm run python -m scripts.cleanup_images                 # 只列出将要删除的图片，不删除
    pdm run python -m scripts.cleanup_images --apply         # 确认无误后真正删除
    pdm run python -m scripts.cleanup_images --min-age-days 30

判断规则：
- 引用：任意笔记的正文中出现 /uploads/<图片路径>（不区分是哪位用户的笔记）
- 候选：数据库 image 表中的记录，以及上传目录 images/ 下存在但没有数据库记录的文件
- 只删除上传时间早于 --min-age-days 天（默认 7 天）的图片：刚粘贴的图片可能还在编辑器或
  浏览器本地草稿中、尚未保存到服务器，留出宽限期避免误删

删除是不可恢复的，执行 --apply 前建议先备份上传目录（见 docs/images.md）。
"""

import argparse
import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.models import Image, Note

REFERENCE = re.compile(r"/uploads/(images/[A-Za-z0-9/_.-]+)")


@dataclass
class Candidate:
    path: str
    size: int
    created_at: datetime
    in_db: bool
    on_disk: bool


async def referenced_paths() -> set[str]:
    refs: set[str] = set()
    async with SessionLocal() as session:
        result = await session.stream(select(Note.content).execution_options(yield_per=200))
        async for (content,) in result:
            refs.update(REFERENCE.findall(content))
    return refs


async def candidates(upload_dir: Path) -> dict[str, Candidate]:
    found: dict[str, Candidate] = {}
    async with SessionLocal() as session:
        for image in (await session.scalars(select(Image))).all():
            file = upload_dir / image.path
            found[image.path] = Candidate(
                path=image.path,
                size=image.size,
                created_at=image.created_at.replace(tzinfo=UTC),
                in_db=True,
                on_disk=file.is_file(),
            )
    images_dir = upload_dir / "images"
    if images_dir.is_dir():
        for file in images_dir.rglob("*"):
            if not file.is_file() or file.suffix == ".tmp":
                continue
            path = file.relative_to(upload_dir).as_posix()
            if path not in found:
                stat = file.stat()
                found[path] = Candidate(
                    path=path,
                    size=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_mtime, UTC),
                    in_db=False,
                    on_disk=True,
                )
    return found


async def main(apply: bool, min_age_days: int) -> None:
    upload_dir = get_settings().upload_dir
    cutoff = datetime.now(UTC) - timedelta(days=min_age_days)
    refs = await referenced_paths()
    all_images = await candidates(upload_dir)
    unused = sorted(
        (c for c in all_images.values() if c.path not in refs and c.created_at < cutoff),
        key=lambda c: c.created_at,
    )

    print(f"上传目录：{upload_dir}")
    print(f"图片总数：{len(all_images)}，被引用：{len(refs & all_images.keys())}")
    print(
        f"未被引用且早于 {cutoff:%Y-%m-%d %H:%M}（UTC）：{len(unused)} 张，"
        f"共 {sum(c.size for c in unused) / 1024 / 1024:.2f} MB"
    )
    for c in unused:
        note = (
            "" if c.in_db and c.on_disk else ("（文件已不存在）" if c.in_db else "（无数据库记录）")
        )
        print(f"  {c.created_at:%Y-%m-%d}  {c.size / 1024:8.1f} KB  /uploads/{c.path}{note}")

    if not unused:
        return
    if not apply:
        print("\n以上仅为预览，没有删除任何文件。确认后加上 --apply 执行删除。")
        return

    for c in unused:
        (upload_dir / c.path).unlink(missing_ok=True)
    async with SessionLocal() as session:
        await session.execute(delete(Image).where(Image.path.in_([c.path for c in unused])))
        await session.commit()
    print(f"\n已删除 {len(unused)} 张图片。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清理没有被任何笔记引用的图片")
    parser.add_argument("--apply", action="store_true", help="真正删除（默认只预览）")
    parser.add_argument(
        "--min-age-days", type=int, default=7, help="只清理上传超过这么多天的图片（默认 7）"
    )
    args = parser.parse_args()

    async def run() -> None:
        try:
            await main(args.apply, args.min_age_days)
        finally:
            await engine.dispose()

    asyncio.run(run())
