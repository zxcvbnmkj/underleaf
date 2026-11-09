"""add access_token table

Revision ID: a3c1e5f7b902
Revises: 6fe939b81c88
Create Date: 2026-11-09 02:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "a3c1e5f7b902"
down_revision: str | Sequence[str] | None = "6fe939b81c88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "access_token",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_chars", sa.String(length=8), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("last_used_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("revoked_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_access_token_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_access_token_token_hash")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_520_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(op.f("ix_access_token_user_id"), "access_token", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_access_token_user_id"), table_name="access_token")
    op.drop_table("access_token")
