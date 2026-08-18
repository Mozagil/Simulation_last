"""Kalıcı geometri kaydı ve Physical Group modelleri.

`Geometry`, yüklenen her STEP/IGES dosyası için kalıcı bir kayıttır — artık
geçici bir `stored_filename` değil, veritabanında yaşayan bir `id` (geometry_id)
kanonik kimlik olarak kullanılıyor. `current_filename`, o an geometrinin en
güncel halini (kopyalama gibi mutasyonlardan sonra güncellenmiş) gösteren
dosya adıdır — mutasyon işlemleri bu dosyayı yerinde günceller (overwrite).

`PhysicalGroup`, bir geometriye atanmış isimli yüzey grubunu (örn. "inlet")
tutar. STEP dosyaları Gmsh'in Physical Group kavramını saklamadığı için (bu
saf bir mesh/modelleme kavramı, CAD dosyasının bir parçası değil), bu bilgi
veritabanında saklanır — her istek gerektiğinde Gmsh oturumuna yeniden
uygulanabilir (replay).
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Geometry(Base):
    __tablename__ = "geometries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    current_filename: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    physical_groups: Mapped[list["PhysicalGroup"]] = relationship(
        back_populates="geometry", cascade="all, delete-orphan"
    )


class PhysicalGroup(Base):
    __tablename__ = "physical_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geometry_id: Mapped[int] = mapped_column(ForeignKey("geometries.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    entity_tags: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    geometry: Mapped["Geometry"] = relationship(back_populates="physical_groups")
