"""统一错误响应：{ "code": ..., "message": ..., "detail": ... }。

业务代码中抛出 AppError，由 register_error_handlers 注册的处理器转换为 JSON。
message 直接展示给用户，使用中文；code 供前端按类型处理。
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        detail: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail
        self.headers = headers


def _response(
    status: int,
    code: str,
    message: str,
    detail: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "detail": detail},
        headers=headers,
    )


_FIELD_NAMES = {
    "email": "邮箱",
    "password": "密码",
    "newPassword": "新密码",
    "oldPassword": "原密码",
    "nickname": "昵称",
    "code": "验证码",
    "account": "账号",
    "title": "标题",
    "content": "内容",
}


def _friendly(error: Any) -> str:
    """把 Pydantic 的英文校验信息转成中文提示。"""
    field = str(error["loc"][-1]) if error.get("loc") else ""
    name = _FIELD_NAMES.get(field, field)
    kind = error.get("type", "")
    ctx = error.get("ctx") or {}
    if kind == "value_error":
        if field == "email":
            return "邮箱格式不正确"
        return str(ctx.get("error", error["msg"]))
    if kind == "missing":
        return f"请填写{name}"
    if kind == "string_too_short":
        return (
            f"{name}不能为空"
            if ctx.get("min_length") == 1
            else f"{name}至少 {ctx.get('min_length')} 个字符"
        )
    if kind == "string_too_long":
        return f"{name}不能超过 {ctx.get('max_length')} 个字符"
    if kind == "string_pattern_mismatch" and field == "code":
        return "验证码为 6 位数字"
    if kind in ("literal_error", "enum"):
        return f"{name}不正确"
    return f"{name}格式不正确" if name else "请求参数不正确"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _response(exc.status, exc.code, exc.message, exc.detail, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": _friendly(e)}
            for e in exc.errors()
        ]
        # message 直接展示给用户：取第一个错误
        message = errors[0]["message"] if errors else "请求参数不正确"
        return _response(422, "validation_error", message, errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        messages = {404: "接口不存在", 405: "请求方法不正确"}
        message = messages.get(exc.status_code, str(exc.detail))
        return _response(exc.status_code, f"http_{exc.status_code}", message)
