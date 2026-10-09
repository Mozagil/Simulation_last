"""R2 — Barrowman CP / CNα (analitik referans, roket şablonu parametreleriyle)."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.postprocess.barrowman import barrowman, nose_volume_mm3
from app.templates.rocket import RocketParams


@pytest.mark.parametrize(
    "shape, ratio",
    [("konik", 2 / 3), ("ogive", 0.4625), ("elips", 1 / 3), ("von_karman", 0.5)],
)
def test_nose_cp_textbook_ratios(shape, ratio):
    """İnce gövde: X = Ln − V/A_taban → koni 2/3, ogive ≈ 0.466, elips 1/3, Haack 1/2."""
    p = RocketParams(nose_shape=shape)
    b = barrowman(p)
    nose = b["components"][0]
    assert nose["name"] == "burun" and nose["cn_alpha"] == pytest.approx(2.0)
    assert nose["x_mm"] / p.nose_length == pytest.approx(ratio, abs=2e-3)


def test_cone_volume_exact():
    p = RocketParams(nose_shape="konik")
    assert nose_volume_mm3(p) == pytest.approx(math.pi * p.radius**2 * p.nose_length / 3, rel=1e-6)


def test_fin_term_by_hand():
    p = RocketParams()  # D 100, s 100, Cr 150, Ct 60, Xs 80, N 4, Xf 0
    fin = barrowman(p)["components"][-1]
    l_m = math.sqrt(100**2 + (80 + 30 - 75) ** 2)
    k = 1 + 50 / 150
    cn = k * 4 * 4 * 1.0 / (1 + math.sqrt(1 + (2 * l_m / 210) ** 2))
    x_b = 1500 - 150
    x = x_b + 80 / 3 * (150 + 120) / 210 + (210 - 150 * 60 / 210) / 6
    assert fin["cn_alpha"] == pytest.approx(cn) and fin["x_mm"] == pytest.approx(x)
    assert fin["interference_k"] == pytest.approx(k)


def test_total_is_weighted_and_stability():
    p = RocketParams()
    b = barrowman(p, cg_mm=900.0)
    comps = b["components"]
    assert b["cn_alpha"] == pytest.approx(sum(c["cn_alpha"] for c in comps))
    assert b["x_cp_mm"] == pytest.approx(sum(c["cn_alpha"] * c["x_mm"] for c in comps) / b["cn_alpha"])
    assert b["stability_calibers"] == pytest.approx((b["x_cp_mm"] - 900.0) / 100.0)
    assert b["a_ref_m2"] == pytest.approx(math.pi * 0.1**2 / 4)


def test_boattail_negative_and_many_fins_note():
    b = barrowman(RocketParams(boattail_length=100, boattail_aft_diameter=80))
    bt = next(c for c in b["components"] if c["name"] == "boattail")
    assert bt["cn_alpha"] == pytest.approx(2 * (0.8**2 - 1))
    assert bt["x_mm"] == pytest.approx(1500 + 100 / 3 * (1 + (1 - 1.25) / (1 - 1.25**2)))
    assert any("N > 4" in n for n in barrowman(RocketParams(fin_count=6, fin_thickness=3)).get("notes", []))


def test_api_params_and_geometry():
    client = TestClient(app)
    r = client.post("/cfd/rocket/barrowman", json={"params": {"nose_shape": "konik"}, "cg_mm": 900})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["params"]["nose_shape"] == "konik" and "stability_calibers" in d
    assert client.post("/cfd/rocket/barrowman", json={}).status_code == 422
    assert client.post("/cfd/rocket/barrowman", json={"params": {"body_length": 10}}).status_code == 422
    gid = client.post("/templates/rocket/create", json={"params": {"nose_shape": "elips"}}).json()["geometry_id"]
    g = client.post("/cfd/rocket/barrowman", json={"geometry_id": gid}).json()
    assert g["params"]["nose_shape"] == "elips"
    assert g["components"][0]["x_mm"] == pytest.approx(100.0, abs=0.5)  # 1/3 · 300
