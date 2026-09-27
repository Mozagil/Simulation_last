"""NLGEOM DOE (TODO 4 — veri seti): spec alanları, u/L alt sınırı, runner.

Tanım: `docs/doe/nlgeom_kiris_v1.json` (kiriş, 6061-T6, 150 örnek,
lineer u/L 0.10–0.33 ⇔ α = FL²/EI 0.3–1.0).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app.doe.runner as runner
from app.doe.sampling import BcScenario, DoeSample, DoeSpec, sample_spec
from app.doe.screening import screen_sample

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "doe" / "nlgeom_kiris_v1.json"
AL = {4: {"youngs_modulus": 68.9e9, "yield_strength": 276e6}}
BEAM = {"length": 1000.0, "thickness": 6.4, "width": 40.0}


def _spec(**kw) -> DoeSpec:
    base = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    return DoeSpec.model_validate(base | kw)


def test_alt_sinir_kucuk_sehimi_eler():
    # α ≈ 0.1 → lineer u/L ≈ 0.033: NLGEOM bandının dışında
    res = screen_sample("cantilever_beam", BEAM, force_n=6.0, youngs_modulus_pa=68.9e9,
                        yield_strength_pa=276e6, max_u_over_l=0.34, min_u_over_l=0.10)
    assert not res.ok and "küçük deformasyon" in res.reason
    # α = 1 → u/L = 0.333: bantta
    ok = screen_sample("cantilever_beam", BEAM, force_n=60.2, youngs_modulus_pa=68.9e9,
                       yield_strength_pa=276e6, max_u_over_l=0.34, min_u_over_l=0.10)
    assert ok.ok


def test_alt_sinir_varsayilanda_kapali():
    """Lineer DOE'ler değişmez: min verilmezse küçük sehim elenmez."""
    res = screen_sample("cantilever_beam", BEAM, force_n=6.0, youngs_modulus_pa=68.9e9,
                        yield_strength_pa=276e6)
    assert res.ok


def test_alt_sinir_ust_sinirdan_kucuk_olmali():
    with pytest.raises(ValidationError, match="screen_min_u_over_l"):
        _spec(screen_min_u_over_l=0.4)


def test_tanim_dosyasi_150_ornegin_hepsini_bantta_uretir():
    spec = _spec()
    assert spec.nlgeom is True and spec.n_increments == 20
    samples = sample_spec(spec, AL)
    assert len(samples) == 150
    for s in samples:
        g = s.geometry_params
        force = abs(s.scenario.bcs[1]["fy"])
        inertia = g["width"] * g["thickness"] ** 3 / 12
        alpha = force * g["length"] ** 2 / (68.9e3 * inertia)
        assert 0.3 - 1e-9 <= alpha <= 1.02
        assert force * g["length"] * g["thickness"] / 2 / inertia <= 0.8 * 276 + 1e-6
        # Korpus yakınsama kapısı (max_mesh_ratio = 1.0) geçilsin.
        assert s.element_size / g["thickness"] <= 1.0 + 1e-9


def test_runner_nlgeom_u_cozucuye_iletir(monkeypatch):
    seen = {}
    monkeypatch.setattr(runner, "create_geometry_from_template",
                        lambda db, tpl, params: (SimpleNamespace(id=7), {}, None))
    monkeypatch.setattr(runner, "generate_mesh", lambda *a, **k: None)
    monkeypatch.setattr(runner, "groups_by_name", lambda db, gid: {})
    monkeypatch.setattr(runner, "bind_scenario_bcs", lambda groups, bcs: [
        {"type": "fixed", "face_ids": [1]},
        {"type": "cload", "face_ids": [2], "fx": 0.0, "fy": -50.0, "fz": 0.0},
    ])

    def fake_solve(gid, body, bg, db):
        seen["nlgeom"], seen["n_increments"] = body.nlgeom, body.n_increments
        return {"run_id": None, "status": "solved"}

    monkeypatch.setattr(runner, "solve_geometry", fake_solve)
    db = SimpleNamespace(get=lambda *a: SimpleNamespace(), add=lambda *a: None,
                         commit=lambda: None)
    spec = _spec(n_increments=35)
    sample = DoeSample(index=0, geometry_params=BEAM, element_size=6.0, material_id=4,
                       scenario=BcScenario(**spec.bc_scenarios[0].model_dump()))
    case = SimpleNamespace(geometry_id=None, bound_bcs=None, run_id=None,
                           study_id=1, index=0, status=None, message=None)
    runner._execute_sample(db, spec, sample, case)
    assert seen == {"nlgeom": True, "n_increments": 35}
    assert case.status == "solved"
