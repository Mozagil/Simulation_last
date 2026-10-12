"""Kompozit ply kütüphanesi + dizilim (Faz 3.1 / 3.5).

Metal `materials` tablosuna karışmaz: ortotrop 9 sabit + mukavemet.
Değerler tipik/nominal el kitabı aralığıdır (mill test report değil).
`source="library"` seed; `user_defined` POST ile.

`CompositeLayup`: geometri + parça ↔ katman listesi (`plies[0]` alt).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CompositeMaterial(Base):
    """Tek bir UD (veya ileride dokuma) ply: ENGINEERING CONSTANTS + allowables."""

    __tablename__ = "composite_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    #: ud | woven — Dalga 1 yalnız ud seed'ler.
    ply_kind: Mapped[str] = mapped_column(String, nullable=False, default="ud")
    #: cfrp | gfrp | custom
    category: Mapped[str] = mapped_column(String, nullable=False)
    standard: Mapped[str | None] = mapped_column(String, nullable=True)
    density: Mapped[float] = mapped_column(Float, nullable=False)  # kg/m³
    e1: Mapped[float] = mapped_column(Float, nullable=False)  # Pa
    e2: Mapped[float] = mapped_column(Float, nullable=False)  # Pa
    e3: Mapped[float] = mapped_column(Float, nullable=False)  # Pa
    nu12: Mapped[float] = mapped_column(Float, nullable=False)
    nu13: Mapped[float] = mapped_column(Float, nullable=False)
    nu23: Mapped[float] = mapped_column(Float, nullable=False)
    g12: Mapped[float] = mapped_column(Float, nullable=False)  # Pa
    g13: Mapped[float] = mapped_column(Float, nullable=False)  # Pa
    g23: Mapped[float] = mapped_column(Float, nullable=False)  # Pa
    xt: Mapped[float] = mapped_column(Float, nullable=False)  # Pa, fiber çekme
    xc: Mapped[float] = mapped_column(Float, nullable=False)  # Pa, fiber basma
    yt: Mapped[float] = mapped_column(Float, nullable=False)  # Pa, enine çekme
    yc: Mapped[float] = mapped_column(Float, nullable=False)  # Pa, enine basma
    s12: Mapped[float] = mapped_column(Float, nullable=False)  # Pa, düzlem içi kayma
    s13: Mapped[float | None] = mapped_column(Float, nullable=True)
    s23: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="library")
    is_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CompositeLayup(Base):
    """Bir geometrideki parçaya (part_id) katman dizilimi. plies[0] = alt."""

    __tablename__ = "composite_layups"
    __table_args__ = (
        UniqueConstraint(
            "geometry_id", "part_id", name="uq_composite_layup_geometry_part"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geometry_id: Mapped[int] = mapped_column(
        ForeignKey("geometries.id", ondelete="CASCADE"), nullable=False
    )
    part_id: Mapped[int] = mapped_column(Integer, nullable=False)
    #: [{material_id, thickness_mm, angle_deg}, …] — sıra alt → üst.
    plies: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CompositeOrientation(Base):
    """Paralel rozet + OSS (Faz 3.7). kind yalnız parallel; 0° = dir0."""

    __tablename__ = "composite_orientations"
    __table_args__ = (
        UniqueConstraint(
            "geometry_id", "part_id", name="uq_composite_orientation_geometry_part"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geometry_id: Mapped[int] = mapped_column(
        ForeignKey("geometries.id", ondelete="CASCADE"), nullable=False
    )
    part_id: Mapped[int] = mapped_column(Integer, nullable=False)
    #: parallel
    kind: Mapped[str] = mapped_column(String, nullable=False, default="parallel")
    #: [dx, dy, dz] birim; varsayılan global X.
    dir0: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    #: [x, y, z] mm, CAD.
    origin: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    #: part | faces
    target: Mapped[str] = mapped_column(String, nullable=False, default="part")
    face_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CompositeRun(Base):
    """Kompozit koşu — analysis_runs / crash_runs'tan ayrı. `/solve` değişmez."""

    __tablename__ = "composite_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    geometry_id: Mapped[int] = mapped_column(
        ForeignKey("geometries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    dimension: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    #: pending | inp_only | solved | failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    solver_ran: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inp_path: Mapped[str | None] = mapped_column(String, nullable=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    layup_snapshot: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    orientation_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    bcs: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    scalars: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
