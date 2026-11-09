"""接口依赖：数据库会话、当前登录用户。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import decode_token
from app.models import User

Session = Annotated[AsyncSession, Depends(get_session)]


async def current_user(request: Request, session: Session) -> User:
    """从 Cookie 中的令牌取当前用户；未登录、令牌无效或已因改密码失效时返回 401。"""
    token = request.cookies.get(get_settings().session_cookie)
    payload = decode_token(token) if token else None
    user = await session.get(User, payload.user_id) if payload else None
    if user is None or payload is None or user.token_version != payload.token_version:
        raise AppError(401, "unauthorized", "请先登录")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
