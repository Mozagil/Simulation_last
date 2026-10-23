"""Faz 5.0 — ChronoAdapter: JSON girdi, CSV sonuç ayrıştırma, koşu (PyChrono varsa)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from app.solvers.base import SolverError
from app.solvers.chrono import (
    CASE_FILE,
    ChronoAdapter,
    ChronoQuarterCarParams,
    ChronoSuspensionRigParams,
    parse_results_csv,
    resolve_chrono_runtime,
    run_command,
)


def test_build_input_writes_case_json(tmp_path):
    ad = ChronoAdapter(work_root=tmp_path)
    art = ad.build_input({"sprung_mass_kg": 350, "road": {"height_mm": 80, "length_m": 1.5}, "job_id": "j1"})
    assert art.kind == "directory" and art.path == tmp_path / "j1"
    case = json.loads((art.path / CASE_FILE).read_text(encoding="utf-8"))
    assert case["schema"] == "chrono_case/1"
    assert case["params"]["sprung_mass_kg"] == 350 and case["params"]["road"]["height_mm"] == 80
    assert case["params"]["suspension_k_n_per_m"] == 20000.0  # varsayılan korunur


@pytest.mark.parametrize("bad", [{"sprung_mass_kg": 0}, {"scenario": "excavator"}, {"dt_s": 1.0}])
def test_build_input_rejects(tmp_path, bad):
    with pytest.raises(SolverError, match="geçersiz"):
        ChronoAdapter(work_root=tmp_path).build_input(bad)


def test_runtime_resolution(monkeypatch, tmp_path):
    monkeypatch.delenv("CHRONO_PYTHON", raising=False)
    monkeypatch.delenv("CHRONO_DOCKER_IMAGE", raising=False)
    assert resolve_chrono_runtime() is None
    monkeypatch.setenv("CHRONO_DOCKER_IMAGE", "simsurrogate-chrono:9.0")
    cmd = run_command(resolve_chrono_runtime(), tmp_path)
    assert cmd[1:3] == ["run", "--rm"] and cmd[-1] == "/work" and "simsurrogate-chrono:9.0" in cmd
    monkeypatch.setenv("CHRONO_PYTHON", "/opt/conda/envs/chrono/bin/python")
    cmd = run_command(resolve_chrono_runtime(), tmp_path)
    assert cmd[0].endswith("python") and cmd[1].endswith("chrono_run.py")


def test_submit_without_runtime_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("CHRONO_PYTHON", raising=False)
    monkeypatch.delenv("CHRONO_DOCKER_IMAGE", raising=False)
    ad = ChronoAdapter(work_root=tmp_path)
    with pytest.raises(SolverError, match="CHRONO_PYTHON"):
        ad.submit(ad.build_input({"job_id": "j2"}))


def test_parse_results_csv(tmp_path):
    csvp = tmp_path / "results.csv"
    csvp.write_text(
        "time_s,body_acc_m_s2,susp_force_n\n0,0,-3924\n0.001,2.5,-3900\n0.002,-1.5,-4000\n", encoding="utf-8"
    )
    (tmp_path / "summary.json").write_text('{"steps": 3}', encoding="utf-8")
    rs = parse_results_csv(csvp, tmp_path / "summary.json")
    assert rs.curves["time"] == [0.0, 0.001, 0.002] and rs.curves["susp_force_n"][-1] == -4000.0
    assert rs.scalars["body_acc_m_s2_max"] == 2.5 and rs.scalars["susp_force_n_min"] == -4000.0
    assert rs.scalars["body_acc_m_s2_rms"] == pytest.approx(((0 + 6.25 + 2.25) / 3) ** 0.5)
    assert rs.diagnostics["summary"] == {"steps": 3} and rs.diagnostics["columns"] == ["body_acc_m_s2", "susp_force_n"]


def test_parse_results_requires_time_header(tmp_path):
    p = tmp_path / "results.csv"
    p.write_text("t,x\n0,1\n", encoding="utf-8")
    with pytest.raises(SolverError, match="time_s"):
        parse_results_csv(p)


@pytest.mark.skipif(not os.environ.get("CHRONO_PYTHON"), reason="CHRONO_PYTHON yok (5.1'de Codespaces)")
def test_quarter_car_run_smoke(tmp_path):
    ad = ChronoAdapter(work_root=tmp_path)
    job = ad.submit(ad.build_input({"job_id": "smoke", "t_end_s": 1.0, "output_every": 10}))
    st = ad.poll_status(job)
    assert st.state == "done", st.message
    rs = ad.parse_results(job)
    assert rs.scalars["body_acc_m_s2_max"] > 0 and len(rs.curves["time"]) > 50


def test_params_defaults_are_finite():
    p = ChronoQuarterCarParams()
    assert p.scenario == "quarter_car_bump" and p.road.kind == "cosine_bump"


def test_build_suspension_rig_writes_case(tmp_path):
    ad = ChronoAdapter(work_root=tmp_path)
    art = ad.build_input({"scenario": "suspension_test_rig", "spring_k_n_per_m": 15000, "job_id": "rig1"})
    case = json.loads((art.path / CASE_FILE).read_text(encoding="utf-8"))
    assert case["params"]["scenario"] == "suspension_test_rig"
    assert case["params"]["spring_k_n_per_m"] == 15000
    assert case["params"]["upright_mass_kg"] == 8.0
    assert case["params"]["angle_amp_rad"] == 0.04
    assert "sprung_mass_kg" not in case["params"]


@pytest.mark.parametrize("bad", [
    {"scenario": "suspension_test_rig", "upper_arm_mass_kg": 0},
    {"scenario": "suspension_test_rig", "angle_amp_rad": 1.0},
    {"scenario": "suspension_test_rig", "dt_s": 1.0},
])
def test_build_suspension_rig_rejects(tmp_path, bad):
    with pytest.raises(SolverError, match="geçersiz"):
        ChronoAdapter(work_root=tmp_path).build_input(bad)


def test_suspension_rig_defaults_are_finite():
    p = ChronoSuspensionRigParams()
    assert p.scenario == "suspension_test_rig" and p.lower_arm_mass_kg == 5.0


@pytest.mark.skipif(
    not (os.environ.get("CHRONO_PYTHON") or os.environ.get("CHRONO_DOCKER_IMAGE")),
    reason="Chrono runtime yok",
)
def test_suspension_rig_smoke(tmp_path):
    ad = ChronoAdapter(work_root=tmp_path)
    job = ad.submit(ad.build_input({
        "scenario": "suspension_test_rig", "job_id": "rig-smoke", "t_end_s": 0.4, "output_every": 20,
    }))
    st = ad.poll_status(job)
    assert st.state == "done", st.message
    rs = ad.parse_results(job)
    assert "upper_chassis_fz_n" in rs.curves and "spring_force_n" in rs.curves
    assert "motor_torque_nm" in rs.curves and len(rs.curves["time"]) > 5
    # Şasi mafsalı üst kol ağırlığının bir kısmını dünya Z'de taşır.
    assert rs.scalars["upper_chassis_fz_n_min"] < -5.0
    assert rs.scalars["spring_force_n_max"] - rs.scalars["spring_force_n_min"] > 1.0
