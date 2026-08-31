"""Mesh/CAD parçası için component + property kaydı.

HyperMesh tarzı ayrım:
- Component: ürün ağacındaki parça (ELSET / part_id)
- Material: kütüphane malzemesi (E, ν, ρ, …) — ayrı FK
- Property: kesit tanımı (shell kalınlık / solid) — component üzerinde

Solver henüz bu tabloyu okumaz; ürün ağacı ve atama içindir.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.material import Material


class Component(Base):
    __tablename__ = "components"
    __table_args__ = (
        UniqueConstraint(
            "geometry_id", "part_id", name="uq_component_geometry_part"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geometry_id: Mapped[int] = mapped_column(
        ForeignKey("geometries.id", ondelete="CASCADE"), nullable=False
    )
    part_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="mesh")
    material_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True
    )
    property_kind: Mapped[str] = mapped_column(String, nullable=False, default="shell")
    thickness: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    material: Mapped[Material | None] = relationship()
