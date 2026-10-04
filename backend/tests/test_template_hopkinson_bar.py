"""K9 — Hopkinson şablonu: iki solid silindir, parça sırası, bölgeler."""

from __future__ import annotations

import math

import gmsh
import pytest

from app.templates import build_template, get_template


def test_two_cylinders_volumes_and_regions(tmp_path):
    t = get_template("hopkinson_bar")
    p = t.parse_params({"diameter": 10.0, "striker_length": 50.0, "bar_length": 200.0, "gap": 1.0})
    r = build_template(t, p, tmp_path / "h.step")
    assert all(len(v) == 1 for v in r.regions.values())
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(r.step_path))
        vols = gmsh.model.getEntities(3)
        assert len(vols) == 2
        masses = [gmsh.model.occ.getMass(3, v[1]) for v in vols]
        a = math.pi * 25.0
        assert masses == pytest.approx([a * 200.0, a * 50.0], rel=1e-6)  # ilk hacim giriş çubuğu (parça 0)
    finally:
        gmsh.finalize()
