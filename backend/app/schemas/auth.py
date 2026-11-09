import re
from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field

from app.schemas.base import Schema
from app.services.email_codes import Purpose

NICKNAME_RE = re.compile(r"^[A-Za-z0-9_\-㐀-䶿一-鿿]{2,20}$")


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _check_nickname(value: str) -> str:
    value = value.strip()
    if not NICKNAME_RE.match(value):
        raise ValueError("昵称为 2～20 个字符，只能包含中文、字母、数字、_ 和 -")
    return value


def _check_password(value: str) -> str:
    if not value.strip():
        raise ValueError("密码不能全是空格")
    return value


Email = Annotated[EmailStr, AfterValidator(_normalize_email)]
Nickname = Annotated[str, AfterValidator(_check_nickname)]
Password = Annotated[str, Field(min_length=8, max_length=128), AfterValidator(_check_password)]
Code = Annotated[str, Field(pattern=r"^\s*\d{6}\s*$")]


class UserOut(Schema):
    id: int
    email: str
    nickname: str


class SendCodeIn(Schema):
    email: Email
    purpose: Purpose


class RegisterIn(Schema):
    email: Email
    nickname: Nickname
    password: Password


class CodeLoginIn(Schema):
    email: Email
    code: Code


class PasswordLoginIn(Schema):
    # 邮箱或昵称：包含 @ 视为邮箱
    account: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ResetPasswordIn(Schema):
    email: Email
    code: Code
    new_password: Password


class ChangePasswordIn(Schema):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: Password


class UpdateMeIn(Schema):
    nickname: Nickname
