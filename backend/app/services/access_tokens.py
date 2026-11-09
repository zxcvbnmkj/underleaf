"""个人访问令牌：生成、校验、HTTP Basic 认证（`git clone` 时作为密码使用）。

- 令牌格式 `ulp_` + 43 个随机字符（32 字节），数据库只存 SHA-256 哈希
- 不直接使用登录密码：令牌泄露后可以单独吊销，也不会暴露登录密码
"""

import base64
import binascii
import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccessToken, User

PREFIX = "ulp_"


def generate_token() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def utcnow() -> datetime:
    """数据库中存不带时区的 UTC 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


def is_active(token: AccessToken, now: datetime | None = None) -> bool:
    now = now or utcnow()
    return token.revoked_at is None and (token.expires_at is None or token.expires_at > now)


def parse_basic_auth(header: str | None) -> tuple[str, str] | None:
    """解析 `Authorization: Basic ...`，返回 (用户名, 密码)；格式不对时返回 None。"""
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "basic" or not value:
        return None
    try:
        decoded = base64.b64decode(value.strip(), validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None
    username, sep, password = decoded.partition(":")
    return (username, password) if sep else None


async def authenticate_token(session: AsyncSession, token: str) -> User | None:
    """按令牌查找用户；令牌不存在、已过期或已吊销时返回 None。成功时记录最近使用时间。"""
    if not token.startswith(PREFIX):
        return None
    row = (
        await session.execute(
            select(AccessToken, User)
            .join(User, User.id == AccessToken.user_id)
            .where(AccessToken.token_hash == hash_token(token))
        )
    ).first()
    if row is None:
        return None
    access_token, user = row
    now = utcnow()
    if not is_active(access_token, now):
        return None
    access_token.last_used_at = now
    return user
