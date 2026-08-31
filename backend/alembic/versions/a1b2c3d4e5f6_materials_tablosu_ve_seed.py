"""materials tablosu + kütüphane seed

Revision ID: a1b2c3d4e5f6
Revises: 55c068ebfb0f
Create Date: 2026-08-28 17:52:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "55c068ebfb0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tipik/nominal değerler (EN 10025 / ASM); mill certificate değil.
_SEED_MATERIALS = [
    {
        "name": "S235",
        "category": "steel",
        "standard": "EN 10025-2",
        "density": 7850.0,
        "youngs_modulus": 210e9,
        "poisson_ratio": 0.30,
        "yield_strength": 235e6,
        "ultimate_strength": 360e6,
        "elongation": 26.0,
        "source": "library",
        "is_editable": False,
    },
    {
        "name": "S275",
        "category": "steel",
        "standard": "EN 10025-2",
        "density": 7850.0,
        "youngs_modulus": 210e9,
        "poisson_ratio": 0.30,
        "yield_strength": 275e6,
        "ultimate_strength": 430e6,
        "elongation": 23.0,
        "source": "library",
        "is_editable": False,
    },
    {
        "name": "S355",
        "category": "steel",
        "standard": "EN 10025-2",
        "density": 7850.0,
        "youngs_modulus": 210e9,
        "poisson_ratio": 0.30,
        "yield_strength": 355e6,
        "ultimate_strength": 510e6,
        "elongation": 22.0,
        "source": "library",
        "is_editable": False,
    },
    {
        "name": "6061-T6",
        "category": "aluminum",
        "standard": "ASM",
        "density": 2700.0,
        "youngs_modulus": 68.9e9,
        "poisson_ratio": 0.33,
        "yield_strength": 276e6,
        "ultimate_strength": 310e6,
        "elongation": 12.0,
        "source": "library",
        "is_editable": False,
    },
    {
        "name": "7075-T6",
        "category": "aluminum",
        "standard": "ASM",
        "density": 2810.0,
        "youngs_modulus": 71.7e9,
        "poisson_ratio": 0.33,
        "yield_strength": 503e6,
        "ultimate_strength": 572e6,
        "elongation": 11.0,
        "source": "library",
        "is_editable": False,
    },
]


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("standard", sa.String(), nullable=True),
        sa.Column("density", sa.Float(), nullable=False),
        sa.Column("youngs_modulus", sa.Float(), nullable=False),
        sa.Column("poisson_ratio", sa.Float(), nullable=False),
        sa.Column("yield_strength", sa.Float(), nullable=False),
        sa.Column("ultimate_strength", sa.Float(), nullable=False),
        sa.Column("elongation", sa.Float(), nullable=True),
        sa.Column("sn_curve", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="library"),
        sa.Column("is_editable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name"),
    )

    materials = sa.table(
        "materials",
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("standard", sa.String),
        sa.column("density", sa.Float),
        sa.column("youngs_modulus", sa.Float),
        sa.column("poisson_ratio", sa.Float),
        sa.column("yield_strength", sa.Float),
        sa.column("ultimate_strength", sa.Float),
        sa.column("elongation", sa.Float),
        sa.column("source", sa.String),
        sa.column("is_editable", sa.Boolean),
    )
    op.bulk_insert(materials, _SEED_MATERIALS)


def downgrade() -> None:
    op.drop_table("materials")
