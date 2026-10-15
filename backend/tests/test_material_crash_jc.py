"""1.24f — materials.crash_jc: Johnson–Cook seti (migration seed + API)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_materials import requires_db

client = TestClient(app)

JC = {"a_mpa": 265.0, "b_mpa": 426.0, "n": 0.34, "c": 0.015, "m": 1.0, "eps_dot0_per_s": 1.0,
      "t_melt_k": 775.0, "t_ref_k": 293.0, "d": [0.13, 0.13, -1.5, 0.011, 0.0],
      "source": "Johnson & Cook 1983, Table 1 (2024-T351)"}


def _lib() -> dict[str, dict]:
    return {m["name"]: m for m in client.get("/materials").json()["materials"]}


@requires_db
def test_seed_only_verified_7075_t6():
    lib = _lib()
    jc = lib["7075-T6"]["crash_jc"]
    assert (jc["a_mpa"], jc["b_mpa"], jc["n"], jc["c"], jc["m"]) == (546.0, 674.0, 0.72, 0.059, 1.56)
    assert jc["eps_dot0_per_s"] is None and jc["t_melt_k"] is None  # özette yok → boş
    assert "Brar" in jc["source"]
    # doğrulanan seti olmayan kütüphane malzemeleri boş
    for name in ("6061-T6", "S235", "S355"):
        if name in lib:
            assert lib[name]["crash_jc"] is None


@requires_db
def test_put_crash_jc_user_material_roundtrip_and_rules():
    r = client.post("/materials", json={
        "name": f"T_jc_{uuid.uuid4().hex[:8]}", "density": 2770, "youngs_modulus": 73e9,
        "poisson_ratio": 0.33, "yield_strength": 324e6, "ultimate_strength": 469e6,
    })
    assert r.status_code == 200, r.text
    mid = r.json()["material"]["id"]
    put = client.put(f"/materials/{mid}/crash-jc", json={"jc": JC})
    assert put.status_code == 200, put.text
    assert put.json()["material"]["crash_jc"] == JC
    assert _lib()[put.json()["material"]["name"]]["crash_jc"]["d"] == JC["d"]
    # kaynak zorunlu; T_m > T_r; D 5 değer
    assert client.put(f"/materials/{mid}/crash-jc", json={"jc": {**JC, "source": ""}}).status_code == 422
    assert client.put(f"/materials/{mid}/crash-jc", json={"jc": {k: v for k, v in JC.items() if k != "source"}}).status_code == 422
    assert client.put(f"/materials/{mid}/crash-jc", json={"jc": {**JC, "t_melt_k": 200.0}}).status_code == 422
    assert client.put(f"/materials/{mid}/crash-jc", json={"jc": {**JC, "d": [0.1, 0.2]}}).status_code == 422
    # null siler
    assert client.put(f"/materials/{mid}/crash-jc", json={"jc": None}).json()["material"]["crash_jc"] is None
    # kütüphane malzemesi değişmez
    lib_id = _lib()["7075-T6"]["id"]
    assert client.put(f"/materials/{lib_id}/crash-jc", json={"jc": JC}).status_code == 403
    assert client.put("/materials/99999999/crash-jc", json={"jc": JC}).status_code == 404


def test_schema_validation_without_db():
    from pydantic import ValidationError

    from app.api.materials import CrashJcSet

    assert CrashJcSet.model_validate(JC).m == 1.0
    with pytest.raises(ValidationError):
        CrashJcSet.model_validate({**JC, "a_mpa": float("nan")})
    with pytest.raises(ValidationError):
        CrashJcSet.model_validate({**JC, "n": 0.0})
