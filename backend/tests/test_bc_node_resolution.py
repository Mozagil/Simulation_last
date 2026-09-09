"""CAD vertex (`node_ids`) ile mesh düğümü (`mesh_node_ids`) ayrımı testleri.

Arka plan (gerçek bug): frontend Nokta modunda CAD VERTEX id gönderiyordu,
backend ise bunu doğrudan MESH DÜĞÜM numarası olarak `.inp`'e yazıyordu.
Yani CAD köşe #7 seçilince alakasız mesh düğümü #7 sabitleniyordu. Aynı
dosyadaki `rigid_body` bunu zaten `POINT_{id}` nset'i üzerinden DOĞRU
çözüyordu — kod kendi içinde tutarsızdı.
"""

import pytest

from app.solvers.calculix import _bcs_inp_block, _resolve_bc_node_ids


def test_node_ids_are_resolved_through_point_nset():
    """KRİTİK: `node_ids` CAD vertex id'sidir, POINT_ nset'i üzerinden
    gerçek mesh düğümlerine çevrilmelidir — ham id olarak yazılmamalı."""
    nsets = {"POINT_7": [412, 413], "POINT_9": [88]}
    out = _resolve_bc_node_ids({"node_ids": [7, 9]}, nsets)
    assert out == [412, 413, 88]
    # Ham id'ler ASLA doğrudan geçmemeli
    assert 7 not in out
    assert 9 not in out


def test_mesh_node_ids_pass_through_unchanged():
    """`mesh_node_ids` zaten mesh düğüm numarasıdır — çevrilmemeli."""
    nsets = {"POINT_7": [412]}
    out = _resolve_bc_node_ids({"mesh_node_ids": [1001, 1002]}, nsets)
    assert out == [1001, 1002]


def test_both_sources_combine_and_deduplicate():
    nsets = {"POINT_1": [50, 51]}
    out = _resolve_bc_node_ids(
        {"node_ids": [1], "mesh_node_ids": [51, 99]}, nsets
    )
    # 51 iki kaynaktan da geliyor — bir kez görünmeli, sıra korunmalı
    assert out == [50, 51, 99]


def test_unknown_cad_vertex_falls_back_to_raw_id():
    """Mesh o vertex'e düğüm düşürmediyse eski davranışa (ham id) düşülür —
    geriye dönük uyum, ama yalnız son çare."""
    out = _resolve_bc_node_ids({"node_ids": [42]}, {})
    assert out == [42]


def test_fixed_bc_writes_resolved_mesh_nodes():
    nsets = {"POINT_7": [412, 413]}
    model_text, _step_text = _bcs_inp_block(
        [{"type": "fixed", "node_ids": [7]}], nsets, {}, dimension=3
    )
    assert "412, 1, 3" in model_text
    assert "413, 1, 3" in model_text
    assert "7, 1, 3" not in model_text


def test_cload_on_nodes_splits_total_force_across_nodes():
    """KRİTİK: toplam kuvvet seçili düğümlere EŞİT bölünmeli. Eskiden her
    düğüme TAM kuvvet yazılıyordu — 2 düğüm seçince model 2F yük görüyordu.
    """
    nsets = {"POINT_7": [412, 413]}
    _model_text, step_text = _bcs_inp_block(
        [{"type": "cload", "node_ids": [7], "fy": -500.0}],
        nsets,
        {},
        dimension=3,
    )
    # 500N iki düğüme bölünür -> her birine -250
    assert "412, 2, -250" in step_text
    assert "413, 2, -250" in step_text
    assert "-500" not in step_text


def test_displacement_bc_resolves_cad_vertex():
    nsets = {"POINT_3": [77]}
    model_text, _ = _bcs_inp_block(
        [{"type": "displacement", "node_ids": [3], "dofs": {"2": 0.0}}],
        nsets,
        {},
        dimension=3,
    )
    assert "77, 2, 2, 0" in model_text
