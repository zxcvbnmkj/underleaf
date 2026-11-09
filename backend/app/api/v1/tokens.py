"""个人访问令牌管理（网页登录态），以及 Git 同步的连接信息。"""

from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, Session
from app.core.errors import AppError
from app.models import AccessToken
from app.schemas.tokens import GitInfoOut, TokenCreate, TokenOut
from app.services.access_tokens import (
    decrypt_token,
    encrypt_token,
    generate_token,
    hash_token,
    is_active,
    utcnow,
)
from app.services.git_sync import clone_path

router = APIRouter(tags=["git"])

# 每个用户最多同时有效的令牌数
MAX_ACTIVE_TOKENS = 20


@router.get("/git/info", response_model=GitInfoOut)
async def git_info(user: CurrentUser) -> GitInfoOut:
    return GitInfoOut(clone_path=clone_path(user.id), username=user.nickname)


def _out(record: AccessToken) -> TokenOut:
    return TokenOut(
        id=record.id,
        name=record.name,
        last_chars=record.last_chars,
        token=decrypt_token(record.token_encrypted),
        expires_at=record.expires_at,
        last_used_at=record.last_used_at,
        created_at=record.created_at,
    )


@router.get("/tokens", response_model=list[TokenOut])
async def list_tokens(user: CurrentUser, session: Session) -> list[TokenOut]:
    """有效的令牌（不含已吊销和已过期的），最新的在前，包含完整令牌。"""
    rows = await session.scalars(
        select(AccessToken)
        .where(AccessToken.user_id == user.id, AccessToken.revoked_at.is_(None))
        .order_by(AccessToken.id.desc())
    )
    now = utcnow()
    return [_out(t) for t in rows if is_active(t, now)]


@router.post("/tokens", response_model=TokenOut)
async def create_token(body: TokenCreate, user: CurrentUser, session: Session) -> TokenOut:
    name = body.name.strip()
    if not name:
        raise AppError(422, "invalid_name", "请填写令牌名称")
    now = utcnow()
    active = await session.scalar(
        select(func.count())
        .select_from(AccessToken)
        .where(
            AccessToken.user_id == user.id,
            AccessToken.revoked_at.is_(None),
            (AccessToken.expires_at.is_(None)) | (AccessToken.expires_at > now),
        )
    )
    if (active or 0) >= MAX_ACTIVE_TOKENS:
        raise AppError(
            400, "too_many_tokens", f"最多保留 {MAX_ACTIVE_TOKENS} 个令牌，请先吊销不用的"
        )

    token = generate_token()
    record = AccessToken(
        user_id=user.id,
        name=name,
        token_hash=hash_token(token),
        token_encrypted=encrypt_token(token),
        last_chars=token[-4:],
        expires_at=now + timedelta(days=body.expires_in_days) if body.expires_in_days else None,
    )
    session.add(record)
    await session.commit()
    return _out(record)


@router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(token_id: int, user: CurrentUser, session: Session) -> None:
    record = await session.get(AccessToken, token_id)
    if record is None or record.user_id != user.id:
        raise AppError(404, "not_found", "令牌不存在")
    if record.revoked_at is None:
        record.revoked_at = utcnow()
        await session.commit()
