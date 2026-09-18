"""Run kürasyonu: elle dışlama + DOE seti bağı."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.run import AnalysisRun


@pytest.fixture()
def db_session(tmp_path):
    """Test başına izole SQLite. Repoda paylaşılan conftest yok; diğer
    test dosyaları da fixture'ı kendi içinde tanımlıyor."""
    # check_same_thread=False: TestClient isteği ayrı bir iş parçacığında
    # çalıştırır, SQLite varsayılan olarak buna izin vermez.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'curation.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _run(db, *, template_id="cantilever_beam", study_id=None, excluded=False):
    geo = Geometry(
        original_filename="t.step",
        current_filename="t.step",
        template_id=template_id,
        template_params={"length": 500, "thickness": 10, "width": 50},
    )
    db.add(geo)
    db.flush()
    run = AnalysisRun(
        geometry_id=geo.id,
        dimension=3,
        status="solved",
        bcs=[],
        materials_snapshot=[],
        scalars={
            "max_displacement": 20.0,
            "max_von_mises": 200.0,
            "node_count": 5000.0,
        },
        doe_study_id=study_id,
        excluded=excluded,
    )
    db.add(run)
    db.commit()
    return run


@pytest.fixture()
def client(db_session):
    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


class TestDislama:
    def test_isaretleme_silmez(self, client, db_session):
        run = _run(db_session)
        res = client.patch(
            f"/geometry/runs/{run.id}/exclude",
            json={"excluded": True, "reason": "deneme"},
        )
        assert res.status_code == 200
        assert res.json()["excluded"] is True
        assert res.json()["exclude_reason"] == "deneme"
        # Run hâlâ DB'de
        db_session.expire_all()
        assert db_session.get(AnalysisRun, run.id) is not None

    def test_geri_alinca_sebep_temizlenir(self, client, db_session):
        run = _run(db_session, excluded=True)
        res = client.patch(
            f"/geometry/runs/{run.id}/exclude", json={"excluded": False}
        )
        assert res.json()["excluded"] is False
        assert res.json()["exclude_reason"] is None

    def test_toplu_isaretleme(self, client, db_session):
        ids = [_run(db_session).id for _ in range(3)]
        res = client.patch(
            "/geometry/runs/exclude-bulk",
            json={"run_ids": ids, "excluded": True, "reason": "mükerrer"},
        )
        assert res.status_code == 200
        assert res.json()["updated"] == 3

    def test_bos_liste_reddedilir(self, client):
        res = client.patch(
            "/geometry/runs/exclude-bulk", json={"run_ids": [], "excluded": True}
        )
        assert res.status_code == 400


class TestSuzme:
    def test_sablona_gore_ayrilir(self, client, db_session):
        _run(db_session, template_id="cantilever_beam")
        _run(db_session, template_id="plate_with_hole")
        kiris = client.get("/geometry/runs?template_id=cantilever_beam").json()
        plaka = client.get("/geometry/runs?template_id=plate_with_hole").json()
        assert kiris["count"] == 1
        assert plaka["count"] == 1
        assert kiris["runs"][0]["template_id"] == "cantilever_beam"

    def test_doe_setine_gore_ayrilir(self, client, db_session):
        _run(db_session, study_id=7)
        _run(db_session, study_id=9)
        _run(db_session, study_id=None)
        res = client.get("/geometry/runs?doe_study_id=9").json()
        assert res["count"] == 1
        assert res["runs"][0]["doe_study_id"] == 9

    def test_dislananlar_gizlenebilir(self, client, db_session):
        _run(db_session)
        _run(db_session, excluded=True)
        hepsi = client.get("/geometry/runs").json()
        temiz = client.get("/geometry/runs?include_excluded=false").json()
        assert hepsi["count"] == 2
        assert temiz["count"] == 1

    def test_yalniz_dislananlar(self, client, db_session):
        _run(db_session)
        _run(db_session, excluded=True)
        res = client.get("/geometry/runs?only_excluded=true").json()
        assert res["count"] == 1
        assert res["runs"][0]["excluded"] is True

    def test_varsayilan_davranis_degismedi(self, client, db_session):
        """Parametresiz çağrı eskisi gibi HER ŞEYİ döndürmeli."""
        _run(db_session)
        _run(db_session, excluded=True)
        _run(db_session, template_id="plate_with_hole")
        assert client.get("/geometry/runs").json()["count"] == 3


class TestKorpusDislama:
    def test_dislanan_run_egitime_girmez(self, db_session):
        from app.ml.corpus import CorpusSpec, select_training_runs

        _run(db_session)
        _run(db_session, excluded=True)
        corpus = select_training_runs(
            db_session, CorpusSpec(template_id="cantilever_beam")
        )
        assert corpus.dropped.get("manually_excluded") == 1
