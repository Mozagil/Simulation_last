"""Faz 3.13 — ply alanı + köşe geometrisi; GET /composite/runs/{id}/plies."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.composite import _material_dict
from app.api.composite import router as composite_router
from app.composite.field_mesh import parse_shell_mesh, ply_field_with_mesh
from app.db.session import SessionLocal
from app.models.composite import CompositeMaterial, CompositeRun
from app.models.geometry import Geometry
from tests.test_composite_solve import requires_db

app = FastAPI()
app.include_router(composite_router)
client = TestClient(app)

_DECK = """*HEADING
*NODE
1, 0, 0, 0
2, 2, 0, 0
3, 2, 1, 0
4, 0, 1, 0
5, 1, 0, 0
6, 2, 0.5, 0
7, 1, 1, 0
8, 0, 0.5, 0
9, 3, 0, 0
*ELEMENT, TYPE=S8R, ELSET=PART_0
1, 1, 2, 3, 4, 5, 6,
7, 8
*ELEMENT, TYPE=S3, ELSET=PART_0
2, 2, 9, 3
*NODE FILE
U
"""

_FIELD = {
    "f12_star": -0.5,
    "hashin_modes": ["fiber_tension", "fiber_compression", "matrix_tension", "matrix_compression"],
    "sets": {
        "PART_0": {
            "element_ids": [1, 2],
            "plies": [{"material": "T300", "angle_deg": 0.0}, {"material": "T300", "angle_deg": 90.0}],
            "s11": [[10.0, 1.0], [20.0, 2.0]],
            "s22": [[0.5, 5.0], [0.6, 6.0]],
            "s12": [[0.1, 0.1], [0.2, 0.2]],
            "tsai_wu_irf": [[0.01, 0.1], [0.02, 0.12]],
            "hashin_irf": [[0.01, 0.1], [0.02, 0.12]],
            "hashin_mode": [[0, 2], [0, 2]],
        }
    },
}


def test_parse_shell_mesh_corners_and_continuation():
    nodes, elems = parse_shell_mesh(_DECK)
    assert len(nodes) == 9 and nodes[6] == (2.0, 0.5, 0.0)
    assert elems == {1: [1, 2, 3, 4], 2: [2, 9, 3]}


def test_ply_field_with_mesh(tmp_path):
    inp = tmp_path / "crun1.inp"
    inp.write_text(_DECK, encoding="utf-8")
    ply = tmp_path / "crun1_ply.json"
    ply.write_text(json.dumps(_FIELD), encoding="utf-8")
    field = ply_field_with_mesh(inp, ply)
    part = field["sets"]["PART_0"]
    # Yalnız köşe düğümleri, eleman sırasıyla sıkıştırılmış
    assert part["nodes"] == [[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0], [3, 0, 0]]
    assert part["faces"] == [[0, 1, 2, 3], [1, 4, 2]]
    assert part["tsai_wu_irf"] == _FIELD["sets"]["PART_0"]["tsai_wu_irf"]


def test_material_dict_carries_strengths():
    m = CompositeMaterial(
        name="x", density=1.0, e1=1, e2=1, e3=1, nu12=0.3, nu13=0.3, nu23=0.3,
        g12=1, g13=1, g23=1, xt=1.5e9, xc=1.2e9, yt=5e7, yc=2e8, s12=7e7, s23=None,
    )
    d = _material_dict(m)
    assert (d["xt"], d["xc"], d["yt"], d["yc"], d["s12"], d["s23"]) == (1.5e9, 1.2e9, 5e7, 2e8, 7e7, None)


@requires_db
def test_run_plies_endpoint(tmp_path):
    inp = tmp_path / "crunX.inp"
    inp.write_text(_DECK, encoding="utf-8")
    db = SessionLocal()
    try:
        geo = Geometry(original_filename="cres.step", current_filename="cres.step")
        db.add(geo)
        db.commit()
        db.refresh(geo)
        run = CompositeRun(
            job_id=str(uuid.uuid4()),
            geometry_id=geo.id,
            part_id=0,
            dimension=2,
            status="solved",
            solver_ran=True,
            inp_path=str(inp).replace("\\", "/"),
            request={},
            layup_snapshot=[],
            bcs=[],
            scalars={"tsai_wu_irf_max": 0.12},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id, gid = run.id, geo.id
    finally:
        db.close()

    missing = client.get(f"/composite/runs/{run_id}/plies")
    assert missing.status_code == 404
    assert client.get("/composite/runs", params={"geometry_id": gid}).json()["runs"][0]["has_ply_field"] is False

    (tmp_path / "crunX_ply.json").write_text(json.dumps(_FIELD), encoding="utf-8")
    res = client.get(f"/composite/runs/{run_id}/plies")
    assert res.status_code == 200
    body = res.json()
    assert body["run_id"] == run_id
    assert body["scalars"]["tsai_wu_irf_max"] == pytest.approx(0.12)
    assert body["sets"]["PART_0"]["faces"] == [[0, 1, 2, 3], [1, 4, 2]]
    assert client.get("/composite/runs", params={"geometry_id": gid}).json()["runs"][0]["has_ply_field"] is True
    assert client.get("/composite/runs/2147000000/plies").status_code == 404
