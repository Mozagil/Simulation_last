"""Malzeme kütüphanesi modeli (Faz 0 — 2b).

Değerler tipik/nominal mühendislik el kitabı aralıklarıdır (mill test report değil).
`source="library"` kütüphane kaydı; `user_defined` sonraki adımda.

`MaterialAssignment`: geometri + parça (volume/part_id) ↔ malzeme eşlemesi.
Run/solver bağlanınca `run_id` eklenebilir; şimdilik geometry bazlı.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    standard: Mapped[str | None] = mapped_column(String, nullable=True)
    density: Mapped[float] = mapped_column(Float, nullable=False)  # kg/m³
    youngs_modulus: Mapped[float] = mapped_column(Float, nullable=False)  # Pa
    poisson_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    yield_strength: Mapped[float] = mapped_column(Float, nullable=False)  # Pa
    ultimate_strength: Mapped[float] = mapped_column(Float, nullable=False)  # Pa
    elongation: Mapped[float | None] = mapped_column(Float, nullable=True)  # %
    sn_curve: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="library")
    is_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    assignments: Mapped[list["MaterialAssignment"]] = relationship(
        back_populates="material"
    )


class MaterialAssignment(Base):
    """Bir geometrideki parçaya (part_id) malzeme ataması."""

    __tablename__ = "material_assignments"
    __table_args__ = (
        UniqueConstraint(
            "geometry_id", "part_id", name="uq_material_assignment_geometry_part"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geometry_id: Mapped[int] = mapped_column(
        ForeignKey("geometries.id", ondelete="CASCADE"), nullable=False
    )
    part_id: Mapped[int] = mapped_column(Integer, nullable=False)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    material: Mapped["Material"] = relationship(back_populates="assignments")
