"""1.24c1 — geri sekme metrikleri (animasyon karelerinden; model + parça)."""

from __future__ import annotations

import math

import pytest

from app.postprocess.crash_springback import springback_from_vtk_texts, springback_scalars

# Düğümler: 0–3 parça 1 (dörtgen), 4–7 parça 2 (dörtgen), 8–11 rijit duvar (NODE_ID 0),
# 12 hiçbir hücrede değil (rijit gövde ana düğümü gibi).
CELLS = [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]]
TYPES = [9, 9, 9]
PART = [1, 2, 3]
NODE_ID = [float(i + 1) for i in range(8)] + [0.0] * 4 + [99.0]


def _frame(t: float, u1: float, u2: float, wall: float = 500.0, free: float = 900.0) -> dict:
    """Parça 1 düğümleri x'te u1, parça 2 düğümleri y'de u2 (son düğüm u2/2)."""
    disp = [[u1, 0.0, 0.0]] * 4 + [[0.0, u2, 0.0]] * 3 + [[0.0, u2 / 2, 0.0]]
    disp += [[wall, 0.0, 0.0]] * 4 + [[free, 0.0, 0.0]]
    return {
        "time": t,
        "points": [[0.0, 0.0, 0.0]] * 13,
        "cells": CELLS,
        "cell_types": TYPES,
        "point_data": {"Displacement": disp, "NODE_ID": NODE_ID},
        "cell_data": {"PART_ID": PART},
    }


def test_model_and_part_springback():
    # parça 1: 0 → 10 → 8 (geri sekme 2); parça 2: 0 → 4 → 4 (geri sekme yok)
    frames = [_frame(0.0, 0.0, 0.0), _frame(1.0, 10.0, 3.0), _frame(2.0, 9.0, 4.0), _frame(3.0, 8.0, 4.0)]
    s = springback_scalars(frames)
    # model: kare başına en büyük |u| (duvar 500 ve serbest düğüm 900 sayılmaz)
    assert s["model_disp_peak_mm"] == pytest.approx(10.0)
    assert s["model_disp_peak_t_ms"] == pytest.approx(1.0)
    assert s["model_disp_final_mm"] == pytest.approx(8.0)
    assert s["springback_mm"] == pytest.approx(2.0)
    assert s["springback_ratio"] == pytest.approx(0.2)
    # parça başına
    assert s["part_1_springback_mm"] == pytest.approx(2.0)
    assert s["part_1_springback_ratio"] == pytest.approx(0.2)
    assert s["part_2_disp_peak_mm"] == pytest.approx(4.0)
    assert s["part_2_disp_peak_t_ms"] == pytest.approx(2.0)
    assert s["part_2_springback_mm"] == pytest.approx(0.0)
    assert not any(k.startswith("part_3_") for k in s)  # rijit duvar parçası değil
    # def: parça 1 düğümleri birlikte kayıyor → deformasyon 0; parça 2: 3 düğüm u2, 1 düğüm u2/2
    # → ū = 0.875·u2, en büyük sapma 0.375·u2 (u2 = 4 → 1.5)
    assert s["part_1_def_peak_mm"] == pytest.approx(0.0)
    assert s["part_2_def_peak_mm"] == pytest.approx(1.5)
    assert s["part_2_springback_def_mm"] == pytest.approx(0.0)


def test_translation_removed_definition():
    """D: parça 1 kayan + bir düğümde geri dönen çökme → mutlak tanım ötelemeyi, def çökmeyi ölçer."""

    def fr(t: float, shift: float, dent: float) -> dict:
        f = _frame(t, 0.0, 0.0)
        disp = f["point_data"]["Displacement"]
        for v in range(4):
            disp[v] = [shift + (dent if v == 0 else 0.0), 0.0, 0.0]
        return f

    s = springback_scalars([fr(0.0, 0.0, 0.0), fr(1.0, 50.0, 2.0), fr(2.0, 100.0, 1.0)])
    # mutlak: öteleme büyüyor → tepe son karede, geri sekme 0
    assert s["part_1_disp_peak_t_ms"] == pytest.approx(2.0)
    assert s["part_1_springback_mm"] == pytest.approx(0.0)
    # def: ū = shift + dent/4 → en büyük sapma 3·dent/4: 1.5 → 0.75
    assert s["part_1_def_peak_mm"] == pytest.approx(1.5)
    assert s["part_1_def_peak_t_ms"] == pytest.approx(1.0)
    assert s["part_1_def_final_mm"] == pytest.approx(0.75)
    assert s["part_1_springback_def_mm"] == pytest.approx(0.75)
    assert s["part_1_springback_def_ratio"] == pytest.approx(0.5)
    # model def = parçaların en büyüğü (parça 2 hareketsiz)
    assert s["springback_def_mm"] == pytest.approx(0.75)
    assert s["model_def_peak_mm"] == pytest.approx(1.5)


def test_no_motion_ratio_absent_and_nonfinite_skipped():
    frames = [_frame(0.0, 0.0, 0.0), _frame(1.0, 0.0, 0.0)]
    s = springback_scalars(frames)
    assert s["springback_mm"] == 0.0 and "springback_ratio" not in s
    # ıraksama: NaN düğüm sayılmaz
    f = _frame(1.0, 5.0, 1.0)
    f["point_data"]["Displacement"][0] = [math.nan, 0.0, 0.0]
    assert springback_scalars([_frame(0.0, 0.0, 0.0), f])["model_disp_peak_mm"] == pytest.approx(5.0)


def test_empty_or_without_displacement():
    assert springback_scalars([]) == {}
    f = _frame(0.0, 1.0, 1.0)
    f["point_data"].pop("Displacement")
    assert springback_scalars([f]) == {}


def _vtk(t: float, ux: float) -> str:
    pts = "\n".join(["0 0 0", "1 0 0", "1 1 0", "0 1 0"])
    disp = "\n".join([f"{ux} 0 0"] * 4)
    return (
        "# vtk DataFile Version 3.0\nanim\nASCII\nDATASET UNSTRUCTURED_GRID\n"
        f"FIELD FieldData 1\nTIME 1 1 double\n{t}\n"
        f"POINTS 4 float\n{pts}\nCELLS 1 5\n4 0 1 2 3\nCELL_TYPES 1\n9\n"
        "POINT_DATA 4\nSCALARS NODE_ID int 1\nLOOKUP_TABLE default\n1\n2\n3\n4\n"
        f"VECTORS Displacement float\n{disp}\n"
        "CELL_DATA 1\nSCALARS PART_ID int 1\nLOOKUP_TABLE default\n7\n"
    )


def test_from_vtk_texts():
    s = springback_from_vtk_texts([_vtk(0.0, 0.0), _vtk(0.5, 3.0), _vtk(1.0, 2.25)])
    assert s["springback_mm"] == pytest.approx(0.75)
    assert s["part_7_springback_ratio"] == pytest.approx(0.25)
    assert s["model_disp_peak_t_ms"] == pytest.approx(0.5)


def test_part_map_renames_to_mesh_ids_and_drops_unmapped():
    """Kart kimliği 1 → mesh #0; haritada olmayan kart (2: ör. yay) parça satırına girmez."""
    frames = [_frame(0.0, 0.0, 0.0), _frame(1.0, 10.0, 3.0), _frame(2.0, 8.0, 4.0)]
    s = springback_scalars(frames, part_map={1: 0})
    assert s["part_0_springback_mm"] == pytest.approx(2.0)
    assert not any(k.startswith(("part_1_", "part_2_")) for k in s)
    assert s["model_disp_peak_mm"] == pytest.approx(10.0)  # model değeri tüm parçalardan


def test_deck_writes_part_map(tmp_path):
    import json

    from app.postprocess.crash_springback import read_part_map
    from app.solvers.openradioss import OpenRadiossAdapter
    from tests.test_crash_multipart import _two_part_params

    art = OpenRadiossAdapter().build_input(_two_part_params(tmp_path))
    assert json.loads((art.path.parent / "part_map.json").read_text()) == {"1": 0, "2": 1}
    assert read_part_map(art.path.parent) == {1: 0, 2: 1}
    assert read_part_map(tmp_path / "yok") is None
