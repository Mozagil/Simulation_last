"""CFD koşu PDF raporu — job.json'lu ve job.json'suz."""

from __future__ import annotations

from datetime import datetime, timezone

from app.postprocess.cfd_report import build_cfd_report_pdf

JOB = {
    "application": "rhoSimpleFoam",
    "turbulence": "kOmegaSST",
    "end_iterations": 600,
    "rho_kg_m3": 1.1,
    "mesh": {"kind": "mesh_id", "cells": 56298},
    "case": {"nu_m2_s": 1.46e-5, "control": {"relax_u": 0.5, "relax_other": 0.3, "n_procs": 4},
             "compressible": {"p_inf_pa": 90000, "t_inf_k": 280},
             "patches": [{"name": "inlet", "kind": "farfield", "velocity_m_s": [170, 0, 12]}, {"name": "burun", "kind": "wall"}]},
    "scalars": {"iterations": 182, "converged": True, "Cd": 0.46, "Cd_mean": 0.461, "Cd_std": 0.002, "Cl": 1.11,
                "coeff_average_window": 100, "force_burun_x": 12.0, "force_burun_y": 0.1, "force_burun_z": 3.0,
                "force_burun_pressure_x": 10.0, "force_burun_viscous_x": 2.0},
    "rocket": {"speed_m_s": 170, "alpha_deg": 4, "mach": 0.5},
    "rocket_aero": {"q_pa": 17698, "a_ref_m2": 0.00785, "CA": 0.38, "CN": 1.14, "CD": 0.46, "CL": 1.11, "Cm": -3.2, "x_ref_m": 0.9,
                    "x_cp_m": 1.18, "CN_alpha_per_rad": 16.4, "stability_calibers": 2.8,
                    "barrowman": {"cn_alpha_barrowman": 10.8, "x_cp_barrowman_m": 1.177, "cn_alpha_diff_percent": 51.4, "x_cp_diff_calibers": 0.07}},
    "curves": {"iteration": [1, 2, 3, 4], "residuals": {"p": [1, 0.1, 0.01, 0.001], "Ux": [1, 0.5, 0.2, 0.1]},
               "force_coeffs": {"iteration": [1, 2, 3, 4], "Cd": [0.5, 0.47, 0.46, 0.46], "Cl": [1.0, 1.1, 1.1, 1.11]}},
}
RUN = {"id": 7, "name": "R4 deneme", "status": "solved", "message": "bitti", "created_at": datetime(2026, 10, 9, tzinfo=timezone.utc), "scalars": {}, "reference": None}


def test_report_full():
    pdf = build_cfd_report_pdf(RUN, JOB)
    assert pdf.startswith(b"%PDF") and len(pdf) > 3000


def test_report_without_job():
    assert build_cfd_report_pdf({**RUN, "reference": {"kind": "poiseuille", "dp_error": 0.02}}, {}).startswith(b"%PDF")
