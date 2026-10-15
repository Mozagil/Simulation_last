"""Crash (OpenRadioss) koşu kaydı — 1.16a.

Durability `analysis_runs` tablosundan ayrı (Faz 1: `/solve` refaktör edilmez).
Eğriler DB'de tutulmaz; `uploads/crash/<job_id>/job.json` içinde kalır.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CrashRun(Base):
    __tablename__ = "crash_runs"
    __table_args__ = (
        CheckConstraint("geometry_id IS NOT NULL OR import_id IS NOT NULL", name="ck_crash_runs_geometry_or_import"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: İş klasörü `uploads/crash/<job_id>`; tekil, içe aktarma bununla tekrarsız.
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    #: 1.21e-2b — içe aktarılan (.k) koşuda geometri yok; kayıt ya geometriye ya içe aktarmaya bağlı.
    geometry_id: Mapped[int | None] = mapped_column(ForeignKey("geometries.id"), nullable=True, index=True)
    import_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    t_end_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: rad_only | pending | solved | failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="rad_only")
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    solver_ran: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())

    #: İsteğin tam girdi anlık görüntüsü (bariyer, model, parçalar, temas,
    #: engine, th, kesitler) — 1.17 vekil model girdisi buradan.
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    materials_snapshot: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    scalars: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    #: Elle dışlama (deneme, hatalı kurulum…); silinmez, korpus almaz.
    excluded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(), index=True
    )
    exclude_reason: Mapped[str | None] = mapped_column(String, nullable=True)
