"""Git Smart HTTP 接口：git clone / pull / push 地址为 {网站}/api/v1/git/{user_id}/notes.git。

认证使用 HTTP Basic：用户名随意，密码为个人访问令牌。只支持 Smart HTTP（Git 1.6.6 以上）。
"""

import asyncio
import zlib

from dulwich.repo import Repo
from fastapi import APIRouter, Request, Response
from sqlalchemy.exc import OperationalError

from app.api.deps import Session
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.models import User
from app.services import git_http
from app.services import git_repo as g
from app.services.access_tokens import authenticate_token, parse_basic_auth
from app.services.git_sync import apply_push, repo_dir, sync_snapshot

router = APIRouter(prefix="/git/{user_id}/notes.git", tags=["git"], include_in_schema=False)

_CHALLENGE = {"WWW-Authenticate": 'Basic realm="Underleaf", charset="UTF-8"'}
_NO_CACHE = {"Cache-Control": "no-cache, max-age=0, must-revalidate", "Expires": "0"}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _git_user(request: Request, session: Session, user_id: int) -> User:
    """HTTP Basic 认证：密码为访问令牌。git 客户端第一次请求不带凭据，收到 401 后才会提供。"""
    credentials = parse_basic_auth(request.headers.get("authorization"))
    if credentials is None:
        raise AppError(401, "unauthorized", "请使用访问令牌作为密码", headers=_CHALLENGE)
    user = await authenticate_token(session, credentials[1])
    if user is None:
        await rate_limit(f"git-auth:{_client_ip(request)}", 20, 600, "认证失败次数太多，请稍后再试")
        raise AppError(401, "invalid_token", "访问令牌无效、已过期或已被吊销", headers=_CHALLENGE)
    if user.id != user_id:
        raise AppError(404, "not_found", "仓库不存在")
    await session.commit()  # 保存最近使用时间，并结束事务（之后要加锁读取）
    return user


def _check_service(service: str | None) -> str:
    if service not in git_http.SERVICES:
        raise AppError(403, "unsupported", "只支持 Git Smart HTTP 协议，请升级 Git")
    return service


async def _read_body(request: Request, limit: int) -> bytes:
    """读取请求体（git 可能用 gzip 压缩），超过上限时中止。"""
    too_large = AppError(413, "too_large", f"推送的内容不能超过 {limit // 1024 // 1024}MB")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise too_large
        chunks.append(chunk)
    body = b"".join(chunks)
    if request.headers.get("content-encoding", "").lower() in ("gzip", "x-gzip"):
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            body = decompressor.decompress(body, limit + 1)
        except zlib.error as e:
            raise AppError(400, "bad_request", "请求体解压失败") from e
        if len(body) > limit or decompressor.unconsumed_tail:
            raise too_large
    return body


@router.get("/info/refs")
async def info_refs(
    user_id: int, request: Request, session: Session, service: str | None = None
) -> Response:
    """clone / fetch / push 的第一步：列出分支。网页上有新修改时先生成快照提交。"""
    service = _check_service(service)
    await _git_user(request, session, user_id)
    try:
        await sync_snapshot(session, user_id)
    except OperationalError as e:
        raise AppError(503, "busy", "服务器繁忙，请稍后重试") from e

    def run() -> bytes:
        with g.open_repo(repo_dir(user_id)) as repo:
            return git_http.advertise_refs(repo, service)

    return Response(
        await asyncio.to_thread(run),
        media_type=f"application/x-{service}-advertisement",
        headers=_NO_CACHE,
    )


@router.post("/{service}")
async def rpc(user_id: int, service: str, request: Request, session: Session) -> Response:
    """git-upload-pack（clone / fetch 下载数据）或 git-receive-pack（push 上传数据）。"""
    if service not in git_http.SERVICES:
        raise AppError(404, "not_found", "接口不存在")
    if request.headers.get("content-type") != f"application/x-{service}-request":
        raise AppError(415, "unsupported_media_type", "Content-Type 不正确")
    await _git_user(request, session, user_id)
    settings = get_settings()
    if service == git_http.RECEIVE_PACK:
        await rate_limit(f"git-push:{user_id}", 30, 60, "推送太频繁，请稍后再试")
    body = await _read_body(request, settings.git_max_push_bytes)
    loop = asyncio.get_running_loop()

    def run() -> bytes:
        with g.open_repo(repo_dir(user_id)) as repo:
            if service == git_http.UPLOAD_PACK:
                return git_http.handle_rpc(repo, service, body)

            def on_push(refs: list[git_http.RefUpdate]) -> git_http.PushResult:
                # 在线程中收到数据包后，回到事件循环中执行数据库写回
                coro = _handle_push(session, user_id, repo, refs)
                return asyncio.run_coroutine_threadsafe(coro, loop).result()

            return git_http.handle_rpc(
                repo, service, body, on_push, max_input_size=settings.git_max_push_bytes
            )

    return Response(
        await asyncio.to_thread(run),
        media_type=f"application/x-{service}-result",
        headers=_NO_CACHE,
    )


async def _handle_push(
    session: Session, user_id: int, repo: Repo, refs: list[git_http.RefUpdate]
) -> git_http.PushResult:
    if len(refs) != 1 or refs[0][2] != g.BRANCH:
        return git_http.PushResult(
            "only main", ["Underleaf：只能推送 main 分支（不支持其他分支和标签）"]
        )
    old, new, _ = refs[0]
    if new == git_http.ZERO_SHA:
        return git_http.PushResult("cannot delete", ["Underleaf：不能删除 main 分支"])
    try:
        summary = await apply_push(session, user_id, repo, old, new)
    except g.PushRejected as e:
        await session.rollback()
        return git_http.PushResult(e.reason, [f"Underleaf：{line}" for line in e.details])
    except OperationalError:  # 死锁、锁等待超时
        await session.rollback()
        return git_http.PushResult("busy", ["Underleaf：服务器繁忙，请稍后重试"])
    return git_http.PushResult(None, [summary])
