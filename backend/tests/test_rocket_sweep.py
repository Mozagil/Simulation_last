"""R5 — Mach × α taraması: nokta ızgarası, tablo (CNα eğimi), CSV."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

import app.api.cfd_sweep as sw
from app.main import app
from app.postprocess.rocket_table import aero_table


def test_aero_table_slope_and_cd():
    pts = [
        {"mach": 0.5, "alpha_deg": 0, "CN": 0.0, "CD": 0.40, "x_cp_m": None},
        {"mach": 0.5, "alpha_deg": 4, "CN": 0.70, "CD": 0.45, "x_cp_m": 1.10},
        {"mach": 0.5, "alpha_deg": 8, "CN": 1.40, "CD": 0.55, "x_cp_m": 1.20},
        {"mach": 1.5, "alpha_deg": 4, "CN": 0.90, "CD": 0.70, "x_cp_m": 1.0},
        {"mach": 1.5, "alpha_deg": 8, "status": "failed"},
    ]
    t = aero_table(pts)
    assert [r["mach"] for r in t] == [0.5, 1.5]
    assert t[0]["CD_alpha_min"] == 0.40 and t[0]["n_points"] == 3
    assert t[0]["CN_alpha_per_rad"] == pytest.approx(0.70 / math.radians(4))
    assert t[0]["x_cp_m_mean"] == pytest.approx(1.15)
    assert t[1]["CN_alpha_per_rad"] == pytest.approx(0.90 / math.radians(4))


def test_sweep_endpoint_runs_points(monkeypatch, tmp_path):
    monkeypatch.setattr(sw, "SWEEP_DIR", tmp_path)
    seen = []

    def fake_solve(req, bg, db):
        seen.append((req.speed_m_s, req.alpha_deg, req.solver, req.wait))
        cn = 10.0 * math.radians(req.alpha_deg)
        return {"job_id": f"j{len(seen)}", "status": "solved", "message": "ok",
                "rocket_aero": {"CN": cn, "CD": 0.3 + req.speed_m_s / 1000, "CA": 0.3, "x_cp_m": 1.1}}

    monkeypatch.setattr(sw, "rocket_solve", fake_solve)
    c = TestClient(app)
    r = c.post("/cfd/rocket/sweep", json={"mesh_id": "m", "machs": [0.3, 0.6], "alphas_deg": [0, 4], "solver": "rhoSimpleFoam", "wait": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "done" and len(d["points"]) == 4
    a = 340.294
    assert seen[0][0] == pytest.approx(0.3 * a, rel=1e-3) and all(s[2] == "rhoSimpleFoam" and s[3] for s in seen)
    assert d["table"][1]["CN_alpha_per_rad"] == pytest.approx(10.0)
    csv = c.get(f"/cfd/rocket/sweep/{d['sweep_id']}/csv").text.splitlines()
    assert csv[0] == "mach,n_points,CD_alpha_min,alpha_min_deg,CN_alpha_per_rad,x_cp_m_mean" and len(csv) == 3
    pts = c.get(f"/cfd/rocket/sweep/{d['sweep_id']}/csv", params={"kind": "points"}).text.splitlines()
    assert len(pts) == 5 and pts[0].startswith("mach,alpha_deg,speed_m_s")
    assert c.get("/cfd/rocket/sweep/yok").status_code == 404
