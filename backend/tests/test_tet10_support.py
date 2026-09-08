"""2. mertebe tetrahedron (tet10 / C3D10) desteği regresyon testleri.

Arka plan: 1. mertebe tet (C3D4, sabit gerinimli eleman) eğilmede aşırı
rijittir. 50x10x500 ankastre kiriş doğrulamasında (500N uç yükü, S235):

    el hesabı  : 23.81 mm sapma / 300.0 MPa
    ANSYS      : 24.74 mm sapma / 288.8 MPa  (SOLID187 = tet10)
    tet4 (eski): 9.70 mm sapma / ortalama 23.2 MPa  → 2.45 kat fazla rijit

Bu yüzden 3D tet mesh artık 2. mertebe üretiliyor.
"""

from pathlib import Path

import pytest

from app.mesh.base import MeshParams
from app.mesh.gmsh_adapter import GmshMesherAdapter
from app.solvers.calculix import CalculiXAdapter, _reorder_connectivity

FIXTURES = Path(__file__).parent / "fixtures"
BOX = FIXTURES / "box.step"


def test_tet10_connectivity_reorder_swaps_last_two_midside_nodes():
    """KRİTİK: Gmsh tet10 ile CalculiX C3D10 kenar-ortası düğüm sıralaması
    son iki düğümde farklıdır (Gmsh 8=orta(2,3), 9=orta(1,3); CalculiX
    8=orta(1,3), 9=orta(2,3)). Yeniden sıralanmazsa eleman jakobyeni bozulur.
    """
    conn = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    out = _reorder_connectivity(conn, 11)
    # İlk 8 aynı kalmalı
    assert out[:8] == [10, 11, 12, 13, 14, 15, 16, 17]
    # Son ikisi yer değiştirmeli
    assert out[8] == 19
    assert out[9] == 18


def test_reorder_connectivity_leaves_other_element_types_untouched():
    """tet4 / hex8 / tri3 / quad4 iki formatta da aynı sırada — dokunulmamalı."""
    tet4 = [1, 2, 3, 4]
    assert _reorder_connectivity(tet4, 4) == tet4
    hex8 = [1, 2, 3, 4, 5, 6, 7, 8]
    assert _reorder_connectivity(hex8, 5) == hex8
    tri3 = [1, 2, 3]
    assert _reorder_connectivity(tri3, 2) == tri3


def test_generate_mesh_3d_tet_produces_second_order_elements(tmp_path):
    """3D tet mesh artık tet10 üretmeli (ANSYS SOLID187 ile aynı mertebe)."""
    step = tmp_path / "box_tet10.step"
    step.write_bytes(BOX.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(step)
    result = adapter.generate_mesh(
        geom, MeshParams(element_size=8.0, dimension=3, element_scheme="tet")
    )

    assert "Tetrahedron10" in result.element_type_counts
    assert result.element_type_counts["Tetrahedron10"] > 0
    assert result.element_count > 0
    # Preview hâlâ üretilebilmeli (tet10'da eleman başına 10 düğüm gelir,
    # yüzey üçgenleri için yalnız ilk 4 köşe kullanılır).
    assert result.preview_path is not None
    assert result.preview_path.exists()

    import json

    preview = json.loads(result.preview_path.read_text(encoding="utf-8"))
    assert len(preview["nodes"]) == result.node_count
    assert len(preview["faces"]) >= 9
    assert len(preview["faces"]) % 3 == 0
    # Yüzey üçgenlerinin indeksleri node dizisinin sınırları içinde olmalı
    assert max(preview["faces"]) < len(preview["nodes"])


def test_build_input_writes_c3d10_element_cards(tmp_path):
    """Üretilen .inp'te C3D10 kartı ve eleman başına 10 düğüm bulunmalı."""
    step = tmp_path / "box_c3d10.step"
    step.write_bytes(BOX.read_bytes())

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(step)
    mesh = adapter.generate_mesh(
        geom, MeshParams(element_size=8.0, dimension=3, element_scheme="tet")
    )

    ccx = CalculiXAdapter()
    artifact = ccx.build_input(
        {
            "mesh_path": mesh.mesh_path,
            "dimension": 3,
            "output_dir": tmp_path / "run",
            "job_name": "tet10job",
            "materials": [
                {
                    "part_id": 0,
                    "name": "S235",
                    "youngs_modulus": 210e9,
                    "poisson_ratio": 0.3,
                    "density": 7850.0,
                }
            ],
            "bcs": [{"type": "fixed", "face_ids": [1]}],
        }
    )
    text = artifact.path.read_text(encoding="utf-8")
    assert "TYPE=C3D10" in text
    assert "TYPE=C3D4" not in text

    # C3D10 veri satırı: eleman id + 10 düğüm = 11 alan
    lines = text.splitlines()
    idx = next(i for i, ln in enumerate(lines) if "TYPE=C3D10" in ln)
    first_elem_line = lines[idx + 1]
    assert len(first_elem_line.split(",")) == 11
