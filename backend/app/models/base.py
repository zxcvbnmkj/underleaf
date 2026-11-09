from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, FetchedValue, MetaData, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 约束统一命名，Alembic 迁移中才能稳定地按名字修改或删除
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

TABLE_ARGS: dict[str, Any] = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    # 不区分大小写：Note 与 note 视为重名，与 Windows / macOS 文件系统一致。
    # 服务器为 MySQL 5.7，没有 utf8mb4_0900_ai_ci；unicode_ci / general_ci 会把所有 emoji
    # 视为同一个字符（「笔记🍣」与「笔记🍺」重名），unicode_520_ci 能正确区分。MySQL 8 同样支持
    "mysql_collate": "utf8mb4_unicode_520_ci",
}

# 时间统一存 UTC（连接时已设置 time_zone = '+00:00'），精确到毫秒
Timestamp = DATETIME(fsp=3)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # MySQL 不支持 RETURNING，插入 / 更新后自动回读 updated_at 等由数据库生成的值
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 SQLAlchemy 约定写法


class IdMixin:
    # sort_order 让 id 排在表的第一列、时间字段排在最后
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, sort_order=-100
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        Timestamp, server_default=text("CURRENT_TIMESTAMP(3)"), sort_order=100
    )
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        # 由数据库在 UPDATE 时自动刷新，ORM 更新后会回读最新值
        server_onupdate=FetchedValue(),
        sort_order=100,
    )
