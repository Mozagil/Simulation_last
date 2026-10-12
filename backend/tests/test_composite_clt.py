"""Faz 3.4 — POST /composite/clt (DB yok)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.composite import router as composite_router
from app.composite.layup import Ply, abd_matrix

app = FastAPI()
app.include_router(composite_router)
client = TestClient(app)

_T300 = dict(e1=135e9, e2=10e9, g12=5.2e9, nu12=0.30)


def _ply(angle: float, t: float = 0.125) -> dict:
    return {**_T300, "thickness_mm": t, "angle_deg": angle}


def test_clt_symmetric_0_90_0_matches_abd_matrix():
    plies = [_ply(0.0), _ply(90.0), _ply(0.0)]
    response = client.post("/composite/clt", json={"plies": plies})
    assert response.status_code == 200
    body = response.json()
    assert body["n_plies"] == 3
    assert body["h_mm"] == 0.375
    expect = abd_matrix(
        [Ply(**_T300, thickness_mm=p["thickness_mm"], angle_deg=p["angle_deg"]) for p in plies]
    )
    assert body["A_N_per_mm"] == expect.A.tolist()
    assert body["B_N"] == expect.B.tolist()
    assert body["D_N_mm"] == expect.D.tolist()
    assert body["A_N_per_mm"][0][0] > body["A_N_per_mm"][1][1]
    assert abs(body["B_N"][0][0]) < 1e-9


def test_clt_empty_plies_rejected():
    response = client.post("/composite/clt", json={"plies": []})
    assert response.status_code == 422


def test_clt_nonpositive_thickness_rejected():
    response = client.post("/composite/clt", json={"plies": [_ply(0.0, 0.0)]})
    assert response.status_code == 422
