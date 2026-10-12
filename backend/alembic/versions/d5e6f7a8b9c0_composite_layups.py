"""composite_layups tablosu (Faz 3.5)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-12

geometry + part_id başına bir dizilim. plies JSON: alt → üst
[{material_id, thickness_mm, angle_deg}, …].
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "composite_layups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "geometry_id",
            sa.Integer(),
            sa.ForeignKey("geometries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("plies", sa.JSON(), nullable=False),
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
            name="uq_composite_layup_geometry_part",
        ),
    )


def downgrade() -> None:
    op.drop_table("composite_layups")
