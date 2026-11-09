"""Git 同步：个人访问令牌、每个用户的仓库状态（见 readme「Git 同步」）。"""

from datetime import datetime

from sqlalchemy import BigInteger, FetchedValue, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TABLE_ARGS, Base, IdMixin, Timestamp, TimestampMixin


class AccessToken(IdMixin, TimestampMixin, Base):
    """个人访问令牌：`git clone` 时作为密码使用。

    校验用 SHA-256 哈希；另存一份加密后的令牌（密钥由 JWT_SECRET 派生），供用户在网页上随时查看。
    """

    __tablename__ = "access_token"
    __table_args__ = TABLE_ARGS

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    # 用户起的名字，如「家里的电脑」，便于区分和吊销
    name: Mapped[str] = mapped_column(String(64))
    # 令牌是 32 字节随机数，SHA-256 即可（不需要 Argon2 这类慢哈希）
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Fernet 加密的令牌，只用于网页上显示；更换 JWT_SECRET 后无法解密（令牌照常可用）
    token_encrypted: Mapped[str | None] = mapped_column(String(255))
    # 令牌末尾 4 个字符，列表中展示，帮助用户辨认
    last_chars: Mapped[str] = mapped_column(String(8))
    # NULL 表示永不过期
    expires_at: Mapped[datetime | None] = mapped_column(Timestamp)
    last_used_at: Mapped[datetime | None] = mapped_column(Timestamp)
    revoked_at: Mapped[datetime | None] = mapped_column(Timestamp)


class GitRepo(Base):
    """用户的 Git 仓库状态。仓库本身是磁盘上的裸仓库 GIT_REPO_DIR/{user_id}.git。

    以数据库为准，仓库只是镜像：synced_rev 等于 user.content_rev 时，
    head_commit 的内容与数据库一致。
    这一行同时作为该用户 Git 操作的锁（SELECT ... FOR UPDATE）。
    """

    __tablename__ = "git_repo"
    __table_args__ = TABLE_ARGS

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True, autoincrement=False
    )
    head_commit: Mapped[str | None] = mapped_column(String(40))
    # 生成 head_commit 时（或推送写回后）的 user.content_rev；NULL 表示还没有生成过快照
    synced_rev: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        server_onupdate=FetchedValue(),
    )
