"""Faz 2.1 — OpenFOAM case yazıcı (ESI v2412): dosya içerikleri ve doğrulama.

Birim testleri Docker'sız. Son test yazıcının dosyalarıyla resmi pitzDaily
ağında simpleFoam (k-ω SST) koşturur; OPENFOAM_DOCKER_IMAGE yoksa atlanır.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess

import pytest
from pydantic import ValidationError

from app.solvers.base import SolverError
from app.solvers.openfoam import OpenFoamAdapter
from app.solvers.openfoam_case import CfdCaseParams, case_files, inlet_turbulence

CHANNEL = {
    "nu_m2_s": 1e-3,
    "patches": [
        {"name": "inlet", "kind": "inlet", "velocity_m_s": [0.1, 0, 0]},
        {"name": "outlet", "kind": "outlet", "pressure": 0},
        {"name": "walls", "kind": "wall"},
        {"name": "frontAndBack", "kind": "empty"},
    ],
}


def _files(**over) -> dict[str, str]:
    return case_files(CfdCaseParams.model_validate({**CHANNEL, **over}))


def test_laminar_case_has_only_u_p_and_laminar_model():
    files = _files()
    assert sorted(files) == [
        "0/U",
        "0/p",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
    ]
    assert "simulationType  laminar;" in files["constant/turbulenceProperties"]
    assert "nu              0.001;" in files["constant/transportProperties"]
    assert "div(phi,k)" not in files["system/fvSchemes"]
    assert '"(k|omega)"' not in files["system/fvSolution"]


def test_boundary_types_per_patch_kind():
    files = _files()
    u, p = files["0/U"], files["0/p"]
    assert "inlet\n    {\n        type            fixedValue;\n        value           uniform (0.1 0 0);" in u
    assert "outlet\n    {\n        type            zeroGradient;" in u
    assert "walls\n    {\n        type            noSlip;" in u
    assert "frontAndBack\n    {\n        type            empty;" in u
    assert "outlet\n    {\n        type            fixedValue;\n        value           uniform 0;" in p
    assert "inlet\n    {\n        type            zeroGradient;" in p
    assert "dimensions      [0 2 -2 0 0 0 0];" in p  # kinematik basınç
    for text in files.values():
        assert text.startswith("/*") and "FoamFile\n{" in text


def test_komega_sst_inlet_values_from_intensity_and_length():
    files = _files(turbulence={"model": "kOmegaSST", "intensity": 0.05, "length_scale_m": 0.01})
    k, w = inlet_turbulence(0.1, CfdCaseParams.model_validate({**CHANNEL, "turbulence": {"model": "kOmegaSST"}}).turbulence)
    assert math.isclose(k, 1.5 * (0.1 * 0.05) ** 2)
    assert math.isclose(w, math.sqrt(k) / (0.09**0.25 * 0.01))
    assert "RASModel        kOmegaSST;" in files["constant/turbulenceProperties"]
    assert "walls\n    {\n        type            kqRWallFunction;" in files["0/k"]
    assert "walls\n    {\n        type            omegaWallFunction;" in files["0/omega"]
    assert "walls\n    {\n        type            nutkWallFunction;" in files["0/nut"]
    assert f"internalField   uniform {k:.6g};" in files["0/k"]
    assert '"(U|k|omega)"' in files["system/fvSolution"]


def test_control_values_written():
    files = _files(control={"iterations": 500, "write_interval": 50, "residual_p": 1e-4, "relax_u": 0.7})
    assert "endTime         500;" in files["system/controlDict"]
    assert "writeInterval   50;" in files["system/controlDict"]
    assert "p               0.0001;" in files["system/fvSolution"]
    assert "U               0.7;" in files["system/fvSolution"]


@pytest.mark.parametrize(
    "bad, msg",
    [
        ({"patches": [{"name": "inlet", "kind": "inlet"}, {"name": "o", "kind": "outlet"}]}, "hız"),
        ({"patches": [{"name": "a", "kind": "inlet", "velocity_m_s": [1, 0, 0]}, {"name": "w", "kind": "wall"}]}, "çıkış"),
        ({"patches": [{"name": "1in", "kind": "inlet", "velocity_m_s": [1, 0, 0]}, {"name": "o", "kind": "outlet"}]}, "geçersiz"),
        (
            {
                "patches": [
                    {"name": "a", "kind": "inlet", "velocity_m_s": [1, 0, 0]},
                    {"name": "a", "kind": "outlet"},
                ]
            },
            "tekrar",
        ),
        ({"nu_m2_s": 0}, "greater than 0"),
    ],
)
def test_validation_errors(bad, msg):
    with pytest.raises(ValidationError, match=msg):
        CfdCaseParams.model_validate({**CHANNEL, **bad})


def test_adapter_build_input_writes_case_directory(tmp_path):
    art = OpenFoamAdapter().build_input({"output_dir": str(tmp_path / "case"), "case": CHANNEL})
    assert art.kind == "directory"
    assert (art.path / "0" / "U").is_file()
    assert (art.path / "system" / "fvSolution").is_file()
    with pytest.raises(SolverError, match="geçersiz"):
        OpenFoamAdapter().build_input({"output_dir": str(tmp_path / "x"), "case": {"nu_m2_s": 1e-3, "patches": []}})


def _docker_ready(image: str | None) -> bool:
    if not image or shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0


@pytest.mark.skipif(
    not _docker_ready(os.environ.get("OPENFOAM_DOCKER_IMAGE")),
    reason="OPENFOAM_DOCKER_IMAGE tanımlı değil ya da imaj yok",
)
def test_generated_case_runs_on_pitzdaily_mesh(tmp_path):
    from app.solvers.openfoam import parse_solver_log
    from scripts.openfoam_case_check import run

    assert run(tmp_path, os.environ["OPENFOAM_DOCKER_IMAGE"].strip(), "kOmegaSST") == 0
    log = parse_solver_log((tmp_path / "log.simpleFoam").read_text(errors="replace"))
    assert log.finished and log.converged
    assert set(log.initial_residuals) >= {"Ux", "Uy", "p", "k", "omega"}
