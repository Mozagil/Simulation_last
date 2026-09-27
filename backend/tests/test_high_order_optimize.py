"""gmsh HighOrder optimizasyonu anahtarı (TODO 8.4).

Eğri yüzeylerde (delik, fillet) 2. mertebe kenar-orta düğümler elemanı ters
çevirebiliyor (ccx `nonpositive jacobian`). Anahtar açık değilken gmsh'e
DOKUNULMAZ — varsayılan mesh birebir eskisi gibi kalmalı.
"""

from __future__ import annotations

import gmsh

from app.api.geometry import GenerateMeshRequest
from app.mesh.base import MeshParams
from app.mesh.gmsh_adapter import GmshMesherAdapter
from app.templates import get_template
from app.templates.base import build_template


def _mesh(tmp_path, monkeypatch, flag: bool) -> list[str]:
    calls: list[str] = []
    real = gmsh.model.mesh.optimize
    monkeypatch.setattr(gmsh.model.mesh, "optimize",
                        lambda method="", *a, **k: (calls.append(method), real(method, *a, **k))[1])
    t = get_template("cantilever_beam")
    built = build_template(t, t.parse_params({}), tmp_path / f"b{int(flag)}.step")
    ad = GmshMesherAdapter()
    ad.generate_mesh(ad.import_geometry(built.step_path),
                     MeshParams(element_size=25.0, dimension=3, element_scheme="tet",
                                high_order_optimize=flag))
    return calls


def test_kapaliyken_optimize_cagrilmaz(tmp_path, monkeypatch):
    assert "HighOrder" not in _mesh(tmp_path, monkeypatch, False)


def test_acikken_highorder_optimize_cagrilir(tmp_path, monkeypatch):
    assert "HighOrder" in _mesh(tmp_path, monkeypatch, True)


def test_istek_alani_varsayilan_kapali():
    assert GenerateMeshRequest(element_size=5.0, dimension=3).high_order_optimize is False
    assert GenerateMeshRequest(element_size=5.0, dimension=3, high_order_optimize=True).high_order_optimize
