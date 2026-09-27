"""Mesh grafı gerçekten mesh grafı mı (TODO 1.1).

NEDEN: `write_inputs(..., None)` yüzünden diskteki her `.train.npz`
dosyasında `connectivity.shape == (0, 0)` idi; graf koordinatlardan k-NN
(k=6) ile kuruluyordu. "MeshGraphNet" dediğimiz şey mesh grafı değil,
nokta bulutu komşuluğuydu — eleman bağlantısı `.inp` dosyasında zaten
vardı, sadece geçirilmiyordu.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.dataset.training_data import CONNECTIVITY_PAD, pad_connectivity, write_inputs
from app.ml.graph_data import ELEMENT_EDGES, edges_from_connectivity, load_graph
from app.solvers.calculix import _read_inp_elements

INP = """*HEADING
CAE platform CalculiX job
*NODE
1, 0., 0., 0.
2, 1., 0., 0.
3, 0., 1., 0.
4, 0., 0., 1.
*ELEMENT, TYPE=C3D4, ELSET=PART_0
1, 1, 2, 3, 4
*ELEMENT, TYPE=C3D8, ELSET=PART_1
2, 1, 2, 3, 4, 5, 6, 7, 8
*ELSET, ELSET=FACE_EL_1
1,
*NODE FILE
U
"""


def _edge_set(edges):
    return {tuple(int(v) for v in e) for e in edges}


# --- .inp'ten okuma -----------------------------------------------------------


def test_inp_elemanlari_tip_ve_baglantiyla_okunur(tmp_path):
    p = tmp_path / "run1.inp"
    p.write_text(INP, encoding="utf-8")

    conn, types = _read_inp_elements(p)

    assert types == ["C3D4", "C3D8"]
    assert conn == [[1, 2, 3, 4], [1, 2, 3, 4, 5, 6, 7, 8]]


def test_elset_ve_node_file_bloklari_eleman_sanilmaz(tmp_path):
    """`*ELSET` satırları da sayı içeriyor — tip sıfırlanmazsa eleman sanılır."""
    p = tmp_path / "run1.inp"
    p.write_text(INP, encoding="utf-8")
    conn, _ = _read_inp_elements(p)
    assert len(conn) == 2, "ELSET satırı eleman olarak eklenmemeli"


def test_dosya_yoksa_bos_doner(tmp_path):
    assert _read_inp_elements(tmp_path / "yok.inp") == ([], [])


def test_devam_satiri_birlestirilir(tmp_path):
    """Abaqus/CCX uzun elemanı virgülle bölebilir."""
    p = tmp_path / "c.inp"
    p.write_text(
        "*ELEMENT, TYPE=C3D10, ELSET=P\n1, 1, 2, 3, 4, 5,\n6, 7, 8, 9, 10\n",
        encoding="utf-8",
    )
    conn, types = _read_inp_elements(p)
    assert types == ["C3D10"]
    assert conn == [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]


# --- dikdörtgen diziye çevirme ------------------------------------------------


def test_karisik_tipler_dolgu_ile_saklanir():
    out = pad_connectivity([[1, 2, 3, 4], [1, 2, 3, 4, 5, 6, 7, 8]])
    assert out.shape == (2, 8)
    assert list(out[0]) == [1, 2, 3, 4] + [CONNECTIVITY_PAD] * 4
    assert out.dtype == np.int32


def test_bos_baglanti_sifir_satir():
    assert pad_connectivity([]).shape == (0, 0)
    assert pad_connectivity(None).shape == (0, 0)


# --- kenar üretimi ------------------------------------------------------------


def test_tet10_klik_degil_gercek_kenarlar():
    """Asıl düzeltme: C3D10 klik 45 kenar verir, mesh'te 12 kenar var."""
    conn = np.arange(1, 11, dtype=np.int32).reshape(1, 10)

    mesh = edges_from_connectivity(conn, 10, ["C3D10"])
    clique = edges_from_connectivity(conn, 10, None)

    assert mesh.shape[0] == 12
    assert clique.shape[0] == 45, "tipsiz eski dosyalarda eski davranış korunur"
    # Köşe 0 ile köşe 1 DOĞRUDAN komşu değildir: aralarında 4 no'lu orta düğüm var
    assert (0, 1) not in _edge_set(mesh)
    assert {(0, 4), (1, 4)} <= _edge_set(mesh)


def test_tet10_orta_dugum_derecesi_iki():
    conn = np.arange(1, 11, dtype=np.int32).reshape(1, 10)
    edges = edges_from_connectivity(conn, 10, ["C3D10"])
    deg = np.bincount(edges.reshape(-1), minlength=10)
    assert list(deg[4:]) == [2] * 6, "kenar-ortası düğüm yalnız iki köşeye bağlı"
    assert list(deg[:4]) == [3] * 4, "köşe yalnız 3 orta düğüme bağlı (köşe-köşe yok)"


def test_hex8_on_iki_kenar():
    conn = np.arange(1, 9, dtype=np.int32).reshape(1, 8)
    assert edges_from_connectivity(conn, 8, ["C3D8"]).shape[0] == 12


def test_kabuk_elemanlari():
    assert edges_from_connectivity(np.array([[1, 2, 3]]), 3, ["S3"]).shape[0] == 3
    assert edges_from_connectivity(np.array([[1, 2, 3, 4]]), 4, ["S4"]).shape[0] == 4


def test_komsu_elemanlar_kenari_paylasir():
    """Benzersizlik: ortak kenar iki kez sayılmaz."""
    conn = np.array([[1, 2, 3], [2, 3, 4]], dtype=np.int32)
    edges = edges_from_connectivity(conn, 4, ["S3", "S3"])
    assert edges.shape[0] == 5  # 3 + 3 − 1 paylaşılan
    assert (1, 2) in _edge_set(edges)


def test_karisik_tip_dolgu_atilir():
    conn = pad_connectivity([[1, 2, 3, 4], [1, 2, 3, 4, 5, 6, 7, 8]])
    edges = edges_from_connectivity(conn, 8, ["C3D4", "C3D8"])
    assert (-1, 0) not in _edge_set(edges)
    assert edges.min() >= 0
    assert edges.shape[0] == len(
        {tuple(sorted(e)) for e in ELEMENT_EDGES["C3D4"]}
        | {tuple(sorted(e)) for e in ELEMENT_EDGES["C3D8"]}
    )


def test_bilinmeyen_tip_klige_duser():
    conn = np.array([[1, 2, 3, 4]], dtype=np.int32)
    assert edges_from_connectivity(conn, 4, ["C3D6"]).shape[0] == 6


def test_sifir_tabanli_baglanti_da_calisir():
    """0-based dizi (n_nodes'u aşmayan 1-based sayılmaz) bozulmamalı."""
    conn = np.array([[0, 1, 2]], dtype=np.int32)
    assert _edge_set(edges_from_connectivity(conn, 3, ["S3"])) == {(0, 1), (0, 2), (1, 2)}


def test_bos_girdiler():
    assert edges_from_connectivity(None, 5).shape == (0, 2)
    assert edges_from_connectivity(np.zeros((0, 0), np.int32), 5).shape == (0, 2)


# --- uçtan uca: yazılan dosya mesh grafı veriyor mu ---------------------------


def _write_sample(tmp_path, conn, types):
    X = np.zeros((4, 14), dtype=np.float32)
    X[:, :3] = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
    p = tmp_path / "s.train.npz"
    write_inputs(p, X, conn, element_types=types)
    with np.load(p, allow_pickle=False) as z:
        data = {k: z[k] for k in z.files}
    np.savez_compressed(
        p, **data, node_outputs=np.zeros((4, 4), np.float32),
        analysis_type=np.array("static"),
    )
    return p


def test_yazilan_dosyadan_mesh_grafi_gelir(tmp_path):
    p = _write_sample(tmp_path, pad_connectivity([[1, 2, 3, 4]]), ["C3D4"])
    g = load_graph(p, run_id=1)
    assert g is not None
    assert g.edge_source == "mesh"
    assert g.edges.shape[0] == 6


def test_baglanti_yoksa_knn_isaretlenir(tmp_path):
    """Eski dosyalar k-NN'e düşer ama bu AÇIKÇA işaretlenir."""
    p = _write_sample(tmp_path, None, None)
    g = load_graph(p, run_id=1)
    assert g is not None
    assert g.edge_source == "knn"
    assert g.edges.shape[0] > 0


@pytest.mark.parametrize("etype,n_edges", [("C3D4", 6), ("C3D8", 12), ("C3D10", 12)])
def test_tablo_kenarlari_benzersiz(etype, n_edges):
    table = ELEMENT_EDGES[etype]
    assert len({tuple(sorted(e)) for e in table}) == n_edges
