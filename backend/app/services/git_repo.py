"""Git 仓库操作（不访问数据库）：生成快照提交、校验推送并算出要写回数据库的修改。

映射规则（readme「Git 同步 · 映射规则」）：
- 文件夹对应目录，笔记对应 `标题.md`，正文即文件内容（UTF-8）
- 仓库中只有目录和 `.md` 文件，不放平台私有文件；空文件夹在 Git 中无法表示，不出现在仓库里
- 「文件路径 → 笔记 id」由数据库推导：推送所基于的提交与数据库内容完全一致
"""

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from dulwich.diff_tree import CHANGE_RENAME, RenameDetector, tree_changes
from dulwich.graph import can_fast_forward
from dulwich.index import commit_tree
from dulwich.object_store import iter_tree_contents
from dulwich.objects import Blob, Commit, ObjectID
from dulwich.refs import Ref
from dulwich.repo import Repo

from app.core.errors import AppError
from app.services.names import clean_name

BRANCH = Ref(b"refs/heads/main")
FILE_MODE = 0o100644
# 可执行位在 Windows 上会被忽略，一并接受
_REGULAR_MODES = (0o100644, 0o100755)
_SYMLINK_MODE = 0o120000
_SUBMODULE_MODE = 0o160000
SUFFIX = ".md"
COMMITTER = b"Underleaf <noreply@underleaf>"
# 推送被拒绝时最多列出的问题数
MAX_ERRORS = 20

DirPath = tuple[str, ...]


@dataclass(frozen=True)
class FolderRow:
    id: int
    parent_id: int | None
    name: str


@dataclass(frozen=True)
class NoteRow:
    id: int
    folder_id: int | None
    title: str


class PushRejected(Exception):
    """推送不被接受。

    reason 简短，显示在 `! [remote rejected]` 后面；details 逐行显示为 `remote: ...`。
    """

    def __init__(self, reason: str, details: Iterable[str] = ()) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = list(details)


class RepoOutOfSync(Exception):
    """仓库的提交与数据库不一致（如仓库目录丢失、写回中途崩溃），需要重新生成快照。"""


def key(path: DirPath) -> DirPath:
    """数据库中的名称不区分大小写（排序规则 _ci），比较路径时统一转小写。"""
    return tuple(p.casefold() for p in path)


# ---------- 数据库 → 路径 ----------


def folder_paths(folders: Iterable[FolderRow]) -> dict[int, DirPath]:
    """每个文件夹的完整路径，如 {3: ("读书", "小说")}。"""
    by_id = {f.id: f for f in folders}
    cache: dict[int, DirPath] = {}

    def path_of(fid: int) -> DirPath:
        if fid not in cache:
            f = by_id[fid]
            parent = path_of(f.parent_id) if f.parent_id is not None else ()
            cache[fid] = (*parent, f.name)
        return cache[fid]

    for fid in by_id:
        path_of(fid)
    return cache


def note_path(dirs: DirPath, title: str) -> str:
    return "/".join((*dirs, title + SUFFIX))


def note_paths(folders: Iterable[FolderRow], notes: Iterable[NoteRow]) -> dict[str, int]:
    """{文件路径: 笔记 id}"""
    fpaths = folder_paths(folders)
    return {
        note_path(fpaths[n.folder_id] if n.folder_id is not None else (), n.title): n.id
        for n in notes
    }


# ---------- 仓库 ----------


def open_repo(path: Path) -> Repo:
    """打开裸仓库，不存在时创建（默认分支 main）。"""
    if (path / "HEAD").exists():
        return Repo(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    repo = Repo.init_bare(str(path), mkdir=not path.exists())
    repo.refs.set_symbolic_ref(Ref(b"HEAD"), BRANCH)
    return repo


def head_of(repo: Repo) -> ObjectID | None:
    try:
        return repo.refs[BRANCH]
    except KeyError:
        return None


def write_snapshot(repo: Repo, files: Iterable[tuple[str, bytes]], message: str) -> ObjectID:
    """把 {路径: 内容} 提交为 main 的新提交（父提交为当前 main），返回提交号。

    内容与当前提交完全相同时不生成新提交。调用方需持有该用户的锁。
    """
    store = repo.object_store
    entries: list[tuple[bytes, ObjectID, int]] = []
    for path, data in files:
        blob = Blob.from_string(data)
        if blob.id not in store:
            store.add_object(blob)
        entries.append((path.encode(), blob.id, FILE_MODE))
    tree_id = commit_tree(store, entries)

    head = head_of(repo)
    if head is not None:
        head_commit = repo[head]
        assert isinstance(head_commit, Commit)
        if head_commit.tree == tree_id:
            return head

    commit = Commit()
    commit.tree = tree_id
    commit.parents = [head] if head is not None else []
    commit.author = commit.committer = COMMITTER
    commit.author_time = commit.commit_time = int(time.time())
    commit.author_timezone = commit.commit_timezone = 0
    commit.encoding = b"UTF-8"
    commit.message = message.encode()
    store.add_object(commit)
    repo.refs[BRANCH] = commit.id
    return commit.id


def tree_of(repo: Repo, commit_id: ObjectID) -> ObjectID:
    """提交对应的目录树；对象不存在或不是提交时抛出 PushRejected。"""
    try:
        obj = repo[commit_id]
    except KeyError as e:
        raise PushRejected("提交不存在") from e
    if not isinstance(obj, Commit):
        raise PushRejected("只能推送提交")
    return obj.tree


def is_fast_forward(repo: Repo, old: ObjectID, new: ObjectID) -> bool:
    return old == new or can_fast_forward(repo, old, new)


# ---------- 推送 → 数据库修改 ----------


@dataclass
class PushPlan:
    """把仓库从旧提交改为新提交，需要对数据库做的修改。"""

    # 删除的笔记
    delete_notes: list[int] = field(default_factory=list)
    # 移动或改名的笔记：id → (所在目录, 新标题)
    move_notes: dict[int, tuple[DirPath, str]] = field(default_factory=dict)
    # 正文有变化的笔记：id → 新正文
    update_notes: dict[int, str] = field(default_factory=dict)
    # 新建的笔记：(所在目录, 标题, 正文)
    create_notes: list[tuple[DirPath, str, str]] = field(default_factory=list)
    # 需要新建的文件夹（父目录在前）
    create_dirs: list[DirPath] = field(default_factory=list)
    # 只改了大小写的文件夹：id → 新名称
    rename_dirs: dict[int, str] = field(default_factory=dict)
    # 删除的文件夹（其中的子文件夹由数据库级联删除）
    delete_dirs: list[int] = field(default_factory=list)

    def summary(self) -> str:
        parts = [
            (len(self.create_notes), "新增"),
            (len(self.update_notes), "修改"),
            (len(self.move_notes), "移动或重命名"),
            (len(self.delete_notes), "删除"),
        ]
        text = "，".join(f"{label} {n} 篇" for n, label in parts if n)
        return f"Underleaf：已同步到网页（{text or '笔记没有变化'}）"


@dataclass(frozen=True)
class _NewFile:
    dirs: DirPath
    title: str
    sha: ObjectID


def _check_name(raw: str, what: str) -> str | None:
    """返回错误信息；名称合法时返回 None。名称不能有首尾空白（否则保存后与文件名对不上）。"""
    try:
        cleaned = clean_name(raw, what)
    except AppError as e:
        return e.message
    if cleaned != raw:
        return f"{what}不能以空白字符开头或结尾"
    return None


def _scan_new_tree(
    repo: Repo, tree_id: ObjectID, max_depth: int
) -> tuple[dict[str, _NewFile], list[str]]:
    """列出新提交中的所有笔记，检查文件类型、名称、层数和重名。"""
    files: dict[str, _NewFile] = {}
    errors: list[str] = []
    # 不区分大小写的路径 → 第一次出现时的写法，用于发现重名
    seen_dirs: dict[DirPath, DirPath] = {}
    seen_notes: dict[tuple[DirPath, str], str] = {}

    for entry in iter_tree_contents(repo.object_store, tree_id):
        assert entry.path is not None and entry.mode is not None and entry.sha is not None
        try:
            path = entry.path.decode()
        except UnicodeDecodeError:
            errors.append(f"{entry.path!r}：文件名不是 UTF-8 编码")
            continue
        if entry.mode == _SYMLINK_MODE:
            errors.append(f"{path}：不支持符号链接")
            continue
        if entry.mode == _SUBMODULE_MODE:
            errors.append(f"{path}：不支持子模块")
            continue
        if entry.mode not in _REGULAR_MODES:
            errors.append(f"{path}：不支持的文件类型")
            continue

        *dirs, filename = path.split("/")
        if not filename.endswith(SUFFIX):
            errors.append(f"{path}：只能包含 .md 文件和文件夹")
            continue
        title = filename.removesuffix(SUFFIX)
        problems = [_check_name(d, "文件夹名") for d in dirs] + [_check_name(title, "标题")]
        if len(dirs) > max_depth:
            problems.append(f"文件夹最多 {max_depth} 层")
        problem = next((p for p in problems if p), None)
        if problem:
            errors.append(f"{path}：{problem}")
            continue

        dir_path = tuple(dirs)
        for i in range(1, len(dir_path) + 1):
            prefix = dir_path[:i]
            first = seen_dirs.setdefault(key(prefix), prefix)
            if first != prefix:
                errors.append(f"{'/'.join(prefix)}：与 {'/'.join(first)} 重名（不区分大小写）")
        note_key = (key(dir_path), title.casefold())
        first_note = seen_notes.setdefault(note_key, path)
        if first_note != path:
            errors.append(f"{path}：与 {first_note} 重名（不区分大小写）")
        files[path] = _NewFile(dir_path, title, entry.sha)

    # 同一个重名问题可能被多个文件触发，去重并保持顺序
    return files, list(dict.fromkeys(errors))


def _read_text(
    repo: Repo, path: str, sha: ObjectID, max_bytes: int
) -> tuple[str | None, str | None]:
    """返回 (正文, 错误信息)。"""
    blob = repo[sha]
    assert isinstance(blob, Blob)
    data = blob.as_raw_string()
    if len(data) > max_bytes:
        return None, f"{path}：超过 {max_bytes // 1024 // 1024}MB"
    try:
        return data.decode(), None
    except UnicodeDecodeError:
        return None, f"{path}：不是 UTF-8 编码的文本"


def plan_push(
    repo: Repo,
    old_tree: ObjectID,
    new_tree: ObjectID,
    folders: list[FolderRow],
    notes: list[NoteRow],
    *,
    max_bytes: int,
    max_depth: int,
) -> PushPlan:
    """对比推送前后的目录树，算出要写回数据库的修改；不合法时抛出 PushRejected。

    folders / notes 是数据库中的现状，必须与 old_tree 一致，否则抛出 RepoOutOfSync。
    """
    new_files, errors = _scan_new_tree(repo, new_tree, max_depth)

    # 旧提交中的路径 → 笔记 id（由数据库推导）
    db_paths = note_paths(folders, notes)
    old_files = {
        e.path.decode(): e.sha
        for e in iter_tree_contents(repo.object_store, old_tree)
        if e.path is not None and e.sha is not None
    }
    if set(old_files) != set(db_paths):
        raise RepoOutOfSync

    # 改名检测（内容相似度 ≥ 60% 视为同一篇，与 git 默认一致）：新路径 → 旧路径
    renames: dict[str, str] = {}
    for change in tree_changes(
        repo.object_store, old_tree, new_tree, rename_detector=RenameDetector(repo.object_store)
    ):
        if change.type == CHANGE_RENAME and change.old and change.new:
            assert change.old.path is not None and change.new.path is not None
            renames[change.new.path.decode()] = change.old.path.decode()

    plan = PushPlan()
    kept: set[int] = set()
    for path, f in new_files.items():
        old_path = path if path in old_files else renames.get(path)
        content: str | None = None
        if old_path is None or old_files[old_path] != f.sha:
            content, problem = _read_text(repo, path, f.sha, max_bytes)
            if problem:
                errors.append(problem)
                continue
        if old_path is None:
            assert content is not None
            plan.create_notes.append((f.dirs, f.title, content))
            continue
        note_id = db_paths[old_path]
        kept.add(note_id)
        if old_path != path:
            plan.move_notes[note_id] = (f.dirs, f.title)
        if content is not None:
            plan.update_notes[note_id] = content

    if errors:
        shown = errors[:MAX_ERRORS]
        if len(errors) > MAX_ERRORS:
            shown.append(f"……共 {len(errors)} 个问题")
        raise PushRejected("推送的内容不符合要求", shown)

    plan.delete_notes = sorted(set(db_paths.values()) - kept)

    # 文件夹：按路径（不区分大小写）对应到数据库中的文件夹，包括仓库中看不到的空文件夹
    db_dirs = {key(p): (fid, p) for fid, p in folder_paths(folders).items()}
    new_dirs: dict[DirPath, DirPath] = {}
    for f in new_files.values():
        for i in range(1, len(f.dirs) + 1):
            new_dirs.setdefault(key(f.dirs[:i]), f.dirs[:i])
    old_dirs = {key(tuple(p.split("/")[:i])) for p in old_files for i in range(1, p.count("/") + 1)}
    for k, path in sorted(new_dirs.items(), key=lambda kv: len(kv[0])):
        if k in db_dirs:
            fid, db_path = db_dirs[k]
            if db_path[-1] != path[-1]:
                plan.rename_dirs[fid] = path[-1]
        else:
            plan.create_dirs.append(path)
    # 只删除旧提交中出现过、新提交中消失的目录；从未出现在仓库中的空文件夹保留
    plan.delete_dirs = sorted(
        fid for k, (fid, _) in db_dirs.items() if k in old_dirs and k not in new_dirs
    )
    return plan
