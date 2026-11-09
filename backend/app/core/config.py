from functools import lru_cache
from pathlib import Path
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

    # ---------- 登录 ----------
    # JWT 签名密钥，至少 32 个随机字符：python -c "import secrets; print(secrets.token_urlsafe(48))"
    # 修改后所有用户需要重新登录
    jwt_secret: str
    # 登录有效期（天）
    session_days: int = 30
    session_cookie: str = "underleaf_session"
    # 只在 HTTPS 下发送 Cookie；网站启用 HTTPS 后改为 true
    cookie_secure: bool = False

    # ---------- 邮件（发送验证码） ----------
    # 未配置 SMTP_HOST 时：开发环境把验证码打印到日志，正式环境拒绝发送
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    # 发件人，如 Underleaf <noreply@example.com>；为空时使用 smtp_username
    smtp_from: str = ""
    # 465 端口为 SSL 直连；587 端口为 STARTTLS，此时设为 false
    smtp_ssl: bool = True

    # ---------- PDF 导出 ----------
    # 无头 Chromium 访问前端渲染页的地址：本地开发为 Vite，服务器上为本机 Nginx
    export_render_url: str = "http://localhost:5173"
    # 为空时使用 Playwright 自带的 Chromium（需执行 playwright install chromium）；
    # 本地开发可以填 chrome，直接使用已安装的 Google Chrome，省去下载
    export_browser_channel: str | None = None
    # 同时进行的导出任务数，超出的排队（服务器内存小，不宜过多）
    export_concurrency: int = 2
    # 单次导出超时（秒），包含排队时间
    export_timeout_seconds: float = 30
    # 正文大小上限（字节）
    export_max_content_bytes: int = 5 * 1024 * 1024
    # 导出 Word 时下载正文中的外部图片：单张大小上限、单次最多张数、单张超时（秒）
    export_image_max_bytes: int = 10 * 1024 * 1024
    export_image_max_count: int = 50
    export_image_timeout_seconds: float = 10

    # ---------- 笔记 ----------
    # 正文大小上限（字节）；MEDIUMTEXT 上限 16MB，这里留有余量
    note_max_bytes: int = 5 * 1024 * 1024

    # ---------- 图片上传 ----------
    # 上传文件的存放目录；服务器上放在跨版本共享的目录中（见 docs/images.md）
    upload_dir: Path = Path(__file__).resolve().parents[3] / "uploads"
    # 单张图片大小上限（字节）
    upload_max_bytes: int = 10 * 1024 * 1024

    # ---------- Git 同步 ----------
    # 每个用户一个裸仓库 {GIT_REPO_DIR}/{user_id}.git；
    # 服务器上放在跨版本共享的目录（见 docs/pipeline.md）。
    # 仓库只是数据库的镜像，丢失后会在下次 clone / pull 时重新生成（本地需要重新 clone）
    git_repo_dir: Path = Path(__file__).resolve().parents[3] / "git-repos"
    # 单次 push 请求体上限（字节）；Nginx 的 client_max_body_size 要大于它
    git_max_push_bytes: int = 50 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
