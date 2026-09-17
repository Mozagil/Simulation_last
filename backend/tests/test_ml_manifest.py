"""Donmuş eğitim seti + manuel run onayı (corpus manifest).

Neden: `select_training_runs` her çağrıda canlı veritabanına bakar, yeni bir
run çözülünce set değişir ve iki eğitimin R²'si kıyaslanamaz hale gelir.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app
from app.ml.corpus import evaluate_run, select_training_runs
from app.ml.manifest import (
    ManifestError,
    add_runs,
    list_manifests,
    load_manifest,
    manifest_path,
    reference_from_manifest,
    save_manifest,
    spec_from_manifest,
)
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.run import AnalysisRun


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'manifest.db'}")
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
    disp=20.0,
    vm=200.0,
    element_size=8.0,
    template_id="cantilever_beam",
    E=210e9,
    status="solved",
):
    g = Geometry(
        original_filename="b.step",
        current_filename="b.step",
        template_id=template_id,
        template_params={"length": length, "thickness": thickness, "width": width},
    )
    db.add(g)
    db.flush()
    r = AnalysisRun(
        geometry_id=g.id,
        dimension=3,
        element_size=element_size,
        element_scheme="tet",
        bcs=[{"type": "fixed", "face_ids": [1]}, {"type": "cload", "fy": -500.0}],
        materials_snapshot=[{"youngs_modulus": E, "poisson_ratio": 0.3, "density": 7850.0}],
        status=status,
        scalars={
            "max_displacement": disp,
            "max_von_mises": vm,
            "node_count": 100,
            "_analysis_type": "static",
        },
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_freeze_then_new_runs_do_not_change_set(db_session, tmp_path):
    base = [_run(db_session, disp=18.0 + i) for i in range(8)]
    corpus = select_training_runs(db_session)
    payload = save_manifest("kiris", corpus, root=tmp_path)
    assert payload["run_ids"] == [r.id for r in base]
    assert payload["template_id"] == "cantilever_beam"
    assert payload["mesh_ratio_median"] == pytest.approx(0.8)

    _run(db_session, disp=19.0)
    assert select_training_runs(db_session).n_kept == 9
    assert load_manifest("kiris", root=tmp_path)["run_ids"] == [r.id for r in base]

    names = [m["name"] for m in list_manifests(root=tmp_path)]
    assert names == ["kiris"]


def test_manual_run_needs_explicit_add_and_override(db_session, tmp_path):
    for i in range(8):
        _run(db_session, disp=18.0 + i)
    corpus = select_training_runs(db_session)
    save_manifest("kiris", corpus, root=tmp_path)
    data = load_manifest("kiris", root=tmp_path)
    spec = spec_from_manifest(data)
    ref = reference_from_manifest(data)

    good = _run(db_session, disp=21.0)
    noisy = _run(db_session, disp=300.0)  # u/L = 0.6
    other = _run(db_session, template_id="plate_with_hole", disp=20.0)
    coarse = _run(db_session, element_size=40.0, disp=20.0)

    v_good = evaluate_run(db_session, good.id, spec, reference=ref)
    v_noisy = evaluate_run(db_session, noisy.id, spec, reference=ref)
    v_other = evaluate_run(db_session, other.id, spec, reference=ref)
    v_coarse = evaluate_run(db_session, coarse.id, spec, reference=ref)
    assert v_good.ok and v_good.reason is None
    assert v_noisy.reason == "large_displacement"
    assert v_noisy.u_over_L == pytest.approx(0.6)
    assert v_other.reason == "other_template"
    assert v_coarse.reason == "mesh_outlier"
    assert v_coarse.mesh_deviation == pytest.approx(4.0)

    # Süzgeci geçmeyenler override olmadan girmez.
    res = add_runs(
        "kiris", [v_good, v_noisy, v_other, v_coarse], override=False, root=tmp_path
    )
    assert res["added"] == [good.id]
    assert {r["run_id"] for r in res["rejected"]} == {noisy.id, other.id, coarse.id}
    assert res["manifest"]["manual_notes"][str(good.id)]["gate"] == "pass"

    # Aynı run ikinci kez eklenmez.
    again = add_runs("kiris", [v_good], root=tmp_path)
    assert again["added"] == []
    assert again["already_present"] == [good.id]

    # Bilinçli override gerekçesiyle kaydedilir.
    forced = add_runs("kiris", [v_noisy], override=True, root=tmp_path)
    assert forced["added"] == [noisy.id]
    note = forced["manifest"]["manual_notes"][str(noisy.id)]
    assert note["gate"] == "override"
    assert note["reason"] == "large_displacement"


def test_manifest_name_is_validated(tmp_path):
    with pytest.raises(ManifestError):
        manifest_path("../escape", root=tmp_path)
    with pytest.raises(ManifestError):
        load_manifest("yok", root=tmp_path)


def test_train_api_uses_frozen_manifest(db_session, tmp_path, monkeypatch):
    for i in range(8):
        _run(db_session, disp=18.0 + i)
    monkeypatch.setattr("app.api.surrogate.DEFAULT_MODEL_PATH", tmp_path / "rf.joblib")
    monkeypatch.setattr("app.ml.manifest.MANIFEST_DIR", tmp_path)

    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        frozen = client.post("/surrogate/corpus/freeze", params={"name": "kiris"})
        assert frozen.status_code == 200, frozen.text
        assert len(frozen.json()["manifest"]["run_ids"]) == 8

        # Donduruktan sonra çözülen run eğitime girmez.
        _run(db_session, disp=19.5)
        trained = client.post("/surrogate/scalar/train", params={"corpus_name": "kiris"})
        assert trained.status_code == 200, trained.text
        body = trained.json()
        assert body["n_samples"] == 8
        assert body["corpus"]["source"] == "manifest"
        assert body["corpus"]["name"] == "kiris"

        listed = client.get("/surrogate/corpus")
        assert [m["name"] for m in listed.json()["manifests"]] == ["kiris"]

        missing = client.post("/surrogate/scalar/train", params={"corpus_name": "yok"})
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_membership_separates_auto_and_manual(db_session, tmp_path, monkeypatch):
    for i in range(8):
        _run(db_session, disp=18.0 + i)
    monkeypatch.setattr("app.ml.manifest.MANIFEST_DIR", tmp_path)

    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        client.post("/surrogate/corpus/freeze", params={"name": "kiris"})
        auto_ids = load_manifest("kiris", root=tmp_path)["run_ids"]

        clean = _run(db_session, disp=21.0)
        noisy = _run(db_session, disp=300.0)
        client.post("/surrogate/corpus/kiris/add", json={"run_ids": [clean.id]})
        client.post(
            "/surrogate/corpus/kiris/add",
            json={"run_ids": [noisy.id], "override": True},
        )

        res = client.get("/surrogate/corpus/kiris/membership")
        assert res.status_code == 200
        body = res.json()
        assert body["auto"] == auto_ids
        assert body["manual_pass"] == [clean.id]
        assert body["manual_override"] == [noisy.id]
        assert body["notes"][str(noisy.id)]["reason"] == "large_displacement"

        assert client.get("/surrogate/corpus/yok/membership").status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_evaluate_and_add_endpoints(db_session, tmp_path, monkeypatch):
    for i in range(8):
        _run(db_session, disp=18.0 + i)
    monkeypatch.setattr("app.ml.manifest.MANIFEST_DIR", tmp_path)

    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        client.post("/surrogate/corpus/freeze", params={"name": "kiris"})
        noisy = _run(db_session, disp=300.0)

        ev = client.post(
            "/surrogate/corpus/kiris/evaluate", json={"run_ids": [noisy.id]}
        )
        assert ev.status_code == 200
        assert ev.json()["verdicts"][0]["reason"] == "large_displacement"
        # evaluate hiçbir şey eklememeli
        assert len(load_manifest("kiris", root=tmp_path)["run_ids"]) == 8

        blocked = client.post(
            "/surrogate/corpus/kiris/add", json={"run_ids": [noisy.id]}
        )
        assert blocked.json()["added"] == []

        forced = client.post(
            "/surrogate/corpus/kiris/add",
            json={"run_ids": [noisy.id], "override": True},
        )
        assert forced.json()["added"] == [noisy.id]
        assert len(load_manifest("kiris", root=tmp_path)["run_ids"]) == 9
    finally:
        app.dependency_overrides.pop(get_db, None)
