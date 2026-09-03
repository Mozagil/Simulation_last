"""Kalıcı analiz geçmişi (AnalysisRun).

ROADMAP.md "7. Veritabanına kayıt + geçmiş" — her `/solve` çağrısı, başarılı
ya da başarısız, kalıcı bir `AnalysisRun` satırı olarak kaydedilir. Bu
kayıtlar ASLA silinmez (mevcut geometri mutasyon davranışının aksine) —
Faz 4'teki surrogate model için eğitim verisi kaynağı olacak, ve kullanıcının
farklı senaryoları (case) karşılaştırabilmesi için gerekli.

Dosya adlandırması: eskiden `geo{geometry_id}_d{dimension}` idi — aynı
geometride ikinci kez çözünce ESKİ .inp/.frd/sonuç dosyalarının üzerine
yazılıyordu (history'yi bozardı). Artık her run kendi `run_id`'siyle
adlandırılan, birbirinden bağımsız bir klasörde (`uploads/runs/{run_id}/`)
yaşıyor.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geometry_id: Mapped[int] = mapped_column(ForeignKey("geometries.id"), nullable=False)
    # Kullanıcının verdiği isteğe bağlı etiket (örn. "9kN - orijinal fillet").
    # Boşsa frontend geometri adı + tarihi gösterir.
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    element_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    element_scheme: Mapped[str | None] = mapped_column(String, nullable=True)
    shell_thickness: Mapped[float | None] = mapped_column(Float, nullable=True)

    # O anki BC listesi ve malzeme ataması — run'ın tam girdi anlık görüntüsü
    # (surrogate model eğitimi için feature olarak kullanılacak).
    bcs: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    materials_snapshot: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)

    # "pending" (henüz işleniyor) | "inp_only" (sadece .inp üretildi, ccx
    # çalışmadı) | "solved" (ccx başarıyla bitti) | "failed" (hata)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    message: Mapped[str | None] = mapped_column(String, nullable=True)

    # Sonuç skalerleri (max_von_mises, max_displacement, node_count, ...) —
    # surrogate model için hedef (target) değerler olarak kullanılacak.
    scalars: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Dosya yolları (RUNS_DIR köküne göre değil, tam yol) — hiçbiri silinmez.
    inp_path: Mapped[str | None] = mapped_column(String, nullable=True)
    frd_path: Mapped[str | None] = mapped_column(String, nullable=True)
    results_preview_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # Bu run'ın kendi mesh önizlemesinin ANLIK GÖRÜNTÜSÜ (aynı geometride
    # sonraki bir case'in mesh'i yeniden üretilse bile bu run etkilenmez).
    mesh_preview_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # Bu run'ın kendi CAD tessellation'ının (STL) ANLIK GÖRÜNTÜSÜ — geometri
    # bu run'dan SONRA mutasyona uğrarsa (heal/defeature/offset/midsurface)
    # canlı tessellation_url artık FARKLI bir geometri durumuna işaret eder.
    # Karşılaştırma/geçmiş görünümü bu yüzden HER ZAMAN bu anlık görüntüyü
    # kullanmalı, canlı geometrinin STL'ini değil — gerçek bir ekran
    # görüntüsünde ("sonuçlar geometriden kaymış görünüyor") kanıtlandı.
    tessellation_snapshot_path: Mapped[str | None] = mapped_column(String, nullable=True)

    geometry: Mapped["Geometry"] = relationship()  # noqa: F821
