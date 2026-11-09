"""访问令牌的生成、加密与 HTTP Basic 解析（不需要数据库）。"""

import base64

import pytest

from app.core.config import get_settings
from app.services.access_tokens import (
    decrypt_token,
    encrypt_token,
    generate_token,
    hash_token,
    parse_basic_auth,
)


@pytest.fixture(autouse=True)
def clean_redis() -> None:
    """覆盖 conftest 中的同名夹具：这里的测试不用 Redis。"""


def test_encrypt_roundtrip():
    token = generate_token()
    encrypted = encrypt_token(token)
    assert token not in encrypted and token != hash_token(token)
    assert decrypt_token(encrypted) == token
    assert decrypt_token(None) is None


def test_decrypt_after_secret_change(monkeypatch: pytest.MonkeyPatch):
    encrypted = encrypt_token(generate_token())
    monkeypatch.setattr(get_settings(), "jwt_secret", "another-secret" * 4)
    assert decrypt_token(encrypted) is None


def test_parse_basic_auth():
    header = "Basic " + base64.b64encode(b"alice:ulp_x:y").decode()
    assert parse_basic_auth(header) == ("alice", "ulp_x:y")
    assert parse_basic_auth(None) is None
    assert parse_basic_auth("Bearer abc") is None
    assert parse_basic_auth("Basic !!!") is None
