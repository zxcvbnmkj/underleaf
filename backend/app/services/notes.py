"""文件夹与笔记的公共逻辑：归属校验、层级检查、同名处理、内容版本计数。"""

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Folder, Note, User

# MySQL 级联删除最多连锁 15 层，留出余量
MAX_FOLDER_DEPTH = 10


async def own_folder(session: AsyncSession, user_id: int, folder_id: int) -> Folder:
    folder = await session.get(Folder, folder_id)
    if folder is None or folder.user_id != user_id:
        raise AppError(404, "not_found", "文件夹不存在")
    return folder


async def own_note(session: AsyncSession, user_id: int, note_id: int) -> Note:
    note = await session.get(Note, note_id)
    if note is None or note.user_id != user_id:
        raise AppError(404, "not_found", "笔记不存在或已被删除")
    return note


async def bump_content_rev(session: AsyncSession, user_id: int) -> None:
    """笔记或文件夹有任何变动时调用，供 Git 同步判断是否需要生成快照。原子自增，避免并发丢失。"""
    await session.execute(
        update(User).where(User.id == user_id).values(content_rev=User.content_rev + 1)
    )


async def folder_parents(session: AsyncSession, user_id: int) -> dict[int, int | None]:
    """该用户所有文件夹的 {id: parent_id}，用于计算层级（文件夹数量不多，一次全部取出）。"""
    rows = await session.execute(
        select(Folder.id, Folder.parent_id).where(Folder.user_id == user_id)
    )
    return {fid: pid for fid, pid in rows.all()}


def depth_of(parents: dict[int, int | None], folder_id: int | None) -> int:
    """根目录为 0，根目录下的文件夹为 1。"""
    depth = 0
    while folder_id is not None:
        depth += 1
        folder_id = parents.get(folder_id)
    return depth


def subtree_height(parents: dict[int, int | None], folder_id: int) -> int:
    """以该文件夹为根的子树层数（只有它自己时为 1）。"""
    children: dict[int, list[int]] = {}
    for fid, pid in parents.items():
        if pid is not None:
            children.setdefault(pid, []).append(fid)

    def height(fid: int) -> int:
        return 1 + max((height(c) for c in children.get(fid, [])), default=0)

    return height(folder_id)


def is_descendant(parents: dict[int, int | None], folder_id: int, ancestor_id: int) -> bool:
    """folder_id 是否就是 ancestor_id 或位于它之下。"""
    current: int | None = folder_id
    while current is not None:
        if current == ancestor_id:
            return True
        current = parents.get(current)
    return False


def too_deep() -> AppError:
    return AppError(400, "too_deep", f"文件夹最多 {MAX_FOLDER_DEPTH} 层")


async def save_changes(
    session: AsyncSession, user_id: int, conflict_message: str, *, content_changed: bool = True
) -> None:
    """写入修改并提交；同一文件夹下重名（唯一约束）时返回 409。

    content_changed 时同一事务内给 content_rev 加 1。先 flush 再计数：计数的 UPDATE 会触发自动
    flush，重名错误要在这里统一捕获。
    """
    try:
        await session.flush()
        if content_changed:
            await bump_content_rev(session, user_id)
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise AppError(409, "name_taken", conflict_message) from e


async def unique_title(
    session: AsyncSession, user_id: int, folder_id: int | None, title: str
) -> str:
    """新建笔记时自动避开重名：未命名笔记 → 未命名笔记 2 → 未命名笔记 3 …"""
    rows = await session.scalars(
        select(Note.title).where(
            Note.user_id == user_id,
            Note.folder_id.is_(None) if folder_id is None else Note.folder_id == folder_id,
        )
    )
    # 唯一索引不区分大小写，这里也按小写比较
    taken = {t.lower() for t in rows}
    if title.lower() not in taken:
        return title
    n = 2
    while f"{title} {n}".lower() in taken:
        n += 1
    return f"{title} {n}"
