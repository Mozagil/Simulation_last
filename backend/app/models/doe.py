"""DOE çalışması ve örnek satırları (0.5.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DoeStudy(Base):
    __tablename__ = "doe_studies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    template_id: Mapped[str] = mapped_column(String(80), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spec: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    cases: Mapped[list["DoeCase"]] = relationship(
        back_populates="study", cascade="all, delete-orphan"
    )


class DoeCase(Base):
    __tablename__ = "doe_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("doe_studies.id", ondelete="CASCADE"), nullable=False
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    element_size: Mapped[float] = mapped_column(Float, nullable=False)
    material_id: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario_name: Mapped[str] = mapped_column(String, nullable=False)
    bound_bcs: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    geometry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    message: Mapped[str | None] = mapped_column(String, nullable=True)

    study: Mapped[DoeStudy] = relationship(back_populates="cases")
