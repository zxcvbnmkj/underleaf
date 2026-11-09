"""登录与账号：使用真实的 MySQL 测试库和 Redis，邮件发送替换为记录验证码。"""

import re
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.db import get_session
from app.main import app
from app.services import email_codes

PASSWORD = "correct-horse-1"


class Mailbox:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    async def send(self, to: str, subject: str, text: str) -> None:
        match = re.search(r"\d{6}", subject)
        assert match
        self.codes[to] = match.group()


@pytest.fixture
async def mailbox(monkeypatch: pytest.MonkeyPatch) -> Mailbox:
    box = Mailbox()
    monkeypatch.setattr(email_codes, "send_mail", box.send)
    return box


@pytest.fixture
async def client(engine: AsyncEngine, session: object) -> AsyncIterator[httpx.AsyncClient]:
    """使用测试库的接口客户端（session 夹具负责在测试结束后清空数据）。"""
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def test_session() -> AsyncIterator[object]:
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = test_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def register(
    c: httpx.AsyncClient, box: Mailbox, email: str = "alice@example.com", nickname: str = "爱丽丝"
) -> httpx.Response:
    res = await c.post("/api/v1/auth/email-code", json={"email": email, "purpose": "register"})
    assert res.status_code == 204, res.text
    return await c.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "code": box.codes[email.lower()],
            "nickname": nickname,
            "password": PASSWORD,
        },
    )


# ---------- 注册 ----------


async def test_register_logs_in(client: httpx.AsyncClient, mailbox: Mailbox):
    res = await register(client, mailbox, email="Alice@Example.com")
    assert res.status_code == 200, res.text
    assert res.json()["email"] == "alice@example.com"  # 邮箱统一小写
    assert "underleaf_session" in res.cookies
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie

    me = await client.get("/api/v1/auth/me")
    assert me.json() == {"id": res.json()["id"], "email": "alice@example.com", "nickname": "爱丽丝"}


async def test_register_code_is_single_use(client: httpx.AsyncClient, mailbox: Mailbox):
    await register(client, mailbox)
    res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@example.com",
            "code": mailbox.codes["alice@example.com"],
            "nickname": "bob",
            "password": PASSWORD,
        },
    )
    assert res.json()["code"] == "code_invalid"  # 验证码与邮箱绑定，且已用过


async def test_register_conflicts(client: httpx.AsyncClient, mailbox: Mailbox):
    await register(client, mailbox)
    res = await client.post(
        "/api/v1/auth/email-code", json={"email": "alice@example.com", "purpose": "register"}
    )
    assert res.status_code == 409 and res.json()["code"] == "email_registered"

    res = await register(client, mailbox, email="bob@example.com", nickname="爱丽丝")
    assert res.status_code == 409 and res.json()["code"] == "nickname_taken"


@pytest.mark.parametrize(
    ("nickname", "password", "message"),
    [
        ("a", PASSWORD, "昵称为 2～20 个字符"),
        ("有@符号", PASSWORD, "昵称为 2～20 个字符"),
        ("有 空格", PASSWORD, "昵称为 2～20 个字符"),
        ("正常昵称", "short", "密码至少 8 个字符"),
    ],
)
async def test_register_validation(
    client: httpx.AsyncClient, mailbox: Mailbox, nickname: str, password: str, message: str
):
    res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "x@example.com",
            "code": "123456",
            "nickname": nickname,
            "password": password,
        },
    )
    assert res.status_code == 422
    assert res.json()["message"].startswith(message)


# ---------- 登录 ----------


async def test_password_login_with_email_or_nickname(client: httpx.AsyncClient, mailbox: Mailbox):
    await register(client, mailbox)
    await client.post("/api/v1/auth/logout")
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    for account in ("ALICE@example.com", "爱丽丝"):
        res = await client.post(
            "/api/v1/auth/login/password", json={"account": account, "password": PASSWORD}
        )
        assert res.status_code == 200, account

    for account, password in (("爱丽丝", "wrong-password"), ("nobody", PASSWORD)):
        res = await client.post(
            "/api/v1/auth/login/password", json={"account": account, "password": password}
        )
        assert res.status_code == 401
        assert res.json()["message"] == "账号或密码错误"  # 不透露账号是否存在


async def test_code_login(client: httpx.AsyncClient, mailbox: Mailbox):
    res = await client.post(
        "/api/v1/auth/email-code", json={"email": "new@example.com", "purpose": "login"}
    )
    assert res.status_code == 404 and res.json()["code"] == "email_not_registered"

    await register(client, mailbox)
    await client.post("/api/v1/auth/logout")
    await email_codes.redis.delete("underleaf:code-cooldown:alice@example.com")  # 跳过 60 秒冷却
    await client.post(
        "/api/v1/auth/email-code", json={"email": "alice@example.com", "purpose": "login"}
    )
    res = await client.post(
        "/api/v1/auth/login/email-code",
        json={"email": "alice@example.com", "code": mailbox.codes["alice@example.com"]},
    )
    assert res.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_code_wrong_attempts_and_cooldown(client: httpx.AsyncClient, mailbox: Mailbox):
    await register(client, mailbox)
    await email_codes.redis.delete("underleaf:code-cooldown:alice@example.com")
    send = {"email": "alice@example.com", "purpose": "login"}
    await client.post("/api/v1/auth/email-code", json=send)

    # 60 秒内不能再次发送
    again = await client.post("/api/v1/auth/email-code", json=send)
    assert again.status_code == 429 and again.json()["code"] == "code_cooldown"

    real = mailbox.codes["alice@example.com"]
    wrong = "000000" if real != "000000" else "111111"
    messages = []
    for _ in range(5):
        res = await client.post(
            "/api/v1/auth/login/email-code", json={"email": "alice@example.com", "code": wrong}
        )
        messages.append(res.json()["message"])
    assert messages[0] == "验证码错误，还可以再试 4 次"
    assert messages[-1] == "验证码错误次数过多，请重新获取"
    # 输错 5 次后，正确的验证码也已作废
    res = await client.post(
        "/api/v1/auth/login/email-code", json={"email": "alice@example.com", "code": real}
    )
    assert res.status_code == 400


async def test_codes_are_separated_by_purpose(client: httpx.AsyncClient, mailbox: Mailbox):
    await register(client, mailbox)
    await email_codes.redis.delete("underleaf:code-cooldown:alice@example.com")
    await client.post(
        "/api/v1/auth/email-code", json={"email": "alice@example.com", "purpose": "reset_password"}
    )
    res = await client.post(
        "/api/v1/auth/login/email-code",
        json={"email": "alice@example.com", "code": mailbox.codes["alice@example.com"]},
    )
    assert res.status_code == 400  # 重置密码的验证码不能用来登录


async def test_login_rate_limit(client: httpx.AsyncClient):
    statuses = [
        (
            await client.post(
                "/api/v1/auth/login/password", json={"account": "nobody", "password": "x"}
            )
        ).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


# ---------- 密码 ----------


async def test_reset_password_logs_out_everywhere(client: httpx.AsyncClient, mailbox: Mailbox):
    await register(client, mailbox)
    old_cookie = client.cookies.get("underleaf_session")
    await email_codes.redis.delete("underleaf:code-cooldown:alice@example.com")
    await client.post(
        "/api/v1/auth/email-code", json={"email": "alice@example.com", "purpose": "reset_password"}
    )
    res = await client.post(
        "/api/v1/auth/password/reset",
        json={
            "email": "alice@example.com",
            "code": mailbox.codes["alice@example.com"],
            "newPassword": "brand-new-password",
        },
    )
    assert res.status_code == 204

    client.cookies.set("underleaf_session", old_cookie or "")
    assert (await client.get("/api/v1/auth/me")).status_code == 401  # 旧登录态失效
    res = await client.post(
        "/api/v1/auth/login/password",
        json={"account": "爱丽丝", "password": "brand-new-password"},
    )
    assert res.status_code == 200


async def test_change_password_keeps_current_device(client: httpx.AsyncClient, mailbox: Mailbox):
    await register(client, mailbox)
    other_device = client.cookies.get("underleaf_session")

    res = await client.put(
        "/api/v1/auth/password", json={"oldPassword": "wrong", "newPassword": "another-password"}
    )
    assert res.status_code == 400 and res.json()["code"] == "wrong_password"

    res = await client.put(
        "/api/v1/auth/password", json={"oldPassword": PASSWORD, "newPassword": "another-password"}
    )
    assert res.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200  # 当前设备拿到新令牌

    client.cookies.set("underleaf_session", other_device or "")
    assert (await client.get("/api/v1/auth/me")).status_code == 401  # 其他设备失效


# ---------- 其他 ----------


async def test_update_nickname(client: httpx.AsyncClient, mailbox: Mailbox):
    await register(client, mailbox, email="bob@example.com", nickname="鲍勃")
    await client.post("/api/v1/auth/logout")
    await register(client, mailbox)

    res = await client.patch("/api/v1/auth/me", json={"nickname": "鲍勃"})
    assert res.status_code == 409
    res = await client.patch("/api/v1/auth/me", json={"nickname": "新名字"})
    assert res.json()["nickname"] == "新名字"


async def test_protected_endpoints_require_login(client: httpx.AsyncClient):
    for method, path in (
        ("GET", "/api/v1/auth/me"),
        ("POST", "/api/v1/images"),
        ("POST", "/api/v1/export/pdf"),
        ("POST", "/api/v1/export/docx"),
    ):
        res = await client.request(method, path, json={"title": "t", "content": "x"})
        assert res.status_code == 401, path
        assert res.json()["code"] == "unauthorized"


async def test_tampered_token_rejected(client: httpx.AsyncClient):
    client.cookies.set("underleaf_session", "not-a-valid-token")
    assert (await client.get("/api/v1/auth/me")).status_code == 401
