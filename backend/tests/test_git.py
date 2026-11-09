"""访问令牌、Git 接口认证、快照与推送写回（真实 MySQL 测试库）。

完整的 git clone / pull / push 需要真实的 HTTP 服务和 git 客户端，这里直接调用服务层：
用 dulwich 在服务器仓库中构造提交，再调用 apply_push，与 receive-pack 收到推送后的流程一致。
"""

import base64
import time
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from dulwich.index import commit_tree
from dulwich.object_store import iter_tree_contents
from dulwich.objects import Blob, Commit, ObjectID
from dulwich.repo import Repo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import AccessToken, Folder, Note, User
from app.services import git_repo as g
from app.services.access_tokens import utcnow
from app.services.git_sync import apply_push, repo_dir, sync_snapshot
from tests.conftest import login_as


@pytest.fixture(autouse=True)
def repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(get_settings(), "git_repo_dir", tmp_path)
    return tmp_path


def basic(token: str) -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"git:{token}".encode()).decode()}


async def new_token(api: httpx.AsyncClient, **body: object) -> dict:
    res = await api.post("/api/v1/tokens", json={"name": "laptop", **body})
    assert res.status_code == 200, res.text
    return res.json()


# ---------- 访问令牌 ----------


async def test_token_lifecycle(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session)
    created = await new_token(api, expiresInDays=30)
    assert created["token"].startswith("ulp_") and created["token"].endswith(created["lastChars"])
    assert created["expiresAt"] is not None

    listed = (await api.get("/api/v1/tokens")).json()
    assert [t["id"] for t in listed] == [created["id"]]
    assert "token" not in listed[0]  # 明文只在创建时返回

    # 数据库中只有哈希
    record = await session.get(AccessToken, created["id"])
    assert record is not None and created["token"] not in record.token_hash

    assert (await api.delete(f"/api/v1/tokens/{created['id']}")).status_code == 204
    assert (await api.get("/api/v1/tokens")).json() == []


async def test_token_belongs_to_owner(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session, "alice")
    token = await new_token(api)
    await login_as(api, session, "bob")
    assert (await api.delete(f"/api/v1/tokens/{token['id']}")).status_code == 404


async def test_git_info(api: httpx.AsyncClient, session: AsyncSession):
    user = await login_as(api, session)
    info = (await api.get("/api/v1/git/info")).json()
    assert info["clonePath"] == f"/api/v1/git/{user.id}/notes.git"


# ---------- Git 接口认证 ----------


async def test_git_auth(api: httpx.AsyncClient, session: AsyncSession):
    user = await login_as(api, session)
    token = (await new_token(api))["token"]
    url = f"/api/v1/git/{user.id}/notes.git/info/refs?service=git-upload-pack"
    api.cookies.clear()  # Git 接口不使用登录 Cookie

    res = await api.get(url)
    assert res.status_code == 401 and res.headers["www-authenticate"].startswith("Basic")
    res = await api.get(url, headers=basic("ulp_wrong"))
    assert res.status_code == 401

    res = await api.get(url, headers=basic(token))
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/x-git-upload-pack-advertisement"
    assert b"# service=git-upload-pack" in res.content and b"refs/heads/main" in res.content

    # 只支持 Smart HTTP
    res = await api.get(f"/api/v1/git/{user.id}/notes.git/info/refs", headers=basic(token))
    assert res.status_code == 403
    # 不能访问别人的仓库
    res = await api.get(url.replace(f"/{user.id}/", f"/{user.id + 1}/"), headers=basic(token))
    assert res.status_code == 404

    record = (await session.scalars(select(AccessToken))).one()
    await session.refresh(record)
    assert record.last_used_at is not None


async def test_expired_and_revoked_tokens(api: httpx.AsyncClient, session: AsyncSession):
    user = await login_as(api, session)
    created = await new_token(api)
    url = f"/api/v1/git/{user.id}/notes.git/info/refs?service=git-upload-pack"

    record = await session.get(AccessToken, created["id"])
    assert record is not None
    record.expires_at = utcnow() - timedelta(seconds=1)
    await session.commit()
    assert (await api.get(url, headers=basic(created["token"]))).status_code == 401
    assert (await api.get("/api/v1/tokens")).json() == []

    record.expires_at = None
    await session.commit()
    assert (await api.get(url, headers=basic(created["token"]))).status_code == 200
    await api.delete(f"/api/v1/tokens/{created['id']}")
    assert (await api.get(url, headers=basic(created["token"]))).status_code == 401


# ---------- 快照与推送写回 ----------


def files_at(repo: Repo, commit_id: ObjectID) -> dict[str, bytes]:
    result = {}
    for e in iter_tree_contents(repo.object_store, g.tree_of(repo, commit_id)):
        assert e.path is not None and e.sha is not None
        blob = repo[e.sha]
        assert isinstance(blob, Blob)
        result[e.path.decode()] = blob.as_raw_string()
    return result


def make_commit(repo: Repo, parent: ObjectID, files: dict[str, bytes]) -> ObjectID:
    """模拟用户在本地提交后推送：对象已经写入服务器仓库，main 还没有更新。"""
    entries = []
    for path, data in files.items():
        blob = Blob.from_string(data)
        repo.object_store.add_object(blob)
        entries.append((path.encode(), blob.id, g.FILE_MODE))
    commit = Commit()
    commit.tree = commit_tree(repo.object_store, entries)
    commit.parents = [parent]
    commit.author = commit.committer = b"tester <t@example.com>"
    commit.author_time = commit.commit_time = int(time.time())
    commit.author_timezone = commit.commit_timezone = 0
    commit.message = b"local"
    repo.object_store.add_object(commit)
    return commit.id


async def web_setup(api: httpx.AsyncClient, session: AsyncSession) -> tuple[User, dict, dict]:
    user = await login_as(api, session)
    folder = (await api.post("/api/v1/folders", json={"name": "读书"})).json()
    note = (
        await api.post("/api/v1/notes", json={"title": "红楼梦", "folderId": folder["id"]})
    ).json()
    await api.put(f"/api/v1/notes/{note['id']}/content", json={"content": "正文\n", "version": 1})
    return user, folder, note


async def test_snapshot_follows_web_changes(api: httpx.AsyncClient, session: AsyncSession):
    user, _, note = await web_setup(api, session)
    await sync_snapshot(session, user.id)
    with g.open_repo(repo_dir(user.id)) as repo:
        first = g.head_of(repo)
        assert first is not None
        assert files_at(repo, first) == {"读书/红楼梦.md": "正文\n".encode()}

    await sync_snapshot(session, user.id)  # 没有新修改，不生成提交
    with g.open_repo(repo_dir(user.id)) as repo:
        assert g.head_of(repo) == first

    await api.patch(f"/api/v1/notes/{note['id']}", json={"title": "石头记"})
    await sync_snapshot(session, user.id)
    with g.open_repo(repo_dir(user.id)) as repo:
        head = g.head_of(repo)
        assert head is not None and head != first
        assert list(files_at(repo, head)) == ["读书/石头记.md"]


async def test_push_writes_back(api: httpx.AsyncClient, session: AsyncSession):
    user, folder, note = await web_setup(api, session)
    uid = user.id
    await sync_snapshot(session, uid)
    with g.open_repo(repo_dir(uid)) as repo:
        head = g.head_of(repo)
        assert head is not None
        new = make_commit(
            repo, head, {"工作/石头记.md": "正文\n".encode(), "Todo.md": b"- [ ] a\n"}
        )
        summary = await apply_push(session, uid, repo, head, new)
        assert g.head_of(repo) == new
    assert "新增 1 篇" in summary and "移动或重命名 1 篇" in summary

    session.expire_all()
    notes = {n.title: n for n in await session.scalars(select(Note))}
    folders = {f.id: f.name for f in await session.scalars(select(Folder))}
    assert notes["石头记"].id == note["id"]  # 笔记 id 不变，分享链接继续有效
    assert folders[notes["石头记"].folder_id or 0] == "工作"
    assert notes["Todo"].folder_id is None and notes["Todo"].content == "- [ ] a\n"
    assert folder["name"] not in folders.values()  # 仓库中消失的目录被删除

    # 写回后不需要再生成快照
    await sync_snapshot(session, uid)
    with g.open_repo(repo_dir(uid)) as repo:
        assert g.head_of(repo) == new


async def test_push_bumps_version_on_content_change(api: httpx.AsyncClient, session: AsyncSession):
    user, _, note = await web_setup(api, session)
    await sync_snapshot(session, user.id)
    with g.open_repo(repo_dir(user.id)) as repo:
        head = g.head_of(repo)
        assert head is not None
        new = make_commit(repo, head, {"读书/红楼梦.md": "改过的正文\n".encode()})
        await apply_push(session, user.id, repo, head, new)

    # 浏览器中还是旧版本，保存时冲突
    res = await api.put(f"/api/v1/notes/{note['id']}/content", json={"content": "x", "version": 2})
    assert res.status_code == 409


async def test_push_rejected_after_web_change(api: httpx.AsyncClient, session: AsyncSession):
    user, _, note = await web_setup(api, session)
    await sync_snapshot(session, user.id)
    await api.put(f"/api/v1/notes/{note['id']}/content", json={"content": "网页", "version": 2})

    with g.open_repo(repo_dir(user.id)) as repo:
        head = g.head_of(repo)
        assert head is not None
        new = make_commit(repo, head, {"读书/红楼梦.md": b"local"})
        with pytest.raises(g.PushRejected) as e:
            await apply_push(session, user.id, repo, head, new)
        await session.rollback()
        assert e.value.reason == "fetch first"
        assert g.head_of(repo) == head

    res = await api.get(f"/api/v1/notes/{note['id']}")
    assert res.json()["content"] == "网页"


async def test_push_rejects_invalid_content(api: httpx.AsyncClient, session: AsyncSession):
    user, _, _ = await web_setup(api, session)
    await sync_snapshot(session, user.id)
    with g.open_repo(repo_dir(user.id)) as repo:
        head = g.head_of(repo)
        assert head is not None
        new = make_commit(repo, head, {"读书/红楼梦.md": "正文\n".encode(), "a.png": b"x"})
        with pytest.raises(g.PushRejected) as e:
            await apply_push(session, user.id, repo, head, new)
        await session.rollback()
        assert e.value.details == ["a.png：只能包含 .md 文件和文件夹"]
        assert g.head_of(repo) == head
