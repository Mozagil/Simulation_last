"""Mesh önizlemesinde 2. mertebe (kenar-ortası) düğümlerin işaretlenmesi.

tet10'da Gmsh sıralaması gereği elemanın İLK 4 düğümü köşe, kalan 6'sı
kenar ortasıdır. Arayüz köşe düğümleri ile ara düğümleri ayırt edip ara
düğümleri gizleyebilsin diye önizleme bunları taşır — köşeler geometrinin
gerçek noktalarıdır, ara düğümler yalnız eleman mertebesinin sonucudur.
"""

import json
from pathlib import Path

from app.mesh.base import MeshParams
from app.mesh.gmsh_adapter import GmshMesherAdapter

FIXTURES = Path(__file__).parent / "fixtures"
BOX = FIXTURES / "box.step"


def _preview(tmp_path, dimension: int, scheme: str = "tet"):
    step = tmp_path / f"midside_{dimension}.step"
    step.write_bytes(BOX.read_bytes())
    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(step)
    result = adapter.generate_mesh(
        geom,
        MeshParams(element_size=8.0, dimension=dimension, element_scheme=scheme),
    )
    assert result.preview_path is not None
    return result, json.loads(result.preview_path.read_text(encoding="utf-8"))


def test_3d_tet10_preview_marks_midside_nodes(tmp_path):
    result, preview = _preview(tmp_path, 3)
    idx = preview.get("midside_node_indices")
    assert idx, "tet10 mesh'te ara düğüm listesi boş olmamalı"
    # Ara düğümler toplamın kayda değer bir kısmıdır (tet10'da çoğunluk).
    assert len(idx) < result.node_count
    assert len(idx) > result.node_count * 0.3


def test_midside_indices_are_within_node_array_bounds(tmp_path):
    _result, preview = _preview(tmp_path, 3)
    n = len(preview["nodes"])
    for i in preview["midside_node_indices"]:
        assert 0 <= i < n


def test_midside_indices_are_sorted_and_unique(tmp_path):
    _result, preview = _preview(tmp_path, 3)
    idx = preview["midside_node_indices"]
    assert idx == sorted(idx)
    assert len(idx) == len(set(idx))


def test_midside_nodes_never_appear_as_surface_triangle_corners(tmp_path):
    """Ara düğüm ile köşe düğüm kümeleri AYRIK olmalı.

    Bu, işaretlemenin doğruluğunun asıl kanıtı: yüzey üçgenleri yalnız
    köşe düğümlerinden kurulur (önizleme tet10'da elemanın ilk 4 düğümünü
    kullanır). Bir düğüm hem üçgen köşesi hem "ara düğüm" olarak
    işaretlenmişse indeks eşlemesi kaymış demektir.

    Not: 2D kabukta da ara düğüm olmaz, ama o yol önce midsurface
    gerektirdiği için burada test edilmiyor (bkz. generate_mesh'in
    "2D shell mesh için midsurface gerekli" kontrolü).
    """
    _result, preview = _preview(tmp_path, 3)
    corner_idx = set(preview["faces"])
    midside_idx = set(preview["midside_node_indices"])
    assert corner_idx, "yüzey üçgeni yok"
    assert midside_idx, "ara düğüm yok"
    assert corner_idx.isdisjoint(midside_idx)
