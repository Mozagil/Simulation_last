"""Bu tablo, Alembic migration pipeline'ının uçtan uca çalıştığını kanıtlamak için
eklenmiş boş bir tablodur (ROADMAP.md, Faz 0 / 0. Altyapı iskeleti).

Gerçek domain tabloları (material, analysis_run, result vb.) ilerideki adımlarda
ayrı migration'larla eklenecek — bu tablo onların yerini tutmuyor.
"""

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SystemCheck(Base):
    __tablename__ = "system_check"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
