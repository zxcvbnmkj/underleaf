from sqlalchemy import BigInteger, Computed, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TABLE_ARGS, Base, IdMixin, TimestampMixin


class Folder(IdMixin, TimestampMixin, Base):
    __tablename__ = "folder"

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    # NULL 表示在根目录；删除文件夹时子文件夹由数据库级联删除
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("folder.id", ondelete="CASCADE"))
    # 生成列：根目录记为 0，用于唯一索引（MySQL 中 NULL 与 NULL 不相等，直接用 parent_id
    # 建唯一索引时根目录下的同名限制会失效）。
    # 必须是 VIRTUAL：MySQL 不允许 STORED 生成列的基础列带 ON DELETE CASCADE 外键
    parent_key: Mapped[int] = mapped_column(
        BigInteger, Computed("IFNULL(`parent_id`, 0)", persisted=False)
    )
    # UTF-8 不超过 240 字节，由业务层校验
    name: Mapped[str] = mapped_column(String(255))

    __table_args__ = (UniqueConstraint("user_id", "parent_key", "name"), TABLE_ARGS)
