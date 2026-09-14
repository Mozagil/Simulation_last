"""0.4.5: FEA vs analitik sapma (ccx gerektirmez)."""

from __future__ import annotations

import pytest

from app.templates.compare import (
    REL_WARN_THRESHOLD,
    build_analytic_comparison,
    cload_resultant_n,
    first_pressure_mpa,
)

REF_PARAMS = {"length": 500.0, "thickness": 10.0, "width": 50.0}
MATERIALS = [{"youngs_modulus": 210e9, "poisson_ratio": 0.3}]
BCS = [
    {"type": "fixed", "face_ids": [1]},
    {"type": "cload", "face_ids": [2], "fx": 0.0, "fy": -500.0, "fz": 0.0},
]


def test_cload_resultant_sums_magnitude():
    assert cload_resultant_n(BCS) == 500.0
    assert cload_resultant_n([{"type": "fixed"}]) is None
    assert cload_resultant_n([{"type": "cload", "magnitude": 120.0}]) == 120.0


def test_first_pressure_mpa():
    assert first_pressure_mpa([{"type": "fixed"}]) is None
    assert first_pressure_mpa(
        [{"type": "pressure", "face_ids": [4], "magnitude": 10.0}]
    ) == 10.0
    assert first_pressure_mpa(
        [{"type": "pressure", "magnitude": -8.5}]
    ) == 8.5


def test_no_template_returns_none():
    assert (
        build_analytic_comparison(
            template_id=None,
            template_params=None,
            materials=MATERIALS,
            bcs=BCS,
            analysis_type="static",
            fea_scalars={"max_displacement": 23.92, "max_von_mises": 330.7},
        )
        is None
    )


def test_modal_returns_none():
    assert (
        build_analytic_comparison(
            template_id="cantilever_beam",
            template_params=REF_PARAMS,
            materials=MATERIALS,
            bcs=BCS,
            analysis_type="modal",
            fea_scalars={"max_displacement": 1.0, "max_von_mises": 1.0},
        )
        is None
    )


def test_missing_cload_is_skipped():
    out = build_analytic_comparison(
        template_id="cantilever_beam",
        template_params=REF_PARAMS,
        materials=MATERIALS,
        bcs=[{"type": "fixed", "face_ids": [1]}],
        analysis_type="static",
        fea_scalars={"max_displacement": 23.92, "max_von_mises": 330.7},
    )
    assert out is not None
    assert out["skipped"] is True
    assert "CLOAD" in out["reason"]


def test_reference_case_within_threshold():
    """Faz 0 doğrulama sayıları (23.92 mm / 330.7 MPa) uyarı üretmemeli."""
    out = build_analytic_comparison(
        template_id="cantilever_beam",
        template_params=REF_PARAMS,
        materials=MATERIALS,
        bcs=BCS,
        analysis_type="static",
        fea_scalars={"max_displacement": 23.92, "max_von_mises": 330.7},
    )
    assert out is not None
    assert out["skipped"] is False
    assert out["warned"] is False
    by_key = {m["key"]: m for m in out["metrics"]}
    disp = by_key["max_displacement"]
    vm = by_key["max_von_mises"]
    assert disp["analytic"] == pytest.approx(23.81, abs=0.01)
    assert disp["warn"] is False
    assert disp["rel_error"] < REL_WARN_THRESHOLD["max_displacement"]
    assert vm["analytic"] == pytest.approx(300.0, abs=0.01)
    assert vm["warn"] is False
    assert vm["rel_error"] < REL_WARN_THRESHOLD["max_von_mises"]


def test_large_displacement_deviation_warns():
    out = build_analytic_comparison(
        template_id="cantilever_beam",
        template_params=REF_PARAMS,
        materials=MATERIALS,
        bcs=BCS,
        analysis_type="static",
        fea_scalars={"max_displacement": 50.0, "max_von_mises": 300.0},
    )
    assert out is not None
    assert out["warned"] is True
    disp = next(m for m in out["metrics"] if m["key"] == "max_displacement")
    assert disp["warn"] is True
    vm = next(m for m in out["metrics"] if m["key"] == "max_von_mises")
    assert vm["warn"] is False


def test_simply_supported_uses_midspan_formula():
    out = build_analytic_comparison(
        template_id="simply_supported_beam",
        template_params=REF_PARAMS,
        materials=MATERIALS,
        bcs=BCS,
        analysis_type="static",
        fea_scalars={"max_displacement": 1.49, "max_von_mises": 80.0},
    )
    assert out is not None
    assert out["skipped"] is False
    by_key = {m["key"]: m for m in out["metrics"]}
    assert by_key["max_displacement"]["analytic"] == pytest.approx(1.4881, abs=0.001)
    assert by_key["max_von_mises"]["analytic"] == pytest.approx(75.0, abs=0.01)
    assert out["warned"] is False


def test_plate_with_hole_compares_only_von_mises():
    out = build_analytic_comparison(
        template_id="plate_with_hole",
        template_params={"height": 200.0, "width": 100.0, "thickness": 5.0, "diameter": 20.0},
        materials=MATERIALS,
        bcs=[
            {"type": "fixed", "face_ids": [1]},
            {"type": "cload", "face_ids": [2], "fx": 500.0, "fy": 0.0, "fz": 0.0},
        ],
        analysis_type="static",
        fea_scalars={"max_displacement": 0.1, "max_von_mises": 3.2},
    )
    assert out is not None
    assert out["skipped"] is False
    keys = {m["key"] for m in out["metrics"]}
    assert keys == {"max_von_mises"}
    assert out["metrics"][0]["analytic"] == pytest.approx(3.14, abs=0.01)
    assert out["warned"] is False


def test_dogbone_nominal_gauge_stress():
    out = build_analytic_comparison(
        template_id="dogbone",
        template_params={},
        materials=MATERIALS,
        bcs=[
            {"type": "fixed", "face_ids": [1]},
            {"type": "cload", "face_ids": [2], "fx": 500.0, "fy": 0.0, "fz": 0.0},
        ],
        analysis_type="static",
        fea_scalars={"max_von_mises": 14.0},
    )
    assert out is not None
    assert {m["key"] for m in out["metrics"]} == {"max_von_mises"}
    assert out["metrics"][0]["analytic"] == pytest.approx(13.333, abs=0.01)
    assert out["warned"] is False


def test_thick_walled_tube_uses_pressure_without_cload():
    out = build_analytic_comparison(
        template_id="thick_walled_tube",
        template_params={"length": 100.0, "inner_radius": 10.0, "outer_radius": 20.0},
        materials=MATERIALS,
        bcs=[
            {"type": "fixed", "face_ids": [1]},
            {"type": "pressure", "face_ids": [2], "magnitude": 10.0},
        ],
        analysis_type="static",
        fea_scalars={"max_von_mises": 23.0},
    )
    assert out is not None
    assert out["skipped"] is False
    assert {m["key"] for m in out["metrics"]} == {"max_von_mises"}
    assert out["metrics"][0]["analytic"] == pytest.approx(23.333, abs=0.01)
    assert out["warned"] is False


def test_torsion_shaft_uses_force_times_radius():
    out = build_analytic_comparison(
        template_id="torsion_shaft",
        template_params={"length": 100.0, "radius": 10.0},
        materials=MATERIALS,
        bcs=[
            {"type": "fixed", "face_ids": [1]},
            {"type": "cload", "edge_ids": [1], "fx": 0.0, "fy": 500.0, "fz": 0.0},
        ],
        analysis_type="static",
        fea_scalars={"max_displacement": 0.004, "max_von_mises": 5.5},
    )
    assert out is not None
    assert out["skipped"] is False
    by_key = {m["key"]: m for m in out["metrics"]}
    assert by_key["max_von_mises"]["analytic"] == pytest.approx(5.513, abs=0.01)
    assert out["warned"] is False
