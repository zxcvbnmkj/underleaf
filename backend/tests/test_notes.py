"""文件夹、笔记、公开分享接口（真实 MySQL 测试库）。"""

import re

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import User
from tests.conftest import login_as

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def content_rev(session: AsyncSession, user: User) -> int:
    await session.commit()  # 结束当前事务，才能读到接口在其他连接中提交的修改
    await session.refresh(user)
    return user.content_rev


# ---------- 文件夹 ----------


async def test_folder_crud(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session)
    top = (await api.post("/api/v1/folders", json={"name": "  读书  ", "parentId": None})).json()
    assert top["name"] == "读书" and top["parentId"] is None
    child = (await api.post("/api/v1/folders", json={"name": "小说", "parentId": top["id"]})).json()
    assert child["parentId"] == top["id"]

    res = await api.patch(f"/api/v1/folders/{child['id']}", json={"name": "长篇小说"})
    assert (
        res.json()["name"] == "长篇小说" and res.json()["parentId"] == top["id"]
    )  # 未传 parentId 不移动

    res = await api.patch(f"/api/v1/folders/{child['id']}", json={"parentId": None})
    assert res.json()["parentId"] is None  # 显式传 null 表示移到根目录

    folders = (await api.get("/api/v1/folders")).json()
    assert {f["name"] for f in folders} == {"读书", "长篇小说"}


async def test_folder_name_rules(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session)
    await api.post("/api/v1/folders", json={"name": "Notes"})
    res = await api.post("/api/v1/folders", json={"name": "notes"})  # 不区分大小写
    assert res.status_code == 409 and res.json()["code"] == "name_taken"

    for bad in ("", "   ", "a/b", "c:d", "..", "长" * 81):
        res = await api.post("/api/v1/folders", json={"name": bad})
        assert res.status_code == 422, bad
        assert res.json()["code"] == "invalid_name"


async def test_folder_move_rules(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session)
    a = (await api.post("/api/v1/folders", json={"name": "A"})).json()
    b = (await api.post("/api/v1/folders", json={"name": "B", "parentId": a["id"]})).json()

    for target in (a["id"], b["id"]):  # 移到自己或自己的子文件夹下
        res = await api.patch(f"/api/v1/folders/{a['id']}", json={"parentId": target})
        assert res.status_code == 400 and res.json()["code"] == "invalid_move"


async def test_folder_depth_limit(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session)
    parent = None
    ids = []
    for i in range(10):
        res = await api.post("/api/v1/folders", json={"name": f"L{i}", "parentId": parent})
        assert res.status_code == 200
        parent = res.json()["id"]
        ids.append(parent)
    res = await api.post("/api/v1/folders", json={"name": "L10", "parentId": parent})
    assert res.status_code == 400 and res.json()["code"] == "too_deep"

    # 把一个两层的子树移到第 9 层下面会超过 10 层
    x = (await api.post("/api/v1/folders", json={"name": "X"})).json()
    await api.post("/api/v1/folders", json={"name": "Y", "parentId": x["id"]})
    res = await api.patch(f"/api/v1/folders/{x['id']}", json={"parentId": ids[8]})
    assert res.status_code == 400 and res.json()["code"] == "too_deep"


async def test_delete_folder_cascades(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session)
    top = (await api.post("/api/v1/folders", json={"name": "top"})).json()
    sub = (await api.post("/api/v1/folders", json={"name": "sub", "parentId": top["id"]})).json()
    await api.post("/api/v1/notes", json={"title": "里面的笔记", "folderId": sub["id"]})
    await api.post("/api/v1/notes", json={"title": "根目录笔记"})

    assert (await api.delete(f"/api/v1/folders/{top['id']}")).status_code == 204
    assert (await api.get("/api/v1/folders")).json() == []
    assert [n["title"] for n in (await api.get("/api/v1/notes")).json()] == ["根目录笔记"]


# ---------- 笔记 ----------


async def test_note_lifecycle(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session)
    note = (await api.post("/api/v1/notes", json={"title": "第一篇"})).json()
    assert note["version"] == 1 and note["content"] == "" and note["isPublic"] is False
    assert len(note["publicId"]) == 12
    assert ISO_UTC.match(note["createdAt"]) and ISO_UTC.match(note["updatedAt"])

    listed = (await api.get("/api/v1/notes")).json()
    assert len(listed) == 1 and "content" not in listed[0]  # 列表不含正文

    res = await api.put(
        f"/api/v1/notes/{note['id']}/content", json={"content": "# 你好 🎉", "version": 1}
    )
    assert res.status_code == 200 and res.json()["version"] == 2
    full = (await api.get(f"/api/v1/notes/{note['id']}")).json()
    assert full["content"] == "# 你好 🎉" and full["version"] == 2

    assert (await api.delete(f"/api/v1/notes/{note['id']}")).status_code == 204
    assert (await api.get(f"/api/v1/notes/{note['id']}")).status_code == 404


async def test_new_note_titles_avoid_duplicates(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session)
    titles = [(await api.post("/api/v1/notes", json={})).json()["title"] for _ in range(3)]
    assert titles == ["未命名笔记", "未命名笔记 2", "未命名笔记 3"]

    folder = (await api.post("/api/v1/folders", json={"name": "F"})).json()
    note = (await api.post("/api/v1/notes", json={"folderId": folder["id"]})).json()
    assert note["title"] == "未命名笔记"  # 不同文件夹互不影响


async def test_rename_and_move_conflicts(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session)
    folder = (await api.post("/api/v1/folders", json={"name": "F"})).json()
    a = (await api.post("/api/v1/notes", json={"title": "同名"})).json()
    b = (await api.post("/api/v1/notes", json={"title": "同名", "folderId": folder["id"]})).json()
    other = (await api.post("/api/v1/notes", json={"title": "其他"})).json()

    res = await api.patch(f"/api/v1/notes/{b['id']}", json={"folderId": None})
    assert res.status_code == 409 and res.json()["code"] == "name_taken"
    res = await api.patch(f"/api/v1/notes/{other['id']}", json={"title": "同名"})
    assert res.status_code == 409

    res = await api.patch(f"/api/v1/notes/{a['id']}", json={"folderId": folder["id"]})
    assert res.status_code == 409  # 文件夹里已有「同名」
    res = await api.patch(
        f"/api/v1/notes/{a['id']}", json={"title": "改个名", "folderId": folder["id"]}
    )
    assert res.status_code == 200 and res.json()["folderId"] == folder["id"]


async def test_optimistic_lock(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session)
    note = (await api.post("/api/v1/notes", json={"title": "冲突"})).json()
    url = f"/api/v1/notes/{note['id']}/content"

    assert (await api.put(url, json={"content": "设备 A", "version": 1})).status_code == 200
    res = await api.put(url, json={"content": "设备 B", "version": 1})  # B 还拿着旧版本号
    assert res.status_code == 409 and res.json()["code"] == "version_conflict"
    assert (await api.get(f"/api/v1/notes/{note['id']}")).json()["content"] == "设备 A"


async def test_content_size_limit(
    api: httpx.AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    await login_as(api, session)
    monkeypatch.setattr(get_settings(), "note_max_bytes", 10)
    note = (await api.post("/api/v1/notes", json={"title": "大"})).json()
    res = await api.put(
        f"/api/v1/notes/{note['id']}/content", json={"content": "x" * 11, "version": 1}
    )
    assert res.status_code == 413


async def test_users_cannot_see_each_other(api: httpx.AsyncClient, session: AsyncSession):
    await login_as(api, session, "alice")
    folder = (await api.post("/api/v1/folders", json={"name": "私人"})).json()
    note = (await api.post("/api/v1/notes", json={"title": "秘密"})).json()

    await login_as(api, session, "bob")
    assert (await api.get("/api/v1/notes")).json() == []
    assert (await api.get("/api/v1/folders")).json() == []
    for method, path, body in (
        ("GET", f"/api/v1/notes/{note['id']}", None),
        ("PATCH", f"/api/v1/notes/{note['id']}", {"title": "x"}),
        ("PUT", f"/api/v1/notes/{note['id']}/content", {"content": "x", "version": 1}),
        ("DELETE", f"/api/v1/notes/{note['id']}", None),
        ("PATCH", f"/api/v1/folders/{folder['id']}", {"name": "x"}),
        ("DELETE", f"/api/v1/folders/{folder['id']}", None),
        ("POST", "/api/v1/notes", {"title": "x", "folderId": folder["id"]}),
    ):
        res = await api.request(method, path, json=body)
        assert res.status_code == 404, (method, path)


async def test_content_rev_counts_content_changes(api: httpx.AsyncClient, session: AsyncSession):
    user = await login_as(api, session)
    assert await content_rev(session, user) == 0
    note = (await api.post("/api/v1/notes", json={"title": "t"})).json()
    await api.put(f"/api/v1/notes/{note['id']}/content", json={"content": "x", "version": 1})
    assert await content_rev(session, user) == 2

    await api.patch(f"/api/v1/notes/{note['id']}", json={"isPublic": True})
    assert await content_rev(session, user) == 2  # 只是分享开关，不算内容变动


# ---------- 公开分享 ----------


async def test_share(api: httpx.AsyncClient, session: AsyncSession):
    author = await login_as(api, session, "作者")
    author_cookie = api.cookies.get(get_settings().session_cookie)
    note = (await api.post("/api/v1/notes", json={"title": "公开的笔记"})).json()
    await api.put(f"/api/v1/notes/{note['id']}/content", json={"content": "正文", "version": 1})
    url = f"/api/v1/share/{note['publicId']}"

    api.cookies.clear()  # 分享页不需要登录
    assert (await api.get(url)).status_code == 404  # 未公开

    await login_as(api, session, "其他人")  # 别人不能替作者打开分享
    res = await api.patch(f"/api/v1/notes/{note['id']}", json={"isPublic": True})
    assert res.status_code == 404

    api.cookies.set(get_settings().session_cookie, author_cookie or "")
    res = await api.patch(f"/api/v1/notes/{note['id']}", json={"isPublic": True})
    assert res.status_code == 200 and res.json()["isPublic"] is True

    api.cookies.clear()
    shared = (await api.get(url)).json()
    assert shared["title"] == "公开的笔记" and shared["content"] == "正文"
    assert shared["author"] == {"nickname": author.nickname}
    assert author.email not in str(shared)  # 不暴露作者邮箱
    assert ISO_UTC.match(shared["createdAt"]) and ISO_UTC.match(shared["updatedAt"])
    assert (await api.get("/api/v1/share/notexist1234")).status_code == 404


async def test_requires_login(api: httpx.AsyncClient):
    for method, path in (("GET", "/api/v1/notes"), ("GET", "/api/v1/folders")):
        assert (await api.request(method, path)).status_code == 401
