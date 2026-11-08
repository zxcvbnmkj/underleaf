from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TABLE_ARGS, Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "user"
    __table_args__ = TABLE_ARGS

    # 邮箱和昵称都全局唯一，且不区分大小写（由排序规则保证）
    email: Mapped[str] = mapped_column(String(254), unique=True)
    # 2～20 个字符，不能包含 @（登录时靠 @ 区分邮箱和昵称），长度留有余量
    nickname: Mapped[str] = mapped_column(String(32), unique=True)
    # Argon2 哈希，注册时必填
    password_hash: Mapped[str] = mapped_column(String(255))
    # 写入 JWT，修改 / 重置密码时加 1，使其他设备上的登录态失效
    token_version: Mapped[int] = mapped_column(Integer, server_default="0")
    # 该用户的笔记或文件夹有任何变动就加 1，Git 同步据此判断是否需要生成快照
    content_rev: Mapped[int] = mapped_column(BigInteger, server_default="0")
