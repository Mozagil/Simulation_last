"""Eğitim korpusu süzgeci: karışık aile / malzeme / büyük u / mesh aykırı."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.ml.corpus import CorpusSpec, select_training_runs
from app.ml.scalar_features import collect_scalar_table
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.run import AnalysisRun


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'corpus.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _run(
    db,
    *,
    length=500.0,
    thickness=10.0,
    width=50.0,
    fy=-500.0,
    disp=20.0,
    vm=200.0,
    element_size=8.0,
    template_id="cantilever_beam",
    E=210e9,
    nu=0.3,
    status="solved",
    analysis_type="static",
    node_count=100,
    warned=False,
):
    g = Geometry(
        original_filename="b.step",
        current_filename="b.step",
        template_id=template_id,
        template_params={"length": length, "thickness": thickness, "width": width},
    )
    db.add(g)
    db.flush()
    scalars = {
        "max_displacement": disp,
        "max_von_mises": vm,
        "node_count": node_count,
        "_analysis_type": analysis_type,
    }
    if warned:
        scalars["_analytic_comparison"] = {"warned": True}
    r = AnalysisRun(
        geometry_id=g.id,
        dimension=3,
        element_size=element_size,
        element_scheme="tet",
        bcs=[{"type": "fixed", "face_ids": [1]}, {"type": "cload", "fy": fy}],
        materials_snapshot=[{"youngs_modulus": E, "poisson_ratio": nu, "density": 7850.0}],
        status=status,
        scalars=scalars,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_corpus_keeps_one_family_one_material_linear_mesh(db_session):
    clean = [
        _run(db_session, disp=18.0 + i, fy=-400.0 - 10 * i) for i in range(8)
    ]
    _run(db_session, template_id="plate_with_hole", disp=21.0)
    _run(db_session, template_id="plate_with_hole", disp=22.0)
    _run(db_session, E=69e9, disp=21.0)
    _run(db_session, E=69e9, disp=22.0)
    _run(db_session, warned=True, disp=19.0)
    _run(db_session, disp=90.0)  # u/L = 0.18
    _run(db_session, element_size=40.0, disp=19.0)
    _run(db_session, analysis_type="modal", disp=19.0)

    corpus = select_training_runs(db_session)
    assert corpus.n_kept == 8
    assert set(corpus.run_ids) == {r.id for r in clean}
    assert corpus.template_id == "cantilever_beam"
    assert corpus.youngs_modulus == pytest.approx(210e9)
    assert corpus.dropped["other_template"] == 2
    assert corpus.dropped["other_material"] == 2
    assert corpus.dropped["analytic_warn"] == 1
    assert corpus.dropped["large_displacement"] == 1
    assert corpus.dropped["mesh_outlier"] == 1
    assert corpus.dropped["wrong_analysis"] == 1

    X, y, ids = collect_scalar_table(db_session, run_ids=corpus.run_ids)
    assert ids == corpus.run_ids
    assert X.shape[0] == 8
    assert y.shape[0] == 8


def test_soft_gate_keeps_min_samples_when_all_over_linear(db_session):
    for i in range(10):
        _run(db_session, disp=80.0 + i)  # u/L ≈ 0.16–0.18
    corpus = select_training_runs(db_session)
    assert corpus.n_kept == 8
    assert corpus.dropped["large_displacement"] == 2
    assert corpus.flagged["large_displacement"] == 8

    X, y, ids = collect_scalar_table(db_session, run_ids=corpus.run_ids)
    assert ids == corpus.run_ids
    assert X.shape[0] == 8
    assert y.shape[0] == 8


def test_corpus_template_id_overrides_majority(db_session):
    for _ in range(5):
        _run(db_session, template_id="cantilever_beam", disp=20.0)
    hole = _run(db_session, template_id="plate_with_hole", disp=15.0, width=80.0)
    corpus = select_training_runs(
        db_session, CorpusSpec(template_id="plate_with_hole")
    )
    assert corpus.run_ids == [hole.id]
    assert corpus.dropped["other_template"] == 5


def test_collect_empty_run_ids(db_session):
    _run(db_session)
    X, y, ids = collect_scalar_table(db_session, run_ids=[])
    assert ids == []
    assert X.shape[0] == 0
    assert y.shape[0] == 0


def test_scalar_train_api_filters_noise(db_session, tmp_path, monkeypatch):
    for i in range(8):
        _run(db_session, disp=18.0 + i)
    _run(db_session, disp=120.0)
    monkeypatch.setattr("app.api.surrogate.DEFAULT_MODEL_PATH", tmp_path / "rf.joblib")

    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        res = client.post("/surrogate/scalar/train")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["n_samples"] == 8
        assert body["corpus"]["dropped"]["large_displacement"] == 1
        assert body["corpus"]["template_id"] == "cantilever_beam"
    finally:
        app.dependency_overrides.pop(get_db, None)
