"""Analiz geçmişi, şablon parametrelerini taşımalı (DOE sonuçlarını okumak için).

DOE taramasında onlarca run aynı şablondan üretilir; "hangi parametre
kombinasyonu hangi sonucu verdi" sorusunun cevabı ancak run ile geometrinin
`template_params`'ı birlikte görülünce çıkar.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.main import app
from app.models.geometry import Geometry
from app.models.run import AnalysisRun

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
def test_run_list_and_detail_expose_template_params():
    db = SessionLocal()
    created: list[int] = []
    try:
        geo = Geometry(
            original_filename="cantilever_beam.step",
            current_filename="x.step",
            template_id="cantilever_beam",
            template_params={"length": 512.5, "thickness": 9.4, "width": 48.0},
        )
        db.add(geo)
        db.commit()
        run = AnalysisRun(geometry_id=geo.id, dimension=3, status="solved", scalars={})
        db.add(run)
        db.commit()
        created = [run.id, geo.id]

        row = next(r for r in client.get("/geometry/runs").json()["runs"] if r["id"] == run.id)
        assert row["template_id"] == "cantilever_beam"
        assert row["template_params"]["length"] == 512.5

        detail = client.get(f"/geometry/runs/{run.id}").json()
        assert detail["template_id"] == "cantilever_beam"
        assert detail["template_params"] == {"length": 512.5, "thickness": 9.4, "width": 48.0}
    finally:
        if created:
            db.query(AnalysisRun).filter(AnalysisRun.id == created[0]).delete()
            db.query(Geometry).filter(Geometry.id == created[1]).delete()
            db.commit()
        db.close()


@requires_db
def test_uploaded_geometry_run_has_null_template_fields():
    db = SessionLocal()
    ids: list[int] = []
    try:
        geo = Geometry(original_filename="user.step", current_filename="user.step")
        db.add(geo)
        db.commit()
        run = AnalysisRun(geometry_id=geo.id, dimension=3, status="solved", scalars={})
        db.add(run)
        db.commit()
        ids = [run.id, geo.id]

        detail = client.get(f"/geometry/runs/{run.id}").json()
        assert detail["template_id"] is None
        assert detail["template_params"] is None
    finally:
        if ids:
            db.query(AnalysisRun).filter(AnalysisRun.id == ids[0]).delete()
            db.query(Geometry).filter(Geometry.id == ids[1]).delete()
            db.commit()
        db.close()
