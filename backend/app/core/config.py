from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从环境变量或 backend/.env 读取（字段名不区分大小写）。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "prod"] = "dev"

    # mysql+aiomysql://用户:密码@主机:3306/underleaf
    database_url: str
    # 打印 SQL，调试用
    database_echo: bool = False

    # redis://:密码@主机:6379/0
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
