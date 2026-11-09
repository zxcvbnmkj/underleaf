from pydantic import Field

from app.schemas.base import Schema
from app.schemas.common import UtcDatetime


class TokenCreate(Schema):
    name: str = Field(min_length=1, max_length=64)
    # 有效期（天）；null 表示永不过期
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class TokenOut(Schema):
    id: int
    name: str
    # 令牌末尾几个字符，帮助辨认
    last_chars: str
    expires_at: UtcDatetime | None
    last_used_at: UtcDatetime | None
    created_at: UtcDatetime


class TokenCreated(TokenOut):
    # 明文令牌，只在创建时返回这一次
    token: str


class GitInfoOut(Schema):
    # git clone 地址的路径部分（如 /api/v1/git/3/notes.git），前端拼上当前网站的地址
    clone_path: str
    # 推送时的提交作者等不需要；用户名可以随便填，这里给出建议值
    username: str
