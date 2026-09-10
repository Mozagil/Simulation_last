"""CalculiX kabuk genişletmesinin orta yüzeye geri katlanması.

CalculiX kabuk elemanlarını içeride 3B hacme genişletir: her kabuk düğümü
üst/alt yüzey için ikiye katlanır ve `.frd` bu genişletilmiş düğümleri
yazar. Düğüm sayısı mesh'in iki katı olunca arayüz hizalayamaz ve düzgün
yüzey konturu yerine kaba bir nokta bulutuna düşer.

`*NODE FILE, OUTPUT=2D` denendi ve GERİ ALINDI: hizalamayı çözüyordu ama
gerilmeyi kabuğun ORTA DÜZLEMİNDE veriyordu. Eğilmede gerilme kalınlık
boyunca lineerdir — yüzeyde ±sigma_max, orta düzlemde SIFIR. Gerçek bir
testte 300 MPa olması gereken kabuk gerilmesi 79.8 MPa'ya düştü.

Doğru çözüm: genişletilmiş çıktıyı koru, post-process'te katla.
von Mises için MAKSİMUM (yüzey gerilmesi), deplasman için ORTALAMA.
"""

from app.solvers.calculix import (
    _collapse_shell_expansion,
    _read_inp_nodes,
    _von_mises_stress,
)


def _shell_case():
    """t=10 kabuk: 2 orta yüzey düğümü, her biri ±5mm'de ikiye katlanmış."""
    mesh_nodes = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)]
    node_coords = {
        1: (0.0, -5.0, 0.0),
        2: (100.0, -5.0, 0.0),
        3: (0.0, 5.0, 0.0),
        4: (100.0, 5.0, 0.0),
    }
    displacement = {
        1: (0.0, -1.0, 0.0),
        2: (0.0, -20.0, 0.0),
        3: (0.0, -1.0, 0.0),
        4: (0.0, -20.0, 0.0),
    }
    # Alt yüzey çekme, üst yüzey basma — orta düzlemde net sıfır.
    stress = {
        1: (300.0, 0, 0, 0, 0, 0),
        2: (60.0, 0, 0, 0, 0, 0),
        3: (-300.0, 0, 0, 0, 0, 0),
        4: (-60.0, 0, 0, 0, 0, 0),
    }
    return mesh_nodes, node_coords, displacement, stress


def test_collapse_halves_node_count():
    mesh_nodes, nc, disp, st = _shell_case()
    out = _collapse_shell_expansion(nc, disp, st, mesh_nodes)
    assert out is not None
    order, nodes, _d, _s = out
    assert len(order) == len(mesh_nodes)
    assert nodes == [[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]]


def test_collapse_keeps_surface_stress_not_midplane_average():
    """KRİTİK: von Mises MAKSİMUM alınmalı. Ortalama alınsaydı üst/alt
    yüzeyin zıt işaretli eğilme gerilmeleri birbirini götürür ve sonuç
    sıfıra yakın çıkardı — OUTPUT=2D denemesindeki hata buydu."""
    mesh_nodes, nc, disp, st = _shell_case()
    order, _n, _d, stress_out = _collapse_shell_expansion(nc, disp, st, mesh_nodes)
    vms = [_von_mises_stress(*stress_out[nid]) for nid in order]
    assert abs(vms[0] - 300.0) < 1e-6
    assert abs(vms[1] - 60.0) < 1e-6


def test_collapse_averages_displacement():
    mesh_nodes, nc, disp, st = _shell_case()
    order, _n, disp_out, _s = _collapse_shell_expansion(nc, disp, st, mesh_nodes)
    assert abs(disp_out[order[0]][1] - (-1.0)) < 1e-6
    assert abs(disp_out[order[1]][1] - (-20.0)) < 1e-6


def test_collapse_returns_none_for_solid_without_expansion():
    """3D solid'de genişletme yoktur — fonksiyon dokunmadan çekilmeli."""
    assert _collapse_shell_expansion({1: (0.0, 0.0, 0.0)}, {}, {}, [(0.0, 0.0, 0.0)]) is None


def test_collapse_returns_none_on_empty_inputs():
    assert _collapse_shell_expansion({}, {}, {}, []) is None


def test_read_inp_nodes_parses_node_block(tmp_path):
    inp = tmp_path / "job.inp"
    inp.write_text(
        "*HEADING\ntest\n*NODE\n1, 0.0, 0.0, 0.0\n2, 10.0, 0.0, 0.0\n"
        "*ELEMENT, TYPE=S4, ELSET=PART_0\n1, 1, 2, 3, 4\n",
        encoding="utf-8",
    )
    nodes = _read_inp_nodes(inp)
    assert nodes == [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]


def test_read_inp_nodes_ignores_node_file_card(tmp_path):
    """`*NODE FILE` bir çıktı kartıdır, düğüm bloğu DEĞİLDİR — altındaki
    'U' satırı koordinat sanılmamalı."""
    inp = tmp_path / "job2.inp"
    inp.write_text(
        "*NODE\n1, 1.0, 2.0, 3.0\n*STEP\n*STATIC\n*NODE FILE\nU\n*END STEP\n",
        encoding="utf-8",
    )
    assert _read_inp_nodes(inp) == [(1.0, 2.0, 3.0)]
