"""Surrogate eğitim veri seti üretimi testleri.

Bkz. `app/dataset/training_data.py` — neden `.frd` yerine `.npz`, neden iki
aşamalı yazım, neden kayıpsız sıkıştırma.
"""

import gzip
from pathlib import Path

import numpy as np
import pytest

from app.dataset.training_data import (
    NODE_INPUT_CHANNELS,
    NODE_OUTPUT_CHANNELS,
    build_node_inputs,
    gzip_frd,
    normalize_mode_shape,
    write_inputs,
    write_modal_sample,
    write_training_sample,
)
from app.solvers.calculix import _resolve_bc_node_ids

COORDS = [(0.0, 0.0, 0.0), (0.0, 10.0, 0.0), (500.0, 0.0, 0.0), (500.0, 10.0, 0.0)]
MATERIALS = [
    {
        "part_id": 0,
        "name": "S235",
        "youngs_modulus": 210e9,
        "poisson_ratio": 0.3,
        "density": 7850.0,
    }
]
NSETS = {"FACE_1": [1, 2], "FACE_2": [3, 4]}


def _inputs(bcs, dimension=3, thickness=0.0):
    return build_node_inputs(
        COORDS, bcs, NSETS, MATERIALS, dimension, thickness, _resolve_bc_node_ids
    )


def _ch(name):
    return NODE_INPUT_CHANNELS.index(name)


def test_coordinates_are_written_per_node():
    X = _inputs([])
    assert X.shape == (4, len(NODE_INPUT_CHANNELS))
    assert X[2, _ch("x")] == pytest.approx(500.0)
    assert X[1, _ch("y")] == pytest.approx(10.0)


def test_fixed_bc_marks_only_targeted_nodes():
    X = _inputs([{"type": "fixed", "face_ids": [1]}])
    # FACE_1 -> düğüm 1,2 (index 0,1)
    assert X[0, _ch("fixed_ux")] == 1.0
    assert X[1, _ch("fixed_ux")] == 1.0
    assert X[2, _ch("fixed_ux")] == 0.0
    assert X[3, _ch("fixed_ux")] == 0.0


def test_shell_fixed_also_marks_rotational_dofs():
    """Kabukta ankastre mesnet dönmeleri de kısıtlar (1..6). Bu ayrım gerçek
    bir hatanın kaynağıydı; model için anlamlı bir girdi."""
    solid = _inputs([{"type": "fixed", "face_ids": [1]}], dimension=3)
    shell = _inputs([{"type": "fixed", "face_ids": [1]}], dimension=2, thickness=10.0)
    assert solid[0, _ch("fixed_rot")] == 0.0
    assert shell[0, _ch("fixed_rot")] == 1.0


def test_cload_is_split_across_target_nodes():
    """KRİTİK: `.inp` yazıcısı toplam kuvveti düğümlere böler; girdi
    matrisi de AYNI kuralı kullanmalı. Farklı olsaydı model, çözücünün
    gördüğünden başka bir yük görürdü."""
    X = _inputs([{"type": "cload", "face_ids": [2], "fy": -500.0}])
    # FACE_2 -> 2 düğüm, her birine -250
    assert X[2, _ch("load_fy")] == pytest.approx(-250.0)
    assert X[3, _ch("load_fy")] == pytest.approx(-250.0)
    # Toplam korunmalı
    assert X[:, _ch("load_fy")].sum() == pytest.approx(-500.0)


def test_material_is_converted_to_solver_units():
    """E: Pa -> MPa, yoğunluk: kg/m^3 -> tonne/mm^3. Çözücüye yazılanla
    aynı birimde olmalı."""
    X = _inputs([])
    assert X[0, _ch("youngs_modulus_mpa")] == pytest.approx(210000.0)
    assert X[0, _ch("density_tonne_mm3")] == pytest.approx(7.85e-9)


def test_shell_thickness_only_set_in_2d():
    solid = _inputs([], dimension=3, thickness=10.0)
    shell = _inputs([], dimension=2, thickness=10.0)
    assert solid[0, _ch("shell_thickness_mm")] == 0.0
    assert shell[0, _ch("shell_thickness_mm")] == pytest.approx(10.0)


def test_training_sample_roundtrip(tmp_path):
    X = _inputs([{"type": "fixed", "face_ids": [1]}, {"type": "cload", "face_ids": [2], "fy": -500.0}])
    ip = tmp_path / "job.inputs.npz"
    write_inputs(ip, X, None)

    out = tmp_path / "job.train.npz"
    info = write_training_sample(
        ip,
        out,
        node_order=[1, 2, 3, 4],
        disp_vectors=[[0, 0, 0], [0, 0, 0], [0, -23.9, 0], [0, -23.9, 0]],
        von_mises=[330.7, 330.7, 1.2, 1.2],
    )
    assert info is not None and info["nodes"] == 4

    with np.load(out, allow_pickle=False) as z:
        assert z["node_inputs"].shape == (4, len(NODE_INPUT_CHANNELS))
        assert z["node_outputs"].shape == (4, len(NODE_OUTPUT_CHANNELS))
        assert z["node_outputs"][2, 1] == pytest.approx(-23.9)
        assert z["node_outputs"][0, 3] == pytest.approx(330.7)
        assert list(z["node_ids"]) == [1, 2, 3, 4]


def test_training_sample_skipped_on_node_count_mismatch(tmp_path):
    """KRİTİK: hizasız bir örnek, eksik örnekten çok daha kötüdür — model
    yanlış düğümün cevabını öğrenir ve bu hiçbir metrikte görünmez."""
    X = _inputs([])
    ip = tmp_path / "job.inputs.npz"
    write_inputs(ip, X, None)

    out = tmp_path / "job.train.npz"
    info = write_training_sample(
        ip, out, node_order=[1, 2], disp_vectors=[[0, 0, 0]] * 2, von_mises=[1.0, 1.0]
    )
    assert info is None
    assert not out.exists()


def test_gzip_frd_is_lossless_and_removes_original(tmp_path):
    frd = tmp_path / "job.frd"
    content = "FRD-CONTENT\n" * 5000
    frd.write_text(content, encoding="utf-8")
    original_size = frd.stat().st_size

    gz = gzip_frd(frd)
    assert gz is not None and gz.name == "job.frd.gz"
    assert not frd.exists(), "orijinal silinmeliydi"
    assert gz.stat().st_size < original_size

    with gzip.open(gz, "rt", encoding="utf-8") as fh:
        assert fh.read() == content, "sıkıştırma KAYIPSIZ olmalı"


def test_gzip_frd_returns_none_when_missing(tmp_path):
    assert gzip_frd(tmp_path / "yok.frd") is None


def test_normalize_mode_shape_scales_to_unit_peak():
    """Mod şekilleri özvektördür; mutlak genlik keyfidir. Normalize
    edilmezse aynı fiziksel mod iki run'da kat kat farklı genlikte gelir ve
    model öğrenilemez bir büyüklüğü öğrenmeye çalışır."""
    v = np.array([[0.0, 0.5, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 0.0]])
    out, scale = normalize_mode_shape(v)
    assert scale == pytest.approx(2.0)
    assert np.linalg.norm(out, axis=1).max() == pytest.approx(1.0)


def test_normalize_mode_shape_handles_zero_mode():
    out, scale = normalize_mode_shape(np.zeros((3, 3)))
    assert scale == 0.0
    assert np.all(out == 0.0)


def _modal_modes(n_nodes: int, n_modes: int):
    modes = []
    for k in range(n_modes):
        vecs = [[0.0, float(k + 1) * (i + 1), 0.0] for i in range(n_nodes)]
        modes.append(
            {"index": k + 1, "frequency_hz": 33.27 * (k + 1), "displacement_vectors": vecs}
        )
    return modes


def test_modal_sample_stores_shapes_and_frequencies(tmp_path):
    X = _inputs([{"type": "fixed", "face_ids": [1]}])
    ip = tmp_path / "job.inputs.npz"
    write_inputs(ip, X, None)

    out = tmp_path / "job.train.npz"
    info = write_modal_sample(ip, out, [1, 2, 3, 4], _modal_modes(4, 3))
    assert info is not None and info["modes"] == 3

    with np.load(out, allow_pickle=False) as z:
        assert str(z["analysis_type"]) == "modal"
        assert z["mode_shapes"].shape == (3, 4, 3)
        assert z["mode_frequencies_hz"].shape == (3,)
        assert z["mode_frequencies_hz"][0] == pytest.approx(33.27)
        # Her mod birim maksimuma normalize edilmiş olmalı
        for k in range(3):
            peak = np.linalg.norm(z["mode_shapes"][k], axis=1).max()
            assert peak == pytest.approx(1.0)
        # Ölçek çarpanı saklanmalı — atılmamalı
        assert z["mode_scale_factors"][0] > 0


def test_static_sample_is_marked_as_static(tmp_path):
    """Yükleyici iki şemayı ayırt edebilmeli; aksi halde modal örnek
    statik sanılıp gerilme kanalı aranır."""
    X = _inputs([])
    ip = tmp_path / "job.inputs.npz"
    write_inputs(ip, X, None)
    out = tmp_path / "job.train.npz"
    write_training_sample(
        ip, out, [1, 2, 3, 4], [[0, 0, 0]] * 4, [0.0] * 4
    )
    with np.load(out, allow_pickle=False) as z:
        assert str(z["analysis_type"]) == "static"


def test_modal_sample_skipped_on_misaligned_mode(tmp_path):
    X = _inputs([])
    ip = tmp_path / "job.inputs.npz"
    write_inputs(ip, X, None)
    bad = [{"index": 1, "frequency_hz": 10.0, "displacement_vectors": [[0, 1, 0]]}]
    out = tmp_path / "job.train.npz"
    assert write_modal_sample(ip, out, [1, 2, 3, 4], bad) is None
    assert not out.exists()
