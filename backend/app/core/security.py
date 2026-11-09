"""密码哈希与登录令牌。

- 密码：Argon2（pwdlib）。哈希计算耗 CPU，放到线程中执行，避免阻塞事件循环
- 令牌：JWT（HS256），放在 httpOnly Cookie 中。载荷中的 ver 对应 user.token_version，
  修改 / 重置密码时版本加 1，之前签发的令牌全部失效
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_hasher = PasswordHash.recommended()
ALGORITHM = "HS256"


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(_hasher.verify, password, password_hash)


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash("underleaf-dummy-password")


async def burn_password_check(password: str) -> None:
    """账号不存在时也做一次同样耗时的校验，避免通过响应时间判断账号是否存在。"""
    await verify_password(password, await asyncio.to_thread(_dummy_hash))


@dataclass
class TokenPayload:
    user_id: int
    token_version: int


def create_token(user_id: int, token_version: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(days=settings.session_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenPayload | None:
    try:
        data = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
        return TokenPayload(user_id=int(data["sub"]), token_version=int(data["ver"]))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None
