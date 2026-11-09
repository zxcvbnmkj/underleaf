"""登录与账号（readme「登录」）。

- 注册：邮箱 + 验证码 + 昵称 + 密码
- 登录：邮箱 / 昵称 + 密码，或邮箱 + 验证码（邮箱未注册时提示先注册）
- 登录态：JWT 放在 httpOnly Cookie 中；修改 / 重置密码后其他设备的登录态失效
- 防暴力破解：不锁定账号，按 IP 限流（登录 10 次 / 分钟，发验证码 5 次 / 分钟）
"""

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, Session
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.core.security import burn_password_check, create_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import (
    ChangePasswordIn,
    CodeLoginIn,
    PasswordLoginIn,
    RegisterIn,
    ResetPasswordIn,
    SendCodeIn,
    UpdateMeIn,
    UserOut,
)
from app.services.email_codes import send_code, verify_code

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = AppError(401, "invalid_credentials", "账号或密码错误")


def _client_ip(request: Request) -> str:
    # 部署时 uvicorn 开启了 --proxy-headers，这里是 Nginx 转发来的真实 IP
    return request.client.host if request.client else "unknown"


def _login(response: Response, user: User) -> UserOut:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie,
        create_token(user.id, user.token_version),
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return UserOut.model_validate(user, from_attributes=True)


async def _user_by_email(session: Session, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


async def _user_by_nickname(session: Session, nickname: str) -> User | None:
    return await session.scalar(select(User).where(User.nickname == nickname))


async def _commit_unique(session: Session) -> None:
    """提交时处理邮箱 / 昵称唯一约束冲突（并发注册或改名时可能出现）。"""
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if "nickname" in str(e.orig):
            raise AppError(409, "nickname_taken", "这个昵称已被使用") from e
        raise AppError(409, "email_registered", "这个邮箱已注册，请直接登录") from e


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(body: UpdateMeIn, user: CurrentUser, session: Session) -> User:
    """修改昵称。"""
    if body.nickname != user.nickname:
        existing = await _user_by_nickname(session, body.nickname)
        if existing and existing.id != user.id:
            raise AppError(409, "nickname_taken", "这个昵称已被使用")
        user.nickname = body.nickname
        await _commit_unique(session)
    return user


@router.post("/email-code", status_code=204)
async def email_code(body: SendCodeIn, request: Request, session: Session) -> None:
    """发送验证码（登录、重置密码），邮箱必须已注册。"""
    await rate_limit(f"email-code:{_client_ip(request)}", 5, 60)
    if await _user_by_email(session, body.email) is None:
        raise AppError(404, "email_not_registered", "这个邮箱还没有注册")
    await send_code(body.email, body.purpose)


@router.post("/register", response_model=UserOut)
async def register(body: RegisterIn, response: Response, session: Session) -> UserOut:
    if await _user_by_email(session, body.email):
        raise AppError(409, "email_registered", "这个邮箱已注册，请直接登录")
    if await _user_by_nickname(session, body.nickname):
        raise AppError(409, "nickname_taken", "这个昵称已被使用")
    user = User(
        email=body.email,
        nickname=body.nickname,
        password_hash=await hash_password(body.password),
    )
    session.add(user)
    await _commit_unique(session)
    return _login(response, user)


@router.post("/login/email-code", response_model=UserOut)
async def login_with_code(
    body: CodeLoginIn, request: Request, response: Response, session: Session
) -> UserOut:
    await rate_limit(f"login:{_client_ip(request)}", 10, 60, "登录尝试太频繁，请稍后再试")
    user = await _user_by_email(session, body.email)
    if user is None:
        raise AppError(404, "email_not_registered", "这个邮箱还没有注册")
    await verify_code(body.email, "login", body.code)
    return _login(response, user)


@router.post("/login/password", response_model=UserOut)
async def login_with_password(
    body: PasswordLoginIn, request: Request, response: Response, session: Session
) -> UserOut:
    await rate_limit(f"login:{_client_ip(request)}", 10, 60, "登录尝试太频繁，请稍后再试")
    account = body.account.strip()
    user = (
        await _user_by_email(session, account.lower())
        if "@" in account
        else await _user_by_nickname(session, account)
    )
    if user is None:
        await burn_password_check(body.password)
        raise INVALID_CREDENTIALS
    if not await verify_password(body.password, user.password_hash):
        raise INVALID_CREDENTIALS
    return _login(response, user)


@router.post("/password/reset", status_code=204)
async def reset_password(body: ResetPasswordIn, session: Session) -> None:
    """通过邮箱验证码重置密码；所有设备上的登录态失效，需要用新密码重新登录。"""
    user = await _user_by_email(session, body.email)
    if user is None:
        raise AppError(404, "email_not_registered", "这个邮箱还没有注册")
    await verify_code(body.email, "reset_password", body.code)
    user.password_hash = await hash_password(body.new_password)
    user.token_version += 1
    await session.commit()


@router.put("/password", response_model=UserOut)
async def change_password(
    body: ChangePasswordIn, user: CurrentUser, response: Response, session: Session
) -> UserOut:
    """修改密码：其他设备上的登录态失效，当前设备保持登录。"""
    if not await verify_password(body.old_password, user.password_hash):
        raise AppError(400, "wrong_password", "原密码不正确")
    user.password_hash = await hash_password(body.new_password)
    user.token_version += 1
    await session.commit()
    return _login(response, user)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
