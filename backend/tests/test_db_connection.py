"""DB session'ın kurulabildiğini ve system_check tablosuna yazılıp okunabildiğini
doğrulayan test. Bu test gerçek bir PostgreSQL bağlantısı ister (DATABASE_URL) ve
`alembic upgrade head` çalıştırılmış olmalı.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models.system_check import SystemCheck


def _db_available() -> bool:
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except OperationalError:
        return False


requires_db = pytest.mark.skipif(
    not _db_available(),
    reason="PostgreSQL bağlantısı yok (DATABASE_URL ayarlı değil ya da servis kapalı)",
)


@requires_db
def test_can_insert_and_read_system_check():
    db = SessionLocal()
    try:
        row = SystemCheck()
        db.add(row)
        db.commit()
        db.refresh(row)

        assert row.id is not None

        fetched = db.get(SystemCheck, row.id)
        assert fetched is not None

        db.delete(fetched)
        db.commit()
    finally:
        db.close()
