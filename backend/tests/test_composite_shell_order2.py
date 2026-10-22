"""Kompozit için 2. mertebe kabuk ağı: gmsh quad8/tri6 → ccx S8R/S6, tutarlı kenar yükü.

Delikli plaka (200×100, Ø40) uygulamanın ağ adaptöründen geçer; ccx varsa
`*SHELL SECTION, COMPOSITE` ile uçtan uca çözülür (önceden S4 ile ccx
"COMPOSITE yalnız S8R/S6" hatasıyla duruyordu).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

gmsh = pytest.importorskip("gmsh")

from app.composite.assemble import assemble_composite_layup  # noqa: E402
from app.mesh.base import MeshParams  # noqa: E402
from app.mesh.gmsh_adapter import GmshMesherAdapter  # noqa: E402
from app.solvers.calculix import CalculiXAdapter, _ccx_executable  # noqa: E402

_T300 = {
    "name": "T300/epoxy",
    "e1": 135e9, "e2": 10e9, "e3": 10e9, "nu12": 0.3, "nu13": 0.3, "nu23": 0.45,
    "g12": 5.2e9, "g13": 5.2e9, "g23": 3.4e9, "density": 1600.0,
    "xt": 1500e6, "xc": 1200e6, "yt": 50e6, "yc": 200e6, "s12": 70e6, "s23": 40e6,
}
_ANGLES = (0, 45, -45, 90, 90, -45, 45, 0)
_FX = 5000.0


def _plate_step(path: Path) -> None:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("p")
        r = gmsh.model.occ.addRectangle(0, 0, 0, 200, 100)
        d = gmsh.model.occ.addDisk(100, 50, 0, 20, 20)
        gmsh.model.occ.cut([(2, r)], [(2, d)])
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _edges_at_x(msh: Path, x: float) -> list[int]:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(msh))
        out = []
        for _d, c in gmsh.model.getEntities(1):
            x0, _y0, _z0, x1, _y1, _z1 = gmsh.model.getBoundingBox(1, c)
            if abs(x0 - x) < 1e-6 and abs(x1 - x) < 1e-6:
                out.append(int(c))
        return out
    finally:
        gmsh.finalize()


@pytest.fixture(scope="module")
def plate_mesh(tmp_path_factory):
    d = tmp_path_factory.mktemp("o2")
    step = d / "plate.step"
    _plate_step(step)
    mesher = GmshMesherAdapter()
    geom = mesher.import_geometry(step)
    mesh = mesher.generate_mesh(geom, MeshParams(element_size=8.0, dimension=2, element_scheme="quad", shell_order=2))
    return d, mesh


def test_shell_order2_mesh_is_quad8(plate_mesh):
    _d, mesh = plate_mesh
    counts = mesh.element_type_counts
    assert counts.get("Quad8", 0) > 0 and "Quad" not in counts, counts
    assert mesh.element_count == counts["Quad8"] + counts.get("Triangle6", 0)
    assert mesh.preview_path is not None
    import json

    preview = json.loads(Path(mesh.preview_path).read_text(encoding="utf-8"))
    assert preview["midside_node_indices"]  # kenar ortaları işaretli


def _deck(plate_mesh, tmp_path):
    _d, mesh = plate_mesh
    spec = assemble_composite_layup(
        part_id=0,
        plies=[{"material_id": 1, "thickness_mm": 0.125, "angle_deg": a} for a in _ANGLES],
        materials={1: _T300},
    )
    left = _edges_at_x(mesh.mesh_path, 0.0)
    right = _edges_at_x(mesh.mesh_path, 200.0)
    art = CalculiXAdapter().build_input(
        {
            "mesh_path": mesh.mesh_path,
            "dimension": 2,
            "output_dir": tmp_path,
            "job_name": "o2",
            "materials": [],
            "shell_thickness": 1.0,
            "bcs": [{"type": "fixed", "edge_ids": left}, {"type": "cload", "edge_ids": right, "fx": _FX}],
            "analysis_type": "static",
            "composite_layup": spec,
        }
    )
    return art


def test_deck_s8r_and_consistent_edge_load(plate_mesh, tmp_path):
    art = _deck(plate_mesh, tmp_path)
    text = art.path.read_text(encoding="utf-8")
    assert "*ELEMENT, TYPE=S8R" in text and "TYPE=S4" not in text
    loads = [float(m) for m in re.findall(r"^\d+, 1, ([-\d.eE+]+)$", text.split("*CLOAD", 1)[1], re.M)]
    assert sum(loads) == pytest.approx(_FX, rel=1e-6)
    # Kuadratik kenar (düzgün ağ): uç düğüm ⅙, iç köşe ⅓, kenar ortası ⅔ (× eleman boyu)
    assert max(loads) / min(loads) == pytest.approx(4.0, rel=0.05)


@pytest.mark.skipif(_ccx_executable() is None, reason="ccx yok")
def test_composite_runs_end_to_end_on_app_mesh(plate_mesh, tmp_path):
    adapter = CalculiXAdapter()
    art = _deck(plate_mesh, tmp_path)
    job = adapter.submit(art)
    rs = adapter.parse_results(job)
    sc = rs.scalars
    assert sc["n_plies"] == 8
    # Delik kenarında 90° katman matris çekmesi en kritik (betik koşusunda 0.64 / 0.59)
    assert 0.3 < sc["tsai_wu_irf_max"] < 1.2
    assert int(sc["tsai_wu_ply"]) in (4, 5)
    assert int(sc["hashin_mode"]) == 2
    assert (tmp_path / "o2_ply.json").exists()
