"""2.9 — CFD DOE (örnekleme + sıralı koşu) ve vekil model (korpus, eğitim, tahmin)."""

from __future__ import annotations

import math
import uuid

import pytest
from fastapi.testclient import TestClient

import app.api.cfd_ml as ml
from app.db.session import SessionLocal
from app.main import app
from app.ml.cfd.corpus import load_cfd_corpus, run_features
from app.models.cfd_run import CfdRun

TUNNEL = {"base_cell_m": 0.3}


def test_run_features_categorical():
    f = run_features({"mach": 0.3, "alpha_deg": 4, "x_ref_m": 0.9, "speed_m_s": 100}, {"nose_shape": "ogive", "fin_span": 100})
    assert f == {"flow.mach": 0.3, "flow.alpha_deg": 4.0, "flow.x_ref_m": 0.9, "geom.fin_span": 100.0, "geom.nose_shape#ogive": 1.0}


def test_sample_doe_lhs_and_validation():
    body = ml.CfdDoeRequest(ranges={"fin_span": (80, 120), "mach": (0.2, 0.6)}, n_samples=6, tunnel=TUNNEL, template_params={"nose_shape": "ogive"})
    s = ml.sample_doe(body)
    assert len(s) == 6 and all(80 <= x["template_params"]["fin_span"] <= 120 for x in s)
    assert all(x["template_params"]["nose_shape"] == "ogive" and x["alpha_deg"] == 4.0 for x in s)
    # LHS: her dilimde bir örnek
    assert sorted(int((x["mach"] - 0.2) / 0.4 * 6) for x in s) == list(range(6))
    with pytest.raises(ValueError):
        ml.CfdDoeRequest(ranges={"nose_shape": (0, 1)}, tunnel=TUNNEL)


def test_doe_runs_samples_sequentially(monkeypatch, tmp_path):
    monkeypatch.setattr(ml, "DOE_DIR", tmp_path)
    calls = []

    class G:
        def __init__(self, i):
            self.id = i

    def fake_geo(db, tid, params):
        calls.append(("geo", params["fin_span"]))
        if len([c for c in calls if c[0] == "geo"]) == 2:
            raise ValueError("geçersiz")
        return G(len(calls)), {}, None

    monkeypatch.setattr(ml, "create_geometry_from_template", fake_geo)
    monkeypatch.setattr(ml, "cfd_mesh", lambda req, bg, db: {"mesh_id": f"m{req.geometry_id}", "status": "meshed", "check": {"cells": 1000}})
    monkeypatch.setattr(ml, "rocket_solve", lambda req, bg, db: {"job_id": "j-" + req.mesh_id, "status": "solved", "message": "ok", "rocket_aero": {"CD": 0.3, "CN": 1.0, "x_cp_m": 1.1}})
    r = TestClient(app).post("/cfd/ml/doe", json={"ranges": {"fin_span": [80, 120]}, "n_samples": 3, "tunnel": TUNNEL, "solve": {"solver": "simpleFoam", "iterations": 50}, "wait": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "done" and d["message"] == "2/3 örnek çözüldü"
    assert [s["status"] for s in d["samples"]] == ["solved", "failed", "solved"]
    assert d["samples"][0]["aero"]["CD"] == 0.3 and d["samples"][1]["message"].startswith("ValueError")
    assert TestClient(app).get("/cfd/ml/doe").json()["does"][0]["n_samples"] == 3


def test_corpus_train_predict(monkeypatch, tmp_path):
    monkeypatch.setattr(ml, "MODELS_ROOT", tmp_path)
    tag = uuid.uuid4().hex[:8]
    job_ids = []
    with SessionLocal() as db:
        try:
            db.query(CfdRun).limit(1).all()
        except Exception:  # noqa: BLE001
            pytest.skip("veritabanı yok")
        for i in range(12):
            m, a = 0.1 + 0.05 * i, float(i % 4) * 2
            jid = f"t29-{tag}-{i}"
            job_ids.append(jid)
            db.add(CfdRun(
                job_id=jid, application="simpleFoam", status="solved", solver_ran=True,
                request={"rocket": {"mach": m, "alpha_deg": a, "x_ref_m": 0.9}},
                scalars={}, diagnostics={},
                reference={"kind": "rocket_r3", "aero": {"CD": 0.25 + m * 0.1, "CN": 10 * math.radians(a), "CA": 0.25, "CL": 0.1, "Cm": -1.0, "x_cp_m": 1.1}},
            ))
        db.add(CfdRun(job_id=f"t29-{tag}-x", application="simpleFoam", status="failed", request={}, scalars={}, diagnostics={}))
        job_ids.append(f"t29-{tag}-x")
        db.commit()
        c = load_cfd_corpus(db, "simpleFoam", job_ids=job_ids)
    assert len(c.run_ids) == 12 and c.feature_names == ["flow.alpha_deg", "flow.mach"]
    assert c.constant_features == {"flow.x_ref_m": 0.9} and c.dropped == {"durum failed": 1}

    monkeypatch.setattr(ml, "read_doe", lambda i: {"samples": [{"job_id": j} for j in job_ids]})
    client = TestClient(app)
    r = client.post("/cfd/ml/train", json={"application": "simpleFoam", "doe_id": "d", "n_folds": 3})
    assert r.status_code == 200, r.text
    t = {x["key"]: x for x in r.json()["targets"]}
    assert t["CN"]["trained"] and t["CN"]["cv"]["n"] == 12
    p = client.post("/cfd/ml/predict", json={"application": "simpleFoam", "inputs": {"flow.mach": 0.3, "flow.alpha_deg": 9}})
    assert p.status_code == 200 and p.json()["out_of_domain"] == ["flow.alpha_deg"]
    assert client.post("/cfd/ml/predict", json={"application": "rhoCentralFoam", "inputs": {}}).status_code == 404
    with SessionLocal() as db:
        db.query(CfdRun).filter(CfdRun.job_id.in_(job_ids)).delete(synchronize_session=False)
        db.commit()
