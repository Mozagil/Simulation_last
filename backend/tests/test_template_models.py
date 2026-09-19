"""Şablona özgü özellik vektörü, şablon başına model saklama, hibrit tür.

NEDEN: özellik vektörü kirişe sabitlenmişti (length/thickness/width) —
delikli plakada `diameter` ve `height` hiç özellik değildi. Model dosyaları
tek ve global olduğu için plaka eğitimi kiriş modelinin üzerine yazıyordu.
"""

from __future__ import annotations

import joblib
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ml.model_store import ModelStoreError, list_models, load_model, model_path, save_model
from app.ml.scalar_features import (
    FEATURE_KEYS,
    MixedTemplateError,
    collect_template_table,
    feature_keys_for,
    features_from_run,
)
from app.ml.scalar_loglinear import (
    LEGACY_SPEC,
    design_keys_of,
    design_spec_for,
    predict_scalar_loglinear,
    train_scalar_hybrid,
    train_scalar_loglinear,
)
from app.ml.scalar_rf import train_scalar_rf
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.run import AnalysisRun

PLATE_KEYS = feature_keys_for("plate_with_hole")


# --- özellik anahtarları -----------------------------------------------------


def test_kiris_anahtarlari_eski_vektorle_birebir_ayni():
    """Kaydedilmiş kiriş modelleri ve eski bundle'lar bu sırayı varsayar."""
    assert feature_keys_for("cantilever_beam") == FEATURE_KEYS


def test_plaka_delik_capini_ve_yuksekligi_gorur():
    assert "diameter" in PLATE_KEYS
    assert "height" in PLATE_KEYS
    assert "length" not in PLATE_KEYS


def test_kategorik_alan_gosterge_olur():
    keys = feature_keys_for("notched_bar")
    assert "notch_kind=u" in keys and "notch_kind=v" in keys


def test_bilinmeyen_sablon_eski_anahtarlara_duser():
    assert feature_keys_for("yok_boyle_sablon") == FEATURE_KEYS
    assert feature_keys_for(None) == FEATURE_KEYS


# --- DB'den tablo --------------------------------------------------------------


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tm.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _run(db, template_id, params, *, fx=0.0, fy=0.0, es=4.0, disp=0.05, vm=150.0):
    g = Geometry(
        original_filename="x.step", current_filename="x.step",
        template_id=template_id, template_params=params,
    )
    db.add(g)
    db.flush()
    r = AnalysisRun(
        geometry_id=g.id, dimension=3, element_size=es, element_scheme="tet",
        bcs=[{"type": "fixed", "face_ids": [1]}, {"type": "cload", "fx": fx, "fy": fy}],
        materials_snapshot=[{"youngs_modulus": 210e9, "poisson_ratio": 0.3}],
        status="solved",
        scalars={"max_displacement": disp, "max_von_mises": vm, "_analysis_type": "static"},
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r, g


def test_plaka_run_vektoru_delik_capini_tasir(db):
    r, g = _run(db, "plate_with_hole",
                {"height": 200.0, "width": 100.0, "thickness": 5.0, "diameter": 24.0}, fx=30000.0)
    x = features_from_run(r, g)
    assert x[PLATE_KEYS.index("diameter")] == 24.0
    assert x[PLATE_KEYS.index("load_fx")] == 30000.0


def test_kategorik_parametre_vektore_girer(db):
    r, g = _run(db, "notched_bar",
                {"length": 200.0, "width": 40.0, "thickness": 8.0, "notch_radius": 2.0,
                 "notch_depth": 5.0, "v_angle_deg": 60.0, "notch_kind": "v"}, fx=1000.0)
    keys = feature_keys_for("notched_bar")
    x = features_from_run(r, g)
    assert x[keys.index("notch_kind=v")] == 1.0
    assert x[keys.index("notch_kind=u")] == 0.0


def test_korpus_tablosu_sablonun_anahtarlarini_kullanir(db):
    ids = [
        _run(db, "plate_with_hole",
             {"height": 200.0, "width": 100.0, "thickness": 5.0, "diameter": 10.0 + i},
             fx=1000.0)[0].id
        for i in range(3)
    ]
    X, _Y, got, keys, tpl = collect_template_table(db, ids)
    assert tpl == "plate_with_hole"
    assert keys == PLATE_KEYS
    assert list(X[:, keys.index("diameter")]) == [10.0, 11.0, 12.0]
    assert got == ids


def test_karisik_sablon_korpusu_reddedilir(db):
    a, _ = _run(db, "plate_with_hole",
                {"height": 200.0, "width": 100.0, "thickness": 5.0, "diameter": 20.0}, fx=1.0)
    b, _ = _run(db, "cantilever_beam",
                {"length": 500.0, "thickness": 10.0, "width": 50.0}, fy=-1.0)
    with pytest.raises(MixedTemplateError):
        collect_template_table(db, [a.id, b.id])


# --- log tasarımı --------------------------------------------------------------


def _beam(n=80, seed=1):
    rng = np.random.default_rng(seed)
    L, T, W = rng.uniform(400, 700, n), rng.uniform(10, 16, n), rng.uniform(40, 70, n)
    F = rng.uniform(40, 220, n)
    X = np.zeros((n, len(FEATURE_KEYS)))
    idx = {k: i for i, k in enumerate(FEATURE_KEYS)}
    X[:, idx["length"]], X[:, idx["thickness"]], X[:, idx["width"]] = L, T, W
    X[:, idx["element_size"]] = rng.uniform(0.5, 0.8, n) * T
    X[:, idx["youngs_modulus"]], X[:, idx["poisson_ratio"]] = 210e9, 0.3
    X[:, idx["load_fy"]], X[:, idx["dimension"]] = -F, 3.0
    I = W * T**3 / 12
    y = np.column_stack([F * L**3 / (3 * 210000 * I), F * L * (T / 2) / I])
    return X, y


def _plate(n=160, seed=2):
    """Peterson Kt(d/W) ile — saf kuvvet yasası DEĞİL."""
    rng = np.random.default_rng(seed)
    H, W, T = rng.uniform(150, 300, n), rng.uniform(70, 140, n), rng.uniform(4, 12, n)
    D = rng.uniform(0.1, 0.45, n) * W
    F = rng.uniform(5e3, 6e4, n)
    X = np.zeros((n, len(PLATE_KEYS)))
    idx = {k: i for i, k in enumerate(PLATE_KEYS)}
    for k, v in (("height", H), ("width", W), ("thickness", T), ("diameter", D),
                 ("element_size", rng.uniform(0.12, 0.25, n) * D), ("youngs_modulus", 210e9),
                 ("poisson_ratio", 0.3), ("load_fx", F), ("dimension", 3.0)):
        X[:, idx[k]] = v
    r = D / W
    kt = 3 - 3.14 * r + 3.667 * r**2 - 1.527 * r**3
    sigma = kt * F / ((W - D) * T)
    u = F * H / (210000 * W * T) * (1 + 0.9 * r**2)
    return X, np.column_stack([u, sigma])


def test_kiris_tasarimi_eski_sabit_tasarimla_ayni():
    X, _ = _beam()
    spec = design_spec_for(FEATURE_KEYS, X)
    assert spec["log_keys"] == LEGACY_SPEC["log_keys"]
    assert spec["abs_log_keys"] == LEGACY_SPEC["abs_log_keys"]
    assert spec["indicator_keys"] == []


def test_plaka_tasarimi_sifir_olmayan_yuku_ve_capi_alir():
    X, _ = _plate()
    spec = design_spec_for(PLATE_KEYS, X)
    assert "diameter" in spec["log_keys"]
    assert spec["abs_log_keys"] == ["load_fx"], "sıfır yük sütunları tasarıma girmemeli"
    assert "|load_fx|" in design_keys_of(spec)


def test_eski_bundle_ayni_tahmini_verir():
    """design_spec taşımayan (bu değişiklikten önce kaydedilmiş) kiriş
    bundle'ı eski sabit tasarımla okunur ve AYNI sonucu verir."""
    X, y = _beam()
    new = train_scalar_loglinear(X, y, feature_keys=FEATURE_KEYS)
    old = dict(new)
    old.pop("design_spec")
    for row in X[:5]:
        a = predict_scalar_loglinear(new, row)["predictions"]
        b = predict_scalar_loglinear(old, row)["predictions"]
        assert a["max_displacement"] == pytest.approx(b["max_displacement"], rel=1e-12)


def test_hibrit_kuvvet_yasasi_olmayan_hedefte_log_logu_gecer():
    X, y = _plate()
    ll = train_scalar_loglinear(X, y, feature_keys=PLATE_KEYS)
    hy = train_scalar_hybrid(X, y, feature_keys=PLATE_KEYS)
    assert hy["kind"] == "scalar_hybrid"
    m_ll = ll["metrics"]["test"]["max_von_mises"]["mape"]
    m_hy = hy["metrics"]["test"]["max_von_mises"]["mape"]
    assert m_hy < m_ll, (m_hy, m_ll)
    # hibrit tahmini de aynı sözleşmeyle gelir
    p = predict_scalar_loglinear(hy, X[0])
    assert set(p) == {"kind", "predictions", "out_of_domain"}
    assert p["predictions"]["max_von_mises"] == pytest.approx(y[0, 1], rel=0.05)


def test_ozellik_sayisi_uyusmazsa_hata():
    X, y = _plate(n=20)
    with pytest.raises(ValueError, match="özellik anahtarı"):
        train_scalar_loglinear(X, y, feature_keys=FEATURE_KEYS)
    with pytest.raises(ValueError, match="özellik anahtarı"):
        train_scalar_rf(X, y, feature_keys=FEATURE_KEYS)


# --- şablon başına saklama ----------------------------------------------------


def test_sablon_basina_kayit_birbirini_ezmez(tmp_path):
    save_model("cantilever_beam", "loglinear", {"kind": "k", "v": 1}, root=tmp_path)
    save_model("plate_with_hole", "loglinear", {"kind": "p", "v": 2}, root=tmp_path)
    assert load_model("cantilever_beam", "loglinear", root=tmp_path)["v"] == 1
    assert load_model("plate_with_hole", "loglinear", root=tmp_path)["v"] == 2
    assert list_models(root=tmp_path) == {
        "cantilever_beam": ["loglinear"], "plate_with_hole": ["loglinear"],
    }


def test_eski_global_dosya_yalniz_kendi_sablonuna_yedek(tmp_path):
    """Eski global dosya silinmez; korpusu hangi şablonsa yalnız ona döner."""
    joblib.dump({"kind": "scalar_loglinear", "corpus": {"template_id": "cantilever_beam"}},
                tmp_path / "scalar_loglinear.joblib")
    got = load_model("cantilever_beam", "loglinear", root=tmp_path)
    assert got is not None and got["legacy_path"].endswith("scalar_loglinear.joblib")
    assert load_model("plate_with_hole", "loglinear", root=tmp_path) is None
    assert list_models(root=tmp_path) == {"cantilever_beam": ["loglinear"]}


def test_sablon_klasoru_eski_dosyaya_oncelikli(tmp_path):
    joblib.dump({"v": "eski", "corpus": {"template_id": "cantilever_beam"}},
                tmp_path / "scalar_rf.joblib")
    save_model("cantilever_beam", "rf", {"v": "yeni"}, root=tmp_path)
    assert load_model("cantilever_beam", "rf", root=tmp_path)["v"] == "yeni"


@pytest.mark.parametrize("tpl, kind", [("../kiris", "rf"), ("Plate", "rf"), ("plate", "xgb")])
def test_gecersiz_ad_ya_da_tur_reddedilir(tmp_path, tpl, kind):
    with pytest.raises(ModelStoreError):
        model_path(tpl, kind, root=tmp_path)
