"""Çözüm öncesi u/L ön kontrolü — arayüz NLGEOM sorusu için (karar kullanıcının)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.solve import SolveBC, SolveScreenBody, screen_solve
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.material import Material, MaterialAssignment


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _beam(db, L=1000.0, T=6.4, W=40.0, E=68.9e9):
    g = Geometry(original_filename="b.step", current_filename="b.step", template_id="cantilever_beam",
                 template_params={"length": L, "thickness": T, "width": W})
    db.add(g); db.flush()
    m = Material(name="Al", category="metal", youngs_modulus=E, poisson_ratio=0.33, density=2700.0, yield_strength=276e6, ultimate_strength=310e6)
    db.add(m); db.flush()
    db.add(MaterialAssignment(geometry_id=g.id, part_id=0, material_id=m.id)); db.commit()
    return g


def test_buyuk_sehim_bayragi_ve_esik(db):
    g = _beam(db)
    body = SolveScreenBody(bcs=[SolveBC(type="cload", fy=-60.2)])  # α = 1 → lineer u/L 0.333
    out = screen_solve(g.id, body, db)
    assert out["has_analytic"] and out["large_deformation"] is True
    assert out["u_over_l"] == pytest.approx(0.333, abs=0.002)
    assert out["threshold"] == 0.10

    small = screen_solve(g.id, SolveScreenBody(bcs=[SolveBC(type="cload", fy=-6.0)]), db)
    assert small["large_deformation"] is False and small["u_over_l"] < 0.05


def test_sablonsuz_geometri_soru_sormaz(db):
    g = Geometry(original_filename="x.step", current_filename="x.step")
    db.add(g); db.commit()
    out = screen_solve(g.id, SolveScreenBody(bcs=[SolveBC(type="cload", fy=-1e6)]), db)
    assert out["has_analytic"] is False and out["large_deformation"] is False
