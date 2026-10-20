"""1.19e — /crash/ml: korpus özeti, eğitim, model listesi / detayı, tahmin."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.api.crash_ml as crash_ml
from app.main import app
from app.ml.crash import surrogate
from tests.test_crash_ml_surrogate import _corpus

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    # Model klasörü geçici; korpus sentetik (DB gerekmez).
    monkeypatch.setattr(surrogate, "MODELS_ROOT", tmp_path)
    monkeypatch.setattr(crash_ml, "load_crash_corpus", lambda _db, *_a, **_k: _corpus())


def test_targets_and_corpus():
    t = client.get("/crash/ml/targets").json()["targets"]
    assert [x["key"] for x in t] == ["peak_force_kn", "mean_force_kn", "energy_absorbed_j", "crush_mm"]
    s = client.post("/crash/ml/corpus", json={"template_id": "crash_box_shell"}).json()
    assert s["n_runs"] == 40 and s["study_id"] == 7


def test_train_list_get_predict():
    r = client.post("/crash/ml/train", json={"template_id": "crash_box_shell", "scenario": "rigid_wall"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["n_runs"] == 40 and m["feature_keys"] == ["req.barrier.speed_m_s", "geom.wall"]
    tgt = {t["key"]: t for t in m["targets"]}
    assert tgt["peak_force_kn"]["trained"] and tgt["peak_force_kn"]["cv"]["r2"] > 0.9
    assert m["requested_kind"] == "auto" and tgt["peak_force_kn"]["kind"] in ("rf", "loglinear", "hybrid")
    assert set(tgt["peak_force_kn"]["cv"]["kinds"]) == {"rf", "loglinear", "hybrid"}
    r2 = client.post("/crash/ml/train", json={"template_id": "crash_box_shell", "scenario": "rigid_wall", "kind": "rf"})
    assert r2.status_code == 200 and r2.json()["requested_kind"] == "rf"
    assert client.post("/crash/ml/train", json={"template_id": "crash_box_shell", "scenario": "rigid_wall", "kind": "svm"}).status_code == 422
    assert not tgt["crush_mm"]["trained"] and tgt["crush_mm"]["unit"] == "mm"

    models = client.get("/crash/ml/models").json()["models"]
    assert [(x["template_id"], x["scenario"]) for x in models] == [("crash_box_shell", "rigid_wall")]
    assert client.get("/crash/ml/models/crash_box_shell/rigid_wall").json()["study_id"] == 7

    p = client.post("/crash/ml/predict", json={
        "template_id": "crash_box_shell", "inputs": {"req.barrier.speed_m_s": 10.0, "geom.wall": 2.0},
    }).json()
    assert p["prediction"]["peak_force_kn"] == pytest.approx(100.0, rel=0.1) and p["out_of_domain"] == []


def test_errors():
    assert client.get("/crash/ml/models/crash_box_shell/rigid_wall").status_code == 404
    assert client.get("/crash/ml/models/BAD!/x").status_code == 422
    client.post("/crash/ml/train", json={"template_id": "crash_box_shell"})
    r = client.post("/crash/ml/predict", json={"template_id": "crash_box_shell", "inputs": {"geom.wall": 2.0}})
    assert r.status_code == 422 and "speed" in r.json()["detail"]
