"""components tablosu (ürün ağacı)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-31 10:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "geometry_id",
            sa.Integer(),
            sa.ForeignKey("geometries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="mesh"),
        sa.Column(
            "material_id",
            sa.Integer(),
            sa.ForeignKey("materials.id"),
            nullable=True,
        ),
        sa.Column(
            "property_kind", sa.String(), nullable=False, server_default="shell"
        ),
        sa.Column("thickness", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "geometry_id",
            "part_id",
            name="uq_component_geometry_part",
        ),
    )


def downgrade() -> None:
    op.drop_table("components")
