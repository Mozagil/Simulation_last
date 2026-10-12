"""1.21e-2a — içe aktarılan mesh'in önizleme yüzeyi."""

from app.importers.dyna_preview import surface_preview


def _grid_nodes(nx: int) -> list[tuple[int, float, float, float]]:
    """x yönünde nx + 1 kesit; her kesitte 4 düğüm (birim kare)."""
    out = []
    for i in range(nx + 1):
        for j, (y, z) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
            out.append((4 * i + j + 1, float(i), float(y), float(z)))
    return out


def _hex(eid: int, i: int) -> tuple[int, ...]:
    a = [4 * i + k + 1 for k in range(4)]
    b = [4 * (i + 1) + k + 1 for k in range(4)]
    # LS-DYNA sırası: n1–n4 bir yüz, n5–n8 karşısı
    return (eid, *a, *b)


def test_two_bricks_hide_shared_face() -> None:
    params = {
        "nodes": _grid_nodes(2),
        "bricks": [_hex(1, 0), _hex(2, 1)],
        "element_parts": {"1": 0, "2": 1},  # JSON'dan gelmiş gibi str anahtar
    }
    p = surface_preview(params)
    assert len(p["faces"]) == 10  # 2 × 6 − ortak yüzün iki kopyası
    assert p["part_faces"] == {"1": 5, "2": 5}
    assert len(p["nodes"]) == 12
    assert p["bbox_mm"] == {"min": [0.0, 0.0, 0.0], "max": [2.0, 1.0, 1.0]}


def test_shells_tets_and_degenerate_brick() -> None:
    nodes = [(1, 0.0, 0.0, 0.0), (2, 1.0, 0.0, 0.0), (3, 1.0, 1.0, 0.0), (4, 0.0, 1.0, 0.0),
             (5, 0.0, 0.0, 1.0), (6, 0.0, 1.0, 1.0), (9, 5.0, 5.0, 5.0)]
    params = {
        "nodes": nodes,
        "shells": [(10, 1, 2, 3, 4)],
        "sh3n": [(11, 1, 2, 3)],
        "tets": [(20, 1, 4, 6, 5)],  # hex ile ortak yüzü yok
        # Dejenere hex (tet biçimli): n4 = n3, n5–n8 tek düğüm
        "bricks": [(30, 1, 2, 3, 3, 5, 5, 5, 5)],
        "element_parts": {10: 0, 11: 0, 20: 2, 30: 3},
    }
    p = surface_preview(params)
    assert p["part_faces"]["1"] == 2
    assert p["part_faces"]["3"] == 4
    assert p["part_faces"]["4"] == 4  # üst yüz noktaya, bir yan yüz çizgiye iner
    assert all(len(f) in (3, 4) for f in p["faces"])
    assert all(len(set(f)) == len(f) for f in p["faces"])
    assert [5.0, 5.0, 5.0] not in p["nodes"]  # kullanılmayan düğüm gönderilmez
