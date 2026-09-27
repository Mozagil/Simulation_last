"""Ankastre kiriş kök filleti (TODO 6 — kalan).

Düz kutuda kökte geometrik köşe yok: tekillik BC kenarından geliyor.
Fillet ancak destek (duvar) modellenince konabiliyor. `root_fillet = 0`
iken geometri eskisiyle birebir aynı kalmalı — eski veri geçerli.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from app.ml.scalar_features import feature_values_from_run
from app.models.geometry import Geometry
from app.models.run import AnalysisRun
from app.templates import get_template
from app.templates.base import build_template
from app.templates.cantilever_beam import REGION_FIXED

T = get_template("cantilever_beam")


def _volume(step_path) -> float:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(step_path))
        return sum(gmsh.model.occ.getMass(3, tag) for _d, tag in gmsh.model.getEntities(3))
    finally:
        gmsh.finalize()


def _fixed_face_x(step_path, tag: int) -> tuple[float, float]:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(step_path))
        x0, _, _, x1, _, _ = gmsh.model.getBoundingBox(2, tag)
        return x0, x1
    finally:
        gmsh.finalize()


def test_fillet_sifirken_duvar_yok(tmp_path):
    r = build_template(T, T.parse_params({}), tmp_path / "b.step")
    assert r.bounding_box[0] == pytest.approx(0.0, abs=1e-6)
    assert _volume(r.step_path) == pytest.approx(500 * 10 * 50, rel=1e-6)


def test_fillet_malzeme_ekler_ve_ankastre_duvar_arkasina_tasinir(tmp_path):
    L, Tk, W, tw, m, r = 300.0, 10.0, 40.0, 15.0, 12.0, 4.0
    p = T.parse_params({"length": L, "thickness": Tk, "width": W,
                        "root_fillet": r, "wall_thickness": tw, "wall_margin": m})
    built = build_template(T, p, tmp_path / "f.step")

    (tag,) = built.regions[REGION_FIXED]
    assert _fixed_face_x(built.step_path, tag) == pytest.approx((-tw, -tw), abs=1e-6)

    sharp = L * Tk * W + tw * (Tk + 2 * m) * (W + 2 * m)
    added = _volume(built.step_path) - sharp
    # İç köşe filletinin kesiti r²(1 − π/4); çevre boyunca 2(T+W).
    # Kesit köşelerinde süpürme örtüşür → yaklaşık, %10 bant.
    expected = r**2 * (1 - math.pi / 4) * 2 * (Tk + W)
    assert added == pytest.approx(expected, rel=0.10)


def test_fillet_duvar_tasmasindan_kucuk_olmali():
    with pytest.raises(ValidationError, match="wall_margin"):
        T.parse_params({"root_fillet": 20.0, "wall_margin": 20.0})


def test_eski_run_yeni_alanlari_varsayilanla_alir():
    """Eski kayıtta alan yok → 0 değil şablon varsayılanı (aynı geometri, aynı vektör)."""
    geo = Geometry(template_id="cantilever_beam",
                   template_params={"length": 500.0, "thickness": 10.0, "width": 50.0})
    run = AnalysisRun(materials_snapshot=[{"youngs_modulus": 210e9, "poisson_ratio": 0.3}],
                      bcs=[], dimension=3, element_size=8.0)
    v = feature_values_from_run(run, geo)
    assert v["root_fillet"] == 0.0
    assert v["wall_thickness"] == 20.0
    assert v["wall_margin"] == 20.0
