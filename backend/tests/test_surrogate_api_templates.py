"""API: şablon başına model, hibrit tür, şablonlu tahmin (0.6.4 — adım B).

NEDEN: eğitim tek global dosyaya yazıyordu; plaka eğitimi kiriş modelinin
üzerine yazardı ve özellik vektörleri farklı olduğu için okunamazdı.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.ml.model_store as store
from app.api.surrogate import ParamPredictBody, predict_from_params, surrogate_status, train_scalar
from app.main import app
from app.ml.model_store import load_model
from app.ml.scalar_features import feature_keys_for
from app.ml.scalar_loglinear import train_scalar_hybrid
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.run import AnalysisRun

PLATE = "plate_with_hole"
PLATE_KEYS = feature_keys_for(PLATE)


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture()
def store_root(tmp_path, monkeypatch):
    """Model deposu geçici klasöre — gerçek uploads/ kirlenmesin."""
    root = tmp_path / "models"
    monkeypatch.setattr(store, "MODELS_ROOT", root)
    return root


def _plate_runs(db, n=14):
    rng = np.random.default_rng(5)
    out = []
    for i in range(n):
        H, W, T = 200.0 + i, 100.0 + rng.uniform(-8, 8), 5.0 + rng.uniform(-1, 1)
        D = 20.0 + rng.uniform(-6, 6)
        F = 30000.0 + 500 * i
        g = Geometry(
            original_filename="p.step", current_filename="p.step", template_id=PLATE,
            template_params={"height": H, "width": W, "thickness": T, "diameter": D},
        )
        db.add(g)
        db.flush()
        kt = 3 - 3.14 * (D / W) + 3.667 * (D / W) ** 2
        r = AnalysisRun(
            geometry_id=g.id, dimension=3, element_size=0.18 * D, element_scheme="tet",
            bcs=[{"type": "fixed", "face_ids": [1]}, {"type": "cload", "fx": F}],
            materials_snapshot=[{"youngs_modulus": 210e9, "poisson_ratio": 0.3}],
            status="solved",
            scalars={
                "max_displacement": F * H / (210000 * W * T),
                "max_von_mises": kt * F / ((W - D) * T),
                "node_count": 5000,
                "_analysis_type": "static",
            },
        )
        db.add(r)
        out.append(r)
    db.commit()
    return out


def _fake_plate_bundle():
    """Küçük sentetik plaka hibrit modeli (tahmin uçlarını sınamak için)."""
    rng = np.random.default_rng(3)
    n = 60
    X = np.zeros((n, len(PLATE_KEYS)))
    idx = {k: i for i, k in enumerate(PLATE_KEYS)}
    H, W, T = rng.uniform(150, 300, n), rng.uniform(70, 140, n), rng.uniform(4, 12, n)
    D = rng.uniform(0.1, 0.4, n) * W
    F = rng.uniform(5e3, 6e4, n)
    for k, v in (("height", H), ("width", W), ("thickness", T), ("diameter", D),
                 ("element_size", 0.18 * D), ("youngs_modulus", 210e9),
                 ("poisson_ratio", 0.3), ("load_fx", F), ("dimension", 3.0)):
        X[:, idx[k]] = v
    y = np.column_stack([F * H / (210000 * W * T), 2.5 * F / ((W - D) * T)])
    return train_scalar_hybrid(X, y, feature_keys=PLATE_KEYS)


# --- eğitim: şablon klasörüne yazar -------------------------------------------


def test_egitim_sablon_klasorune_yazar_digerini_ezmez(db, store_root):
    store.save_model("cantilever_beam", "loglinear", {"kind": "kiris", "v": 1},
                     root=store_root)
    _plate_runs(db)

    out = train_scalar(db=db, template_id=PLATE, corpus_name=None, model="hybrid")

    assert out["template_id"] == PLATE
    assert out["model_kind"] == "hybrid"
    assert (store_root / PLATE / "scalar_hybrid.joblib").is_file()
    # Kiriş modeli olduğu gibi duruyor
    assert load_model("cantilever_beam", "loglinear", root=store_root)["v"] == 1


def test_egitilen_model_sablonun_anahtarlarini_tasir(db, store_root):
    _plate_runs(db)
    out = train_scalar(db=db, template_id=PLATE, corpus_name=None, model="loglinear")
    assert out["feature_keys"] == list(PLATE_KEYS)
    assert "diameter" in out["feature_keys"]


def test_sablonsuz_korpus_egitilemez(db, store_root):
    g = Geometry(original_filename="x.step", current_filename="x.step",
                 template_id=None, template_params={})
    db.add(g)
    db.flush()
    for _ in range(10):
        db.add(AnalysisRun(
            geometry_id=g.id, dimension=3, element_size=8.0, element_scheme="tet",
            bcs=[{"type": "cload", "fy": -100.0}],
            materials_snapshot=[{"youngs_modulus": 210e9, "poisson_ratio": 0.3}],
            status="solved",
            scalars={"max_displacement": 1.0, "max_von_mises": 10.0,
                     "node_count": 100, "_analysis_type": "static"},
        ))
    db.commit()
    with pytest.raises(Exception) as exc:
        train_scalar(db=db, template_id=None, corpus_name=None, model="rf")
    assert "şablon" in str(exc.value).lower()


def test_bilinmeyen_tur_reddedilir(db, store_root):
    with TestClient(app) as c:
        assert c.post("/surrogate/scalar/train?model=xgboost").status_code == 422


# --- tahmin: şablonlu ----------------------------------------------------------


def test_plaka_tahmini_sablon_modelinden_gelir(db, store_root, monkeypatch):
    store.save_model(PLATE, "hybrid", _fake_plate_bundle(), root=store_root)
    body = ParamPredictBody(
        template_id=PLATE,
        params={"height": 200, "width": 100, "thickness": 5, "diameter": 20},
        element_size=3.6, youngs_modulus=210e9, poisson_ratio=0.3,
        load_fx=30000, dimension=3,
    )
    out = predict_from_params(body=body, db=db, model="auto")
    assert out["model_kind"] == "hybrid"
    assert out["template_id"] == PLATE
    assert out["feature_keys"] == list(PLATE_KEYS)
    # 2.5 × 30000 / ((100−20)×5) = 187.5 MPa mertebesinde
    assert out["predictions"]["max_von_mises"] == pytest.approx(187.5, rel=0.15)


def test_eksik_sablon_alani_acik_hata(db, store_root):
    store.save_model(PLATE, "hybrid", _fake_plate_bundle(), root=store_root)
    body = ParamPredictBody(template_id=PLATE, params={"height": 200, "width": 100},
                            load_fx=30000)
    with pytest.raises(Exception) as exc:
        predict_from_params(body=body, db=db, model="auto")
    msg = str(exc.value)
    assert "thickness" in msg and "diameter" in msg


def test_model_yoksa_sablon_adiyla_404(db, store_root):
    body = ParamPredictBody(template_id=PLATE, params={"height": 1, "width": 1,
                                                       "thickness": 1, "diameter": 1})
    with pytest.raises(Exception) as exc:
        predict_from_params(body=body, db=db, model="auto")
    assert PLATE in str(exc.value)


def test_auto_once_hibriti_secer(db, store_root):
    store.save_model(PLATE, "loglinear", _fake_plate_bundle(), root=store_root)
    body = ParamPredictBody(template_id=PLATE,
                            params={"height": 200, "width": 100, "thickness": 5,
                                    "diameter": 20}, load_fx=30000)
    assert predict_from_params(body=body, db=db, model="auto")["model_kind"] == "loglinear"
    store.save_model(PLATE, "hybrid", _fake_plate_bundle(), root=store_root)
    assert predict_from_params(body=body, db=db, model="auto")["model_kind"] == "hybrid"


# --- durum ---------------------------------------------------------------------


def test_status_sablona_gore_doner(store_root):
    store.save_model(PLATE, "hybrid", {"kind": "scalar_hybrid", "n_samples": 7},
                     root=store_root)
    st = surrogate_status(template_id=PLATE)
    assert st["template_id"] == PLATE
    assert st["scalar_hybrid"]["n_samples"] == 7
    assert st["scalar_rf"] is None
    assert st["templates"] == {PLATE: ["hybrid"]}


def test_mesajda_kullanilan_tur_dogru_yazilir(db, store_root):
    """Mesaj eskiden yalnız log-log/RF ayrımı yapıyordu: hibrit tahmin
    "Tahmin (RF)" diye görünüyordu (tarayıcıda görüldü)."""
    store.save_model(PLATE, "hybrid", _fake_plate_bundle(), root=store_root)
    body = ParamPredictBody(
        template_id=PLATE,
        params={"height": 200, "width": 100, "thickness": 5, "diameter": 20},
        element_size=3.6, load_fx=30000,
    )
    out = predict_from_params(body=body, db=db, model="auto")
    assert out["model_kind"] == "hybrid"
    assert out["message"].startswith("Tahmin (hibrit)")
