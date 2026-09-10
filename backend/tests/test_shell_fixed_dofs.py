"""Kabuk (2D) elemanlarda ankastre mesnedin dönme DOF'larını da kısıtlaması.

Gerçek bug: `_bcs_inp_block` `dimension` parametresini alıyor ama
`_ = dimension` ile atıyordu; "fixed" her durumda `1, 3` yazıyordu.

CalculiX'te:
  * 3D solid (C3D4/C3D10/C3D8) düğümünde 3 DOF vardır → 1..3 doğru.
  * 2D kabuk (S3/S4) düğümünde 6 DOF vardır — 1..3 öteleme, 4..6 DÖNME.
    Yalnız 1..3 kısıtlanırsa, kısıt bir doğru üzerindeyken (plakanın
    ankastre kenarı) kabuk o kenar etrafında serbestçe döner: rijit cisim
    hareketi.

Doğrulama: 50x10x500 midsurface kabukta kenar düğümlerine fixed + 500N
uygulanınca maksimum deplasman 4.42e10 mm çıkıyordu; aynı problem 3D
solid'de 23.9 mm (el hesabı 23.81, ANSYS 24.74).
"""

from app.solvers.calculix import _bcs_inp_block


def test_fixed_on_shell_constrains_rotational_dofs():
    """KRİTİK: 2D kabukta ankastre mesnet 1..6 kısıtlamalı."""
    nsets = {"EDGE_1": [1, 2, 3]}
    model_text, _step = _bcs_inp_block(
        [{"type": "fixed", "edge_ids": [1]}], nsets, {}, dimension=2
    )
    assert "EDGE_1, 1, 6" in model_text
    assert "EDGE_1, 1, 3" not in model_text


def test_fixed_on_solid_keeps_translation_only_dofs():
    """3D solid düğümünde dönme DOF'u YOKTUR — 1..6 yazmak CalculiX'te
    tanımsız DOF hatası verir. 1..3 korunmalı."""
    nsets = {"FACE_1": [1, 2, 3]}
    model_text, _step = _bcs_inp_block(
        [{"type": "fixed", "face_ids": [1]}], nsets, {}, dimension=3
    )
    assert "FACE_1, 1, 3" in model_text
    assert "FACE_1, 1, 6" not in model_text


def test_fixed_on_shell_node_selection_also_constrains_rotations():
    """Düğüm bazlı seçimde de aynı kural geçerli — kullanıcı mesh üzerinde
    düğüm seçip fixed verdiğinde kabukta dönmeler serbest kalmamalı."""
    model_text, _step = _bcs_inp_block(
        [{"type": "fixed", "mesh_node_ids": [7, 8]}], {}, {}, dimension=2
    )
    assert "7, 1, 6" in model_text
    assert "8, 1, 6" in model_text


def test_fixed_on_shell_cad_vertex_resolves_and_constrains_rotations():
    nsets = {"POINT_4": [55]}
    model_text, _step = _bcs_inp_block(
        [{"type": "fixed", "node_ids": [4]}], nsets, {}, dimension=2
    )
    assert "55, 1, 6" in model_text
