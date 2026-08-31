"""material_assignments tablosu

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-28 22:25:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "geometry_id",
            sa.Integer(),
            sa.ForeignKey("geometries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column(
            "material_id",
            sa.Integer(),
            sa.ForeignKey("materials.id"),
            nullable=False,
        ),
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
            name="uq_material_assignment_geometry_part",
        ),
    )


def downgrade() -> None:
    op.drop_table("material_assignments")
