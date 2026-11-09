"""邮箱验证码，存在 Redis 中（readme「登录」）。

- 6 位数字，只存 HMAC 哈希，5 分钟有效（TTL 自动过期）
- 同一邮箱 60 秒内只能发送一次（不区分用途）
- 按用途（注册 / 登录 / 重置密码）分开存放，不能混用
- 连续输错 5 次作废；验证成功后立即删除（只能用一次）
"""

import hashlib
import hmac
import secrets
from typing import Literal

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.redis import redis
from app.services.mailer import send_mail

Purpose = Literal["login", "reset_password"]

CODE_TTL = 5 * 60
COOLDOWN = 60
MAX_ATTEMPTS = 5

_PURPOSE_TEXT: dict[Purpose, str] = {
    "login": "登录",
    "reset_password": "重置密码",
}


def _code_key(purpose: Purpose, email: str) -> str:
    return f"underleaf:code:{purpose}:{email}"


def _cooldown_key(email: str) -> str:
    return f"underleaf:code-cooldown:{email}"


def _digest(email: str, code: str) -> str:
    secret = get_settings().jwt_secret.encode()
    return hmac.new(secret, f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


async def send_code(email: str, purpose: Purpose) -> None:
    # SET NX 同时完成「检查冷却」和「开始冷却」，并发请求也只有一个能通过
    if not await redis.set(_cooldown_key(email), "1", ex=COOLDOWN, nx=True):
        ttl = await redis.ttl(_cooldown_key(email))
        raise AppError(
            429,
            "code_cooldown",
            f"验证码发送太频繁，请 {max(ttl, 1)} 秒后再试",
            {"retryAfter": ttl},
        )

    code = f"{secrets.randbelow(10**6):06d}"
    key = _code_key(purpose, email)
    await redis.delete(key)
    await redis.hset(key, mapping={"digest": _digest(email, code), "attempts": 0})  # pyright: ignore[reportGeneralTypeIssues]
    await redis.expire(key, CODE_TTL)
    try:
        await send_mail(
            email,
            f"Underleaf 验证码：{code}",
            f"你正在{_PURPOSE_TEXT[purpose]}，验证码为：{code}\n\n"
            f"验证码 {CODE_TTL // 60} 分钟内有效。"
            "如果不是你本人操作，请忽略这封邮件。\n\n— Underleaf",
        )
    except AppError:
        # 没发出去：撤销验证码和冷却，允许立即重试
        await redis.delete(key, _cooldown_key(email))
        raise


async def verify_code(email: str, purpose: Purpose, code: str) -> None:
    """校验验证码，正确时作废；错误时抛出 AppError。"""
    key = _code_key(purpose, email)
    # Redis 客户端开启了 decode_responses，返回的是 str
    digest = await redis.hget(key, "digest")  # pyright: ignore[reportGeneralTypeIssues]
    if not isinstance(digest, str):
        raise AppError(400, "code_invalid", "验证码错误或已过期，请重新获取")
    if hmac.compare_digest(digest, _digest(email, code.strip())):
        await redis.delete(key)
        return
    attempts = await redis.hincrby(key, "attempts", 1)  # pyright: ignore[reportGeneralTypeIssues]
    if attempts >= MAX_ATTEMPTS:
        await redis.delete(key)
        raise AppError(400, "code_invalid", "验证码错误次数过多，请重新获取")
    raise AppError(400, "code_invalid", f"验证码错误，还可以再试 {MAX_ATTEMPTS - attempts} 次")
