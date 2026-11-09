"""add access_token.token_encrypted

Revision ID: c4e8a1b3d527
Revises: b7d2f4a6c813
Create Date: 2026-11-09 03:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8a1b3d527"
down_revision: str | Sequence[str] | None = "b7d2f4a6c813"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 可空：旧令牌没有密文，只是不能在网页上查看，照常可用
    op.add_column(
        "access_token",
        sa.Column("token_encrypted", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("access_token", "token_encrypted")
