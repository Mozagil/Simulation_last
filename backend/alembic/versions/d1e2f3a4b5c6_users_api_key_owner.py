"""users tablosu (API anahtarı) + geometries.owner_id

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-09-26

WeWeb bağlantısı: Bearer API anahtarı, kullanıcı başına veri. Eski
geometriler owner_id NULL kalır (herkese açık) — veri silinmez, taşınmaz.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_api_key_hash", "users", ["api_key_hash"])
    op.add_column("geometries", sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.create_index("ix_geometries_owner_id", "geometries", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_geometries_owner_id", table_name="geometries")
    op.drop_column("geometries", "owner_id")
    op.drop_index("ix_users_api_key_hash", table_name="users")
    op.drop_table("users")
