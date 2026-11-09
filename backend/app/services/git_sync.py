"""Git 同步与数据库之间的衔接：生成快照（clone / pull）、把推送写回数据库（push）。

以数据库为准，Git 仓库只是镜像（readme「Git 同步 · 实现方案」）：
- 每次 clone / fetch / push 前比较 user.content_rev 与 git_repo.synced_rev，不相等说明网页上有修改，
  从数据库生成目录树并提交一个快照。网页上的多次自动保存不会各自生成提交
- 推送只接受快进，并且要求推送所基于的提交就是当前快照（网页上有新修改时客户端会提示先 pull）；
  写回在一个数据库事务中完成，笔记 id 不变，分享链接继续有效

并发：git_repo 行作为该用户的锁（SELECT ... FOR UPDATE），同一用户的快照和推送串行执行。
"""

import asyncio
from pathlib import Path

from dulwich.objects import ObjectID
from dulwich.repo import Repo
from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.core.config import get_settings
from app.models import Folder, GitRepo, Note, User
from app.services import git_repo as g
from app.services.notes import MAX_FOLDER_DEPTH, bump_content_rev, is_descendant

SNAPSHOT_MESSAGE = "网页端的修改"
# 写回时移动的笔记先临时改成这个标题（含 : ，不可能与合法标题重名），避免互换名称时撞唯一索引
_PARKED_TITLE = "git:parked:{}"


def clone_path(user_id: int) -> str:
    return f"/api/v1/git/{user_id}/notes.git"


def repo_dir(user_id: int) -> Path:
    return get_settings().git_repo_dir / f"{user_id}.git"


async def _lock(session: AsyncSession, user_id: int) -> GitRepo:
    """取得该用户的 Git 锁（行锁，事务结束时释放）。调用前当前会话不能有未结束的事务，
    否则之后读取的笔记可能是加锁之前的旧快照（InnoDB 的一致性读视图在事务第一次普通读取时建立）。
    """
    await session.execute(insert(GitRepo).prefix_with("IGNORE").values(user_id=user_id))
    return (
        await session.scalars(
            select(GitRepo)
            .where(GitRepo.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()


async def _load_tree(
    session: AsyncSession, user_id: int
) -> tuple[list[g.FolderRow], list[g.NoteRow]]:
    folders = await session.execute(
        select(Folder.id, Folder.parent_id, Folder.name).where(Folder.user_id == user_id)
    )
    notes = await session.execute(
        select(Note.id, Note.folder_id, Note.title).where(Note.user_id == user_id)
    )
    return (
        [g.FolderRow(*row) for row in folders.all()],
        [g.NoteRow(*row) for row in notes.all()],
    )


async def sync_snapshot(session: AsyncSession, user_id: int) -> None:
    """clone / fetch / push 之前调用：网页上有新修改时生成快照提交，保证仓库与数据库一致。"""
    await session.commit()  # 结束之前的事务（见 _lock）
    state = await _lock(session, user_id)
    rev = await session.scalar(select(User.content_rev).where(User.id == user_id))
    repo = await asyncio.to_thread(g.open_repo, repo_dir(user_id))
    try:
        head = g.head_of(repo)
        if head is not None and head.decode() == state.head_commit and state.synced_rev == rev:
            await session.commit()
            return

        fpaths = g.folder_paths((await _load_tree(session, user_id))[0])
        rows = await session.execute(
            select(Note.folder_id, Note.title, Note.content).where(Note.user_id == user_id)
        )
        files = [
            (g.note_path(fpaths[fid] if fid is not None else (), title), content.encode())
            for fid, title, content in rows.all()
        ]
        sha = await asyncio.to_thread(g.write_snapshot, repo, files, SNAPSHOT_MESSAGE)
        state.head_commit = sha.decode()
        state.synced_rev = rev
        await session.commit()
    finally:
        repo.close()


async def apply_push(
    session: AsyncSession, user_id: int, repo: Repo, old: ObjectID, new: ObjectID
) -> str:
    """把推送写回数据库并更新 main，返回给客户端的提示。

    不接受时抛出 PushRejected；调用方负责在出错时回滚事务（释放锁）。
    """
    settings = get_settings()
    await session.commit()
    state = await _lock(session, user_id)
    # 锁住用户行：写回期间网页端的保存（会给 content_rev 加 1）要等待，避免检查之后又有新修改
    rev = await session.scalar(select(User.content_rev).where(User.id == user_id).with_for_update())
    head = g.head_of(repo)
    if head is None or head.decode() != state.head_commit or state.synced_rev != rev or old != head:
        raise g.PushRejected(
            "fetch first", ["网页上有新的修改，请先执行 git pull 合并，再重新推送"]
        )
    new_tree = g.tree_of(repo, new)
    if not await asyncio.to_thread(g.is_fast_forward, repo, head, new):
        raise g.PushRejected("non-fast-forward", ["只接受快进推送，请先执行 git pull 合并"])

    folders, notes = await _load_tree(session, user_id)
    try:
        plan = await asyncio.to_thread(
            g.plan_push,
            repo,
            g.tree_of(repo, head),
            new_tree,
            folders,
            notes,
            max_bytes=settings.note_max_bytes,
            max_depth=MAX_FOLDER_DEPTH,
        )
    except g.RepoOutOfSync as e:
        # 理论上不会发生；标记为未同步，下次 fetch 时从数据库重新生成快照
        state.synced_rev = None
        await session.commit()
        raise g.PushRejected(
            "out of sync", ["服务器上的仓库与网页数据不一致，已重新生成，请先执行 git pull"]
        ) from e

    try:
        await _apply_plan(session, user_id, plan)
    except IntegrityError as e:
        raise g.PushRejected(
            "name conflict", ["与已有的笔记或文件夹重名（名称不区分大小写和重音符号）"]
        ) from e
    await bump_content_rev(session, user_id)
    state.synced_rev = await session.scalar(select(User.content_rev).where(User.id == user_id))
    state.head_commit = new.decode()
    await session.flush()

    # 先更新 main 再提交事务；提交失败时把 main 改回去
    repo.refs.set_if_equals(g.BRANCH, head, new)
    try:
        await session.commit()
    except Exception:
        repo.refs.set_if_equals(g.BRANCH, new, head)
        raise
    return plan.summary()


async def _apply_plan(session: AsyncSession, user_id: int, plan: g.PushPlan) -> None:
    """在当前事务中执行写回。顺序很重要：唯一索引 (所在文件夹, 名称) 在每条语句执行时就检查。"""
    notes = {
        n.id: n
        for n in await session.scalars(
            select(Note).options(defer(Note.content)).where(Note.user_id == user_id)
        )
    }
    folders = {
        f.id: f for f in await session.scalars(select(Folder).where(Folder.user_id == user_id))
    }

    # 1. 删除笔记
    for nid in plan.delete_notes:
        await session.delete(notes[nid])
    # 2. 要移动 / 改名的笔记先移到根目录并改成临时标题，腾出名称，也避免被下一步级联删除
    for nid in plan.move_notes:
        notes[nid].folder_id = None
        notes[nid].title = _PARKED_TITLE.format(nid)
    await session.flush()
    # 3. 删除文件夹（子文件夹由数据库级联删除，所以不用 ORM 逐个删除），并从会话中移除
    if plan.delete_dirs:
        await session.execute(
            delete(Folder)
            .where(Folder.id.in_(plan.delete_dirs))
            .execution_options(synchronize_session=False)
        )
        parents = {f.id: f.parent_id for f in folders.values()}
        for fid in [
            f for f in folders if any(is_descendant(parents, f, d) for d in plan.delete_dirs)
        ]:
            session.expunge(folders.pop(fid))
    # 4. 只改了大小写的文件夹
    for fid, name in plan.rename_dirs.items():
        folders[fid].name = name
    # 5. 新建文件夹（父目录在前）
    dir_ids = {
        g.key(p): fid
        for fid, p in g.folder_paths(
            g.FolderRow(f.id, f.parent_id, f.name) for f in folders.values()
        ).items()
    }

    def folder_id_of(path: g.DirPath) -> int | None:
        return dir_ids[g.key(path)] if path else None

    for path in plan.create_dirs:
        folder = Folder(user_id=user_id, parent_id=folder_id_of(path[:-1]), name=path[-1])
        session.add(folder)
        await session.flush()
        dir_ids[g.key(path)] = folder.id
    # 6. 移动到最终位置、更新正文、新建笔记
    for nid, (dirs, title) in plan.move_notes.items():
        notes[nid].folder_id = folder_id_of(dirs)
        notes[nid].title = title
    for nid, content in plan.update_notes.items():
        notes[nid].content = content
        # 正在网页上编辑这篇笔记的浏览器下次保存会收到 409，复用现有的冲突处理
        notes[nid].version = Note.version + 1
    for dirs, title, content in plan.create_notes:
        session.add(
            Note(user_id=user_id, folder_id=folder_id_of(dirs), title=title, content=content)
        )
    await session.flush()
