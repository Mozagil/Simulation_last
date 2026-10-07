"""Crash DOE çalışması ve örnek satırları — 1.19c-2.

Durability `doe_studies` / `doe_cases` deseni, ayrı tablolar (Faz 1: `/solve`
ve durability DOE'ye dokunulmaz). Her örnek doğrulanmış senaryo isteğini
kendi satırında taşır: devam ettirmede yeniden örnekleme yok. Koşu kaydı
`crash_runs`'ta; bağ `run_id`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CrashDoeStudy(Base):
    __tablename__ = "crash_doe_studies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    template_id: Mapped[str] = mapped_column(String(80), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: CrashDoeSpec (base + vary + n_samples + seed)
    spec: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    #: pending | running | completed | completed_with_errors
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cases: Mapped[list["CrashDoeCase"]] = relationship(
        back_populates="study", cascade="all, delete-orphan", order_by="CrashDoeCase.index"
    )


class CrashDoeCase(Base):
    __tablename__ = "crash_doe_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("crash_doe_studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Taranan değerler: noktalı yol → değer
    values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    #: Doğrulanmış CrashScenarioRequest gövdesi
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    geometry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("crash_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: pending | solved | rad_only | failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    message: Mapped[str | None] = mapped_column(String, nullable=True)

    study: Mapped[CrashDoeStudy] = relationship(back_populates="cases")
