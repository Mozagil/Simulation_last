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
    _run(db_session, element_size=40.0, disp=19.0)   # es/t = 4.0 → yakınsamamış
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
    assert corpus.dropped["mesh_too_coarse"] == 1
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


def test_study_id_restricts_corpus_to_that_doe_box(db_session):
    """Süzgeç 'tutarsız mı' der, 'planladığım kutudan mı' demez.

    Gerçek vaka (study 3): DOE kutusu F ≤ 220 N iken, elle çözülen bir
    doğrulama koşusu (F = 1000 N) süzgeci geçip sete girdi. OOD koruması
    min–maks kutusu olduğu için tek bir aykırı örnek koruma sınırını
    F=1000'e taşıyor ve F=900 "eğitim uzayı içinde" sayılıyor.
    """
    from app.models.doe import DoeCase, DoeStudy

    study = DoeStudy(name="kutu", template_id="cantilever_beam", seed=1, spec={}, status="completed")
    db_session.add(study)
    db_session.flush()

    in_box = [_run(db_session, disp=18.0 + i, fy=-200.0 - 5 * i) for i in range(8)]
    for i, r in enumerate(in_box):
        db_session.add(
            DoeCase(
                study_id=study.id,
                index=i,
                run_id=r.id,
                geometry_params={"length": 500.0},
                element_size=8.0,
                material_id=1,
                scenario_name="uc_yuk",
                status="solved",
            )
        )
    db_session.commit()

    # Kutunun dışında, ama süzgecin hiçbir kuralını ihlal etmiyor:
    # aynı aile, aynı malzeme, aynı mesh oranı, u/L küçük.
    outlier = _run(db_session, disp=30.0, fy=-1000.0)

    wide = select_training_runs(db_session)
    assert outlier.id in wide.run_ids, "süzgeç tek başına kutu dışını elemez"

    pinned = select_training_runs(db_session, CorpusSpec(study_id=study.id))
    assert pinned.n_kept == 8
    assert set(pinned.run_ids) == {r.id for r in in_box}
    assert outlier.id not in pinned.run_ids
    assert pinned.as_public()["study_id"] == study.id


def test_study_id_survives_manifest_round_trip(tmp_path, db_session):
    from app.ml.manifest import save_manifest, spec_from_manifest

    corpus = select_training_runs(
        db_session, CorpusSpec(template_id="cantilever_beam", study_id=42)
    )
    payload = save_manifest("kutu-test", corpus, root=tmp_path)
    assert payload["spec"]["study_id"] == 42
    assert spec_from_manifest(payload).study_id == 42


def test_yakinsamamis_cozum_korpusa_girmez(db_session):
    """TODO madde 3: adımı tamamlamamış çözüm eğitim setine girmemeli.

    Kaydı olmayan (bu alan eklenmeden önce çözülmüş) run'lar DÜŞMEZ —
    onlar lineer tek-artımlı; düşürmek mevcut kiriş setini boşaltırdı.
    """
    kept = [_run(db_session, disp=18.0 + i, fy=-400.0 - 10 * i) for i in range(8)]
    bad = _run(db_session, disp=20.5)
    bad.scalars = dict(bad.scalars) | {"_solver_converged": 0.0, "_final_step_time": 0.15}
    ok_nl = _run(db_session, disp=21.5)
    ok_nl.scalars = dict(ok_nl.scalars) | {"_solver_converged": 1.0, "_n_cutbacks": 2.0}
    db_session.commit()

    corpus = select_training_runs(db_session)
    assert bad.id not in corpus.run_ids
    assert corpus.dropped.get("not_converged") == 1
    assert ok_nl.id in corpus.run_ids
    assert {r.id for r in kept} <= set(corpus.run_ids)


def _plate_run(db, *, height, width, thickness, diameter, ratio, fx=20000.0, disp=0.03):
    g = Geometry(
        original_filename="p.step",
        current_filename="p.step",
        template_id="plate_with_hole",
        template_params={"height": height, "width": width, "thickness": thickness, "diameter": diameter},
    )
    db.add(g)
    db.flush()
    r = AnalysisRun(
        geometry_id=g.id,
        dimension=3,
        element_size=ratio * diameter,  # DOE: oran x karakteristik uzunluk (= d)
        element_scheme="tet",
        bcs=[{"type": "fixed", "face_ids": [1]}, {"type": "cload", "fx": fx}],
        materials_snapshot=[{"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}],
        status="solved",
        scalars={"max_displacement": disp, "max_von_mises": 150.0, "node_count": 5000,
                 "_analysis_type": "static"},
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_mesh_orani_sablonun_karakteristik_uzunluguyla_hesaplanir(db_session):
    """Plakada DOE mesh'i d ile kurar. Kalınlık çok değişse de es/d sabitse
    hiçbiri mesh aykırısı değildir. Eskiden es/T kullanılıyordu: study 5'te
    114 geçerli örneğin 45'i böyle atıldı."""
    thicknesses = [4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 4.5, 11.0, 7.0, 9.0]
    runs = [
        _plate_run(db_session, height=200.0, width=100.0, thickness=t,
                   diameter=12.0 + 2.5 * i, ratio=0.18)
        for i, t in enumerate(thicknesses)
    ]
    corpus = select_training_runs(db_session, CorpusSpec(template_id="plate_with_hole"))
    assert corpus.dropped.get("mesh_outlier", 0) == 0
    assert set(corpus.run_ids) == {r.id for r in runs}
    assert corpus.mesh_ratio_median == pytest.approx(0.18)


def test_kiriste_mesh_orani_degismedi(db_session):
    """Kirişte karakteristik uzunluk = kalınlık: eski ve yeni hesap aynı."""
    from app.ml.corpus import _mesh_ratio

    r = _run(db_session, thickness=10.0, element_size=8.0)
    geo = db_session.get(Geometry, r.geometry_id)
    assert _mesh_ratio(r, geo) == pytest.approx(0.8)


# --- yakınsama kapısı (TODO 6) -------------------------------------------------


def test_kaba_mesh_elenir_hepsi_kabaysa_da(db_session):
    """`mesh_ratio_band` bir TUTARLILIK bandı: korpusun tamamı kabaysa
    hepsini geçirir. ÖLÇÜLDÜ: es/t 0.8'den 1.0'a çıkınca gerilme yayılımı
    %3.45'ten %9.53'e fırlıyor — yakınsamamış koşu hedefin kendisini
    oynatıyor."""
    for i in range(8):
        _run(db_session, element_size=25.0, disp=18.0 + i)   # es/t = 2.5

    corpus = select_training_runs(db_session)

    assert corpus.n_kept == 0
    assert corpus.dropped["mesh_too_coarse"] == 8


def test_ince_mesh_kalir(db_session):
    for i in range(8):
        _run(db_session, element_size=5.0, disp=18.0 + i)    # es/t = 0.5
    corpus = select_training_runs(db_session)
    assert corpus.n_kept == 8
    assert "mesh_too_coarse" not in corpus.dropped


def test_kapi_kapatilabilir(db_session):
    """Mühendislik kararı kullanıcıya ait: eşik gevşetilebilir."""
    for i in range(8):
        _run(db_session, element_size=25.0, disp=18.0 + i)

    corpus = select_training_runs(db_session, CorpusSpec(max_mesh_ratio=None))

    assert corpus.n_kept == 8
    assert corpus.as_public()["max_mesh_ratio"] is None


def test_kapi_ve_bant_farkli_isler_yapar(db_session):
    """Kapı mutlak incelik, bant medyandan sapma. İkisi ayrı sayılmalı."""
    for i in range(8):
        _run(db_session, element_size=8.0, disp=18.0 + i)     # es/t = 0.8 (medyan)
    _run(db_session, element_size=40.0, disp=19.0)            # kaba → kapı
    _run(db_session, element_size=1.0, disp=19.5)             # ince ama aykırı → bant

    corpus = select_training_runs(db_session)

    assert corpus.dropped["mesh_too_coarse"] == 1
    assert corpus.dropped["mesh_outlier"] == 1
    assert corpus.n_kept == 8
