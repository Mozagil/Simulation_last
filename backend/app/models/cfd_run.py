"""CFD (OpenFOAM) koşu kaydı — Faz 2.4 (kullanıcı onayı 2026-10-08).

``crash_runs`` deseni: durability ``analysis_runs`` ve crash tablolarından ayrı.
Eğriler (residual, kuvvet katsayısı geçmişi) DB'de tutulmaz;
``uploads/cfd/<job_id>/job.json`` içinde kalır. Parametrik kanal gibi
geometrisiz mesh'ler olduğu için ``geometry_id`` boş olabilir.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CfdRun(Base):
    __tablename__ = "cfd_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    geometry_id: Mapped[int | None] = mapped_column(ForeignKey("geometries.id"), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    #: Çözücü (simpleFoam …), türbülans modeli, mesh türü (channel | block_mesh_dict …)
    application: Mapped[str | None] = mapped_column(String, nullable=True)
    turbulence: Mapped[str | None] = mapped_column(String, nullable=True)
    mesh_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    #: case_only | pending | solved | failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="case_only")
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    solver_ran: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())

    #: Girdinin tam anlık görüntüsü (case + mesh) — 2.9 vekil model girdisi buradan.
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    scalars: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    #: Analitik referans karşılaştırması (ör. Poiseuille) — veri.
    reference: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false(), index=True)
    exclude_reason: Mapped[str | None] = mapped_column(String, nullable=True)
