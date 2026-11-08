import secrets
import string

from sqlalchemy import BigInteger, Boolean, Computed, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TABLE_ARGS, Base, IdMixin, TimestampMixin

_PUBLIC_ID_ALPHABET = string.ascii_letters + string.digits
PUBLIC_ID_LENGTH = 12


def generate_public_id() -> str:
    """分享链接中的随机 id（62^12 种组合，无法遍历），与自增 id、标题、路径都无关。"""
    return "".join(secrets.choice(_PUBLIC_ID_ALPHABET) for _ in range(PUBLIC_ID_LENGTH))


class Note(IdMixin, TimestampMixin, Base):
    __tablename__ = "note"

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    # NULL 表示在根目录；删除文件夹时其中的笔记由数据库级联删除
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("folder.id", ondelete="CASCADE"))
    # 生成列，作用同 Folder.parent_key
    folder_key: Mapped[int] = mapped_column(
        BigInteger, Computed("IFNULL(`folder_id`, 0)", persisted=False)
    )
    # UTF-8 不超过 240 字节，由业务层校验
    title: Mapped[str] = mapped_column(String(255))
    # MEDIUMTEXT 上限 16MB；MySQL 不支持给 TEXT 类字段设普通默认值，由 ORM 填充空字符串
    content: Mapped[str] = mapped_column(MEDIUMTEXT, default="")
    # 乐观锁：保存时 WHERE version = ?，影响行数为 0 即冲突
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    is_public: Mapped[bool] = mapped_column(Boolean, server_default="0")
    public_id: Mapped[str] = mapped_column(
        String(PUBLIC_ID_LENGTH), unique=True, default=generate_public_id
    )

    __table_args__ = (UniqueConstraint("user_id", "folder_key", "title"), TABLE_ARGS)
