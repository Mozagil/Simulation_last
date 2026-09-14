"""0.5.3 veri seti API — özet endpoint'i."""

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def _db_available() -> bool:
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except OperationalError:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="PostgreSQL yok")


@requires_db
def test_dataset_summary_keys():
    response = client.get("/dataset/summary")
    assert response.status_code == 200
    body = response.json()
    for key in ("geometries", "materials", "analysis_runs", "solved_runs", "training_samples"):
        assert key in body
        assert isinstance(body[key], int)
