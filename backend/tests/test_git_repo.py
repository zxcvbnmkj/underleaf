"""Git 仓库操作：快照、推送校验与写回计划（不需要数据库）。"""

from pathlib import Path

import pytest
from dulwich.index import commit_tree
from dulwich.objects import Blob, Commit, ObjectID
from dulwich.refs import Ref
from dulwich.repo import Repo

from app.services import git_repo as g

MAX = 1024 * 1024


@pytest.fixture(autouse=True)
def clean_redis() -> None:
    """覆盖 conftest 中的同名夹具：这里的测试不用 Redis，没有 Redis 时也能运行。"""


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return g.open_repo(tmp_path / "1.git")


def make_tree(repo: Repo, files: dict[str, bytes], mode: int = g.FILE_MODE) -> ObjectID:
    entries = []
    for path, data in files.items():
        blob = Blob.from_string(data)
        repo.object_store.add_object(blob)
        entries.append((path.encode(), blob.id, mode))
    return commit_tree(repo.object_store, entries)


def plan(
    repo: Repo,
    old: dict[str, bytes],
    new: dict[str, bytes],
    folders: list[g.FolderRow],
    notes: list[g.NoteRow],
) -> g.PushPlan:
    return g.plan_push(
        repo, make_tree(repo, old), make_tree(repo, new), folders, notes,
        max_bytes=MAX, max_depth=3,
    )  # fmt: skip


def rejected(repo: Repo, new: dict[str, bytes]) -> list[str]:
    with pytest.raises(g.PushRejected) as e:
        plan(repo, {}, new, [], [])
    return e.value.details


def test_open_repo_uses_main(repo: Repo, tmp_path: Path):
    assert repo.refs.read_ref(Ref(b"HEAD")) == b"ref: refs/heads/main"
    assert g.head_of(repo) is None
    g.open_repo(tmp_path / "1.git").close()  # 已存在时直接打开


def test_snapshot_skips_unchanged_tree(repo: Repo):
    first = g.write_snapshot(repo, [("a.md", b"A"), ("d/b.md", b"B")], "m")
    assert g.write_snapshot(repo, [("d/b.md", b"B"), ("a.md", b"A")], "m") == first
    second = g.write_snapshot(repo, [("a.md", b"A2")], "m")
    commit = repo[second]
    assert isinstance(commit, Commit) and commit.parents == [first]
    assert g.head_of(repo) == second
    # 空仓库也有一个提交，clone 后就有 main 分支
    assert g.write_snapshot(repo, [], "m") != second


def test_note_paths():
    folders = [g.FolderRow(1, None, "读书"), g.FolderRow(2, 1, "小说"), g.FolderRow(3, None, "空")]
    notes = [g.NoteRow(10, 2, "红楼梦"), g.NoteRow(11, None, "Todo")]
    assert g.note_paths(folders, notes) == {"读书/小说/红楼梦.md": 10, "Todo.md": 11}


BODY = b"".join(f"line {i}\n".encode() for i in range(6))


def test_plan_add_modify_rename_delete(repo: Repo):
    folders = [g.FolderRow(1, None, "old"), g.FolderRow(2, None, "Empty")]
    notes = [
        g.NoteRow(10, None, "keep"),
        g.NoteRow(11, None, "edit"),
        g.NoteRow(12, 1, "move"),
        g.NoteRow(13, None, "gone"),
    ]
    old = {
        "keep.md": b"same",
        "edit.md": b"before",
        "old/move.md": BODY,
        "gone.md": b"bye",
    }
    new = {
        "keep.md": b"same",
        "edit.md": b"after",
        "new/sub/moved.md": BODY + b"line 6\n",
        "empty/x.md": b"x",
        "fresh.md": "新笔记".encode(),
    }
    p = plan(repo, old, new, folders, notes)
    # 改名同时改了内容：相似度够高（按行比较，与 git 一致）时仍视为同一篇
    assert p.update_notes == {11: "after", 12: (BODY + b"line 6\n").decode()}
    assert p.move_notes == {12: (("new", "sub"), "moved")}
    assert sorted(p.create_notes) == [((), "fresh", "新笔记"), (("empty",), "x", "x")]
    assert p.delete_notes == [13]
    # 已有的空文件夹按名称（不区分大小写）复用，并改成仓库中的大小写
    assert p.rename_dirs == {2: "empty"}
    assert p.create_dirs == [("new",), ("new", "sub")]
    assert p.delete_dirs == [1]
    assert "新增 2 篇" in p.summary() and "删除 1 篇" in p.summary()


def test_plan_keeps_empty_folders_not_in_repo(repo: Repo):
    folders = [g.FolderRow(1, None, "a"), g.FolderRow(2, 1, "empty-child")]
    notes = [g.NoteRow(10, 1, "n")]
    p = plan(repo, {"a/n.md": b"x"}, {"a/n.md": b"x", "b.md": b"y"}, folders, notes)
    assert p.delete_dirs == [] and p.create_dirs == []


def test_plan_detects_out_of_sync(repo: Repo):
    with pytest.raises(g.RepoOutOfSync):
        plan(repo, {"a.md": b"x"}, {"a.md": b"y"}, [], [g.NoteRow(1, None, "b")])


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("image.png", "只能包含 .md 文件"),
        ("a:b.md", "不能包含"),
        (" lead.md", "空白字符"),
        ("dir /x.md", "空白字符"),
        (".md", "不能为空"),
        ("a/b/c/d/deep.md", "最多 3 层"),
    ],
)
def test_reject_bad_paths(repo: Repo, path: str, message: str):
    details = rejected(repo, {path: b"x"})
    assert len(details) == 1 and details[0].startswith(path) and message in details[0]


def test_reject_case_insensitive_duplicates(repo: Repo):
    details = rejected(repo, {"Note.md": b"1", "note.md": b"2", "D/a.md": b"", "d/b.md": b""})
    assert any("重名" in d and "note.md" in d.lower() for d in details)
    assert any(d.startswith("d：与 D 重名") or d.startswith("D：与 d 重名") for d in details)


def test_reject_bad_content(repo: Repo):
    details = rejected(repo, {"big.md": b"x" * (MAX + 1), "bin.md": b"\xff\xfe\x00"})
    assert sorted(details) == ["big.md：超过 1MB", "bin.md：不是 UTF-8 编码的文本"]


def test_reject_symlink(repo: Repo):
    tree = make_tree(repo, {"link.md": b"target"}, mode=0o120000)
    with pytest.raises(g.PushRejected) as e:
        g.plan_push(repo, make_tree(repo, {}), tree, [], [], max_bytes=MAX, max_depth=3)
    assert e.value.details == ["link.md：不支持符号链接"]
