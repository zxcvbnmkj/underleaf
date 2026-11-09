from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TABLE_ARGS, Base, IdMixin, TimestampMixin


class Image(IdMixin, TimestampMixin, Base):
    """上传的图片。文件存放在 UPLOAD_DIR/{path}，访问地址为 /uploads/{path}（站内相对路径）。"""

    __tablename__ = "image"
    __table_args__ = TABLE_ARGS

    # 上传者。删除用户时置空、保留图片记录，由清理脚本处理
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL")
    )
    # 相对于 UPLOAD_DIR 的路径，如 images/2026/11/3f2a….png
    path: Mapped[str] = mapped_column(String(255), unique=True)
    mime: Mapped[str] = mapped_column(String(32))
    size: Mapped[int] = mapped_column(Integer)
