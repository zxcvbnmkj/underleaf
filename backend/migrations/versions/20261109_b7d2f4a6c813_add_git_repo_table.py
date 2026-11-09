"""add git_repo table

Revision ID: b7d2f4a6c813
Revises: a3c1e5f7b902
Create Date: 2026-11-09 02:00:01.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "b7d2f4a6c813"
down_revision: str | Sequence[str] | None = "a3c1e5f7b902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "git_repo",
        sa.Column("user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("head_commit", sa.String(length=40), nullable=True),
        sa.Column("synced_rev", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_git_repo_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_git_repo")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_520_ci",
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("git_repo")
