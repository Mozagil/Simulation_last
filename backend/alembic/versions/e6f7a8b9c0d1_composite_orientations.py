"""composite_orientations — paralel rozet + OSS (Faz 3.7)

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "composite_orientations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "geometry_id",
            sa.Integer(),
            sa.ForeignKey("geometries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, server_default="parallel"),
        sa.Column("dir0", sa.JSON(), nullable=False),
        sa.Column("origin", sa.JSON(), nullable=False),
        sa.Column("target", sa.String(), nullable=False, server_default="part"),
        sa.Column("face_ids", sa.JSON(), nullable=False),
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
            name="uq_composite_orientation_geometry_part",
        ),
    )


def downgrade() -> None:
    op.drop_table("composite_orientations")
