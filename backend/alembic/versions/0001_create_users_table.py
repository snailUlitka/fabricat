"""Create users table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_create_users_table"
down_revision = None
branch_labels = None
depends_on = None

AVATAR_ICON = sa.Enum(
    "astronaut",
    "botanist",
    "captain",
    "diver",
    "engineer",
    "geologist",
    "hacker",
    "inventor",
    "pilot",
    "scientist",
    name="avatar_icon",
)


def upgrade() -> None:
    AVATAR_ICON.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("nickname", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "icon",
            AVATAR_ICON,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_users_nickname", "users", ["nickname"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_nickname", table_name="users")
    op.drop_table("users")
    AVATAR_ICON.drop(op.get_bind(), checkfirst=True)
