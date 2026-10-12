"""composite_materials tablosu + UD ply seed (Faz 3.1)

Revision ID: c4d5e6f7a8b9
Revises: a7b8c9d0e1f2
Create Date: 2026-10-12

Tipik/nominal el kitabı aralığı (Daniel/Ishai, Barbero mertebesi); mill
certificate değil. Araç bunları önermez — kütüphane kaydı olarak sunar.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Pa, kg/m³. UD enine izotropi: E3=E2, G13=G12, ν13=ν12.
_SEED = [
    {
        "name": "T300/epoxy",
        "ply_kind": "ud",
        "category": "cfrp",
        "standard": "typical handbook",
        "density": 1600.0,
        "e1": 135e9,
        "e2": 10e9,
        "e3": 10e9,
        "nu12": 0.30,
        "nu13": 0.30,
        "nu23": 0.45,
        "g12": 5.2e9,
        "g13": 5.2e9,
        "g23": 3.4e9,
        "xt": 1500e6,
        "xc": 1200e6,
        "yt": 50e6,
        "yc": 200e6,
        "s12": 70e6,
        "s13": 70e6,
        "s23": 40e6,
        "source": "library",
        "is_editable": False,
    },
    {
        "name": "E-glass/epoxy",
        "ply_kind": "ud",
        "category": "gfrp",
        "standard": "typical handbook",
        "density": 1900.0,
        "e1": 41e9,
        "e2": 10e9,
        "e3": 10e9,
        "nu12": 0.28,
        "nu13": 0.28,
        "nu23": 0.40,
        "g12": 4.3e9,
        "g13": 4.3e9,
        "g23": 3.6e9,
        "xt": 780e6,
        "xc": 480e6,
        "yt": 35e6,
        "yc": 120e6,
        "s12": 55e6,
        "s13": 55e6,
        "s23": 35e6,
        "source": "library",
        "is_editable": False,
    },
]


def upgrade() -> None:
    op.create_table(
        "composite_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ply_kind", sa.String(), nullable=False, server_default="ud"),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("standard", sa.String(), nullable=True),
        sa.Column("density", sa.Float(), nullable=False),
        sa.Column("e1", sa.Float(), nullable=False),
        sa.Column("e2", sa.Float(), nullable=False),
        sa.Column("e3", sa.Float(), nullable=False),
        sa.Column("nu12", sa.Float(), nullable=False),
        sa.Column("nu13", sa.Float(), nullable=False),
        sa.Column("nu23", sa.Float(), nullable=False),
        sa.Column("g12", sa.Float(), nullable=False),
        sa.Column("g13", sa.Float(), nullable=False),
        sa.Column("g23", sa.Float(), nullable=False),
        sa.Column("xt", sa.Float(), nullable=False),
        sa.Column("xc", sa.Float(), nullable=False),
        sa.Column("yt", sa.Float(), nullable=False),
        sa.Column("yc", sa.Float(), nullable=False),
        sa.Column("s12", sa.Float(), nullable=False),
        sa.Column("s13", sa.Float(), nullable=True),
        sa.Column("s23", sa.Float(), nullable=True),
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
    tbl = sa.table(
        "composite_materials",
        sa.column("name", sa.String),
        sa.column("ply_kind", sa.String),
        sa.column("category", sa.String),
        sa.column("standard", sa.String),
        sa.column("density", sa.Float),
        sa.column("e1", sa.Float),
        sa.column("e2", sa.Float),
        sa.column("e3", sa.Float),
        sa.column("nu12", sa.Float),
        sa.column("nu13", sa.Float),
        sa.column("nu23", sa.Float),
        sa.column("g12", sa.Float),
        sa.column("g13", sa.Float),
        sa.column("g23", sa.Float),
        sa.column("xt", sa.Float),
        sa.column("xc", sa.Float),
        sa.column("yt", sa.Float),
        sa.column("yc", sa.Float),
        sa.column("s12", sa.Float),
        sa.column("s13", sa.Float),
        sa.column("s23", sa.Float),
        sa.column("source", sa.String),
        sa.column("is_editable", sa.Boolean),
    )
    op.bulk_insert(tbl, _SEED)


def downgrade() -> None:
    op.drop_table("composite_materials")
