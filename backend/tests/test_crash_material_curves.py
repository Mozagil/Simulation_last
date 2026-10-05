"""1.14c2 — LAW36 eğrileri malzeme kütüphanesinde (materials.crash_curves)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.solvers.base import SolverError
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params
from tests.test_materials import requires_db

client = TestClient(app)

_LIB = [
    {"eps_dot_per_s": 0.0, "points": [[0.0, 235.0], [0.2, 320.0]]},
    {"eps_dot_per_s": 100.0, "points": [[0.0, 260.0], [0.2, 350.0]]},
]


def _deck(tmp_path, model, mats_curves):
    p = _two_part_params(tmp_path)
    p["materials"] = [{**m, "crash_curves": c} for m, c in zip(p["materials"], mats_curves)]
    p["model"] = model
    return OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")


def test_empty_request_curves_fall_back_to_material(tmp_path):
    s = _deck(tmp_path, {"law": "tabulated"}, [_LIB, _LIB[:1]])
    assert int(_card(s, "/MAT/LAW36/1")[3][:10]) == 2  # N_funct: malzemenin 2 eğrisi
    assert int(_card(s, "/MAT/LAW36/2")[3][:10]) == 1
    assert float(_card(s, "/FUNCT/102")[1][20:40]) == pytest.approx(0.26)  # 260 MPa → GPa


def test_request_curves_win_over_material(tmp_path):
    req = [{"eps_dot_per_s": 0.0, "points": [(0.0, 500.0), (1.0, 500.0)]}]
    s = _deck(tmp_path, {"law": "tabulated", "tab_curves": req}, [_LIB, _LIB])
    assert int(_card(s, "/MAT/LAW36/1")[3][:10]) == 1
    assert float(_card(s, "/FUNCT/101")[1][20:40]) == pytest.approx(0.5)


def test_no_curves_anywhere_is_solver_error(tmp_path):
    with pytest.raises(SolverError, match="akma eğrisi yok"):
        _deck(tmp_path, {"law": "tabulated"}, [_LIB, None])


def test_bad_library_curves_is_solver_error(tmp_path):
    bad = [_LIB[1], _LIB[0]]  # hız azalan
    with pytest.raises(SolverError, match="crash_curves geçersiz"):
        _deck(tmp_path, {"law": "tabulated"}, [bad, bad])


def _new_material(**extra) -> dict:
    r = client.post(
        "/materials",
        json={
            "name": f"T_c2_{uuid.uuid4().hex[:8]}",
            "density": 7850, "youngs_modulus": 210e9, "poisson_ratio": 0.3,
            "yield_strength": 235e6, "ultimate_strength": 360e6, **extra,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["material"]


@requires_db
def test_material_api_crash_curves_roundtrip():
    mat = _new_material(crash_curves=_LIB)
    assert mat["crash_curves"] == _LIB
    put = client.put(f"/materials/{mat['id']}/crash-curves", json={"curves": _LIB[:1]})
    assert put.status_code == 200 and put.json()["material"]["crash_curves"] == _LIB[:1]
    listed = next(m for m in client.get("/materials").json()["materials"] if m["id"] == mat["id"])
    assert listed["crash_curves"] == _LIB[:1]
    cleared = client.put(f"/materials/{mat['id']}/crash-curves", json={"curves": None})
    assert cleared.json()["material"]["crash_curves"] is None
    # hız azalan → 422; kütüphane malzemesi → 403
    assert client.put(f"/materials/{mat['id']}/crash-curves", json={"curves": [_LIB[1], _LIB[0]]}).status_code == 422
    lib = next(m for m in client.get("/materials").json()["materials"] if not m["is_editable"])
    assert client.put(f"/materials/{lib['id']}/crash-curves", json={"curves": _LIB}).status_code == 403
