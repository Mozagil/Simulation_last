"""0.5.5 kalite seti: 200 örnek kilitlenir, tarayıcı sınıflar; solver çalışmaz."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.doe.quality import classify_case, scan_study
from app.doe.quality_set import QUALITY_SET_N, QUALITY_SET_SEED, cantilever_quality_spec
from app.doe.runner import persist_study
from app.doe.sampling import sample_spec
from app.main import app
from app.models.base import Base
from app.models.doe import DoeCase, DoeStudy
from app.models.geometry import Geometry
from app.models.material import Material
from app.models.run import AnalysisRun


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'quality.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _fy(sample) -> float:
    for bc in sample.scenario.bcs:
        if str(bc.get("type") or "").lower() == "cload":
            return float(bc["fy"])
    raise AssertionError("CLOAD yok")


def test_quality_set_is_200_reproducible_and_slender():
    spec = cantilever_quality_spec([11])
    a = sample_spec(spec)
    b = sample_spec(spec)
    assert spec.n_samples == QUALITY_SET_N == 200
    assert spec.seed == QUALITY_SET_SEED == 2026
    assert spec.template_id == "cantilever_beam"
    assert len(a) == 200
    assert [s.geometry_params for s in a] == [s.geometry_params for s in b]
    assert [_fy(s) for s in a] == [_fy(s) for s in b]
    for s in a:
        g = s.geometry_params
        assert 450.0 <= g["length"] <= 700.0
        assert 8.0 <= g["thickness"] <= 12.0
        assert 35.0 <= g["width"] <= 70.0
        assert g["length"] / g["thickness"] >= 5.0
        assert 6.0 <= s.element_size <= 14.0
        assert -800.0 <= _fy(s) <= -200.0
        assert s.scenario.name == "tip_-y"
        assert {bc.get("region") for bc in s.scenario.bcs} == {"ankastre_uc", "yuk_yuzeyi"}


def test_quality_set_does_not_invoke_solver_on_persist(db_session, monkeypatch):
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("solver/mesh çalışmamalı")

    monkeypatch.setattr("app.doe.runner._execute_sample", boom)
    spec = cantilever_quality_spec([1], run_solver=True)
    study = persist_study(db_session, spec)
    n = db_session.query(DoeCase).filter(DoeCase.study_id == study.id).count()
    assert n == 200
    assert study.seed == 2026
    assert called["n"] == 0
    assert spec.run_solver is True  # kuyrukta açık; persist çözmez


def test_classify_flags_rigid_body_and_analytic_warn():
    failed = DoeCase(
        study_id=1,
        index=0,
        geometry_params={},
        element_size=8.0,
        material_id=1,
        scenario_name="tip_-y",
        status="failed",
    )
    assert classify_case(failed, None) == "failed"

    pending = DoeCase(
        study_id=1,
        index=1,
        geometry_params={},
        element_size=8.0,
        material_id=1,
        scenario_name="tip_-y",
        status="pending",
    )
    assert classify_case(pending, None) == "pending"

    missing = DoeCase(
        study_id=1,
        index=2,
        geometry_params={},
        element_size=8.0,
        material_id=1,
        scenario_name="tip_-y",
        status="solved",
    )
    assert classify_case(missing, None) == "missing_run"

    run = AnalysisRun(
        geometry_id=1,
        dimension=3,
        bcs=[],
        materials_snapshot=[],
        status="solved",
        scalars={"max_displacement": 2.0e6, "node_count": 4000},
    )
    solved = DoeCase(
        study_id=1,
        index=3,
        geometry_params={},
        element_size=8.0,
        material_id=1,
        scenario_name="tip_-y",
        status="solved",
    )
    assert classify_case(solved, run) == "rigid_body"

    run.scalars = {"max_displacement": 20.0, "node_count": 8}
    assert classify_case(solved, run) == "degenerate_mesh"

    run.scalars = {
        "max_displacement": 20.0,
        "node_count": 4000,
        "_analytic_comparison": {"skipped": True, "warned": False},
    }
    assert classify_case(solved, run) == "analytic_skipped"

    run.scalars = {
        "max_displacement": 20.0,
        "node_count": 4000,
        "_analytic_comparison": {"skipped": False, "warned": True},
    }
    assert classify_case(solved, run) == "analytic_warn"

    run.scalars = {
        "max_displacement": 20.0,
        "node_count": 4000,
        "_analytic_comparison": {"skipped": False, "warned": False},
    }
    assert classify_case(solved, run) == "ok"

    inp = DoeCase(
        study_id=1,
        index=4,
        geometry_params={},
        element_size=8.0,
        material_id=1,
        scenario_name="tip_-y",
        status="inp_only",
    )
    assert classify_case(inp, run) == "inp_only"


def test_scan_study_counts_dummy_flags(db_session):
    g = Geometry(original_filename="a.step", current_filename="a.step")
    db_session.add(g)
    db_session.flush()
    ok_run = AnalysisRun(
        geometry_id=g.id,
        dimension=3,
        bcs=[],
        materials_snapshot=[],
        status="solved",
        scalars={
            "max_displacement": 22.0,
            "node_count": 5000,
            "_analytic_comparison": {"warned": False, "skipped": False},
        },
    )
    warn_run = AnalysisRun(
        geometry_id=g.id,
        dimension=3,
        bcs=[],
        materials_snapshot=[],
        status="solved",
        scalars={
            "max_displacement": 40.0,
            "node_count": 5000,
            "_analytic_comparison": {"warned": True, "skipped": False},
        },
    )
    rigid_run = AnalysisRun(
        geometry_id=g.id,
        dimension=3,
        bcs=[],
        materials_snapshot=[],
        status="solved",
        scalars={"max_displacement": 1.5e6, "node_count": 5000},
    )
    db_session.add_all([ok_run, warn_run, rigid_run])
    db_session.flush()

    study = DoeStudy(
        name="dummy",
        template_id="cantilever_beam",
        seed=1,
        spec={"template_id": "cantilever_beam"},
        status="completed",
    )
    db_session.add(study)
    db_session.flush()
    rows = [
        DoeCase(
            study_id=study.id,
            index=0,
            geometry_params={},
            element_size=8.0,
            material_id=1,
            scenario_name="tip_-y",
            status="solved",
            run_id=ok_run.id,
        ),
        DoeCase(
            study_id=study.id,
            index=1,
            geometry_params={},
            element_size=8.0,
            material_id=1,
            scenario_name="tip_-y",
            status="solved",
            run_id=warn_run.id,
        ),
        DoeCase(
            study_id=study.id,
            index=2,
            geometry_params={},
            element_size=8.0,
            material_id=1,
            scenario_name="tip_-y",
            status="solved",
            run_id=rigid_run.id,
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()
    loaded = db_session.get(DoeStudy, study.id)
    assert loaded is not None
    report = scan_study(db_session, loaded)
    assert report["n_cases"] == 3
    assert report["n_ok"] == 1
    assert report["counts"]["ok"] == 1
    assert report["counts"]["analytic_warn"] == 1
    assert report["counts"]["rigid_body"] == 1
    assert report["flagged"]["analytic_warn"] == [1]
    assert report["flagged"]["rigid_body"] == [2]


def test_quality_set_endpoint_does_not_run_queue(db_session, monkeypatch):
    mat = Material(
        name="TEST-S235",
        category="steel",
        density=7850.0,
        youngs_modulus=210e9,
        poisson_ratio=0.3,
        yield_strength=235e6,
        ultimate_strength=360e6,
    )
    db_session.add(mat)
    db_session.commit()

    ran = {"n": 0}

    def no_queue(_sid: int) -> None:
        ran["n"] += 1

    monkeypatch.setattr("app.api.doe._run_in_background", no_queue)

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        res = client.post("/doe/quality-set", json={"wait": False, "run_solver": False})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["n_cases"] == 200
        assert body["template_id"] == "cantilever_beam"
        assert body["seed"] == 2026
        q = client.get(f"/doe/studies/{body['id']}/quality")
        assert q.status_code == 200
        report = q.json()
        assert report["n_cases"] == 200
        assert report["counts"].get("pending") == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
    # TestClient arka plan görevini çağırır; kuyruk no-op, mesh yok.
    assert ran["n"] == 1
