"""Kullanıcı + API anahtarı (WeWeb bağlantısı).

Anahtar DB'de yalnız SHA-256 özetiyle durur; düz metin bir kez üretilir
(`scripts/create_api_key.py`) ve bir daha okunamaz. Kaybolursa yenisi
üretilir, eskisi geçersiz olur.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
