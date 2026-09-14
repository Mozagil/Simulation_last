"""0.5.4 DOE: LHS tohum, bölge bağlama, hata tüm işi durdurmaz."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.doe.regions import DoeBindError, bind_scenario_bcs
from app.doe.runner import persist_study, run_study
from app.doe.sampling import BcScenario, DoeSpec, sample_spec
from app.models.base import Base
from app.models.doe import DoeCase, DoeStudy
from app.models.geometry import PhysicalGroup


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'doe.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _spec(**kw):
    base = dict(
        template_id="cantilever_beam",
        seed=7,
        n_samples=4,
        geometry={"length": (400.0, 600.0), "thickness": (8.0, 12.0), "width": (40.0, 60.0)},
        element_size=(6.0, 10.0),
        material_ids=[1, 2],
        bc_scenarios=[
            BcScenario(
                name="tip_-y",
                bcs=[
                    {"type": "fixed", "region": "ankastre_uc"},
                    {"type": "cload", "region": "yuk_yuzeyi", "fy": -500.0},
                ],
            ),
            BcScenario(
                name="tip_-z",
                bcs=[
                    {"type": "fixed", "region": "ankastre_uc"},
                    {"type": "cload", "region": "yuk_yuzeyi", "fz": -500.0},
                ],
            ),
        ],
        run_solver=False,
    )
    base.update(kw)
    return DoeSpec.model_validate(base)


def test_lhs_is_reproducible_with_seed():
    a = sample_spec(_spec(seed=42))
    b = sample_spec(_spec(seed=42))
    c = sample_spec(_spec(seed=43))
    assert [s.geometry_params for s in a] == [s.geometry_params for s in b]
    assert [s.element_size for s in a] == [s.element_size for s in b]
    assert [s.geometry_params for s in a] != [s.geometry_params for s in c]


def test_lhs_covers_geometry_bounds():
    samples = sample_spec(_spec(n_samples=12, seed=1))
    lengths = [s.geometry_params["length"] for s in samples]
    assert min(lengths) >= 400.0
    assert max(lengths) <= 600.0
    assert max(lengths) - min(lengths) > 50.0
    assert {s.scenario.name for s in samples} <= {"tip_-y", "tip_-z"}


def test_bind_region_uses_face_or_edge():
    groups = {
        "ankastre_uc": PhysicalGroup(
            geometry_id=1, name="ankastre_uc", dim=2, entity_tags=[4]
        ),
        "yuk_burulma": PhysicalGroup(
            geometry_id=1, name="yuk_burulma", dim=1, entity_tags=[9]
        ),
    }
    bound = bind_scenario_bcs(
        groups,
        [
            {"type": "fixed", "region": "ankastre_uc"},
            {"type": "cload", "region": "yuk_burulma", "fy": -10.0},
        ],
    )
    assert bound[0]["face_ids"] == [4]
    assert "region" not in bound[0]
    assert bound[1]["edge_ids"] == [9]


def test_bind_unknown_region_raises():
    with pytest.raises(DoeBindError, match="yok"):
        bind_scenario_bcs({}, [{"type": "fixed", "region": "ghost"}])


def test_persist_study_writes_seed_and_cases(db_session):
    spec = _spec(n_samples=3, seed=9)
    study = persist_study(db_session, spec)
    assert study.seed == 9
    assert study.template_id == "cantilever_beam"
    cases = db_session.query(DoeCase).filter(DoeCase.study_id == study.id).all()
    assert len(cases) == 3
    assert {c.index for c in cases} == {0, 1, 2}


def test_run_study_continues_after_one_failure(db_session, monkeypatch):
    spec = _spec(n_samples=3, seed=1)
    study = persist_study(db_session, spec)

    def fake_execute(db, spec, sample, case):
        if sample.index == 1:
            raise RuntimeError("örnek 1 patladı")
        case.status = "inp_only"
        case.message = "ok"

    monkeypatch.setattr("app.doe.runner._execute_sample", fake_execute)
    out = run_study(db_session, study.id)
    assert out.status == "completed_with_errors"
    by_i = {
        c.index: c.status
        for c in db_session.query(DoeCase).filter(DoeCase.study_id == study.id)
    }
    assert by_i[0] == "inp_only"
    assert by_i[1] == "failed"
    assert by_i[2] == "inp_only"
