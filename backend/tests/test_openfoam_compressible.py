"""R4 — sıkıştırılabilir çözücüler (rhoSimpleFoam, rhoCentralFoam) ve paralel koşu (R4b).

Dosya içerikleri (Docker'sız): mutlak basınç, sıcaklık, alphat, termofiziksel
özellikler, çözücüye göre şemalar; decomposeParDict ve adaptörün paralel betiği.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import app.solvers.openfoam as of
from app.solvers.base import InputArtifact
from app.solvers.openfoam_case import CfdCaseParams, case_files

PATCHES = [
    {"name": "inlet", "kind": "farfield", "velocity_m_s": [170, 0, 12]},
    {"name": "outlet", "kind": "outlet", "pressure": 500},
    {"name": "sides", "kind": "farfield", "velocity_m_s": [170, 0, 12]},
    {"name": "burun", "kind": "wall"},
]


def _files(solver: str, **over) -> dict[str, str]:
    return case_files(
        CfdCaseParams(
            nu_m2_s=1.46e-5,
            rho_kg_m3=1.225,
            patches=PATCHES,
            turbulence={"model": "kOmegaSST"},
            solver=solver,
            forces={"patches": ["burun"], "u_ref_m_s": 170, "l_ref_m": 0.1, "a_ref_m2": 0.00785},
            **over,
        )
    )


def test_rho_simple_files():
    f = _files("rhoSimpleFoam", compressible={"p_inf_pa": 90000, "t_inf_k": 280, "transonic": True})
    assert set(f) >= {"0/U", "0/p", "0/T", "0/alphat", "0/k", "0/omega", "0/nut", "constant/thermophysicalProperties"}
    assert "constant/transportProperties" not in f
    assert "dimensions      [1 -1 -2 0 0 0 0];" in f["0/p"] and "internalField   uniform 90000;" in f["0/p"]
    assert "outlet\n    {\n        type            fixedValue;\n        value           uniform 90500;" in f["0/p"]
    assert "type            freestreamPressure;" in f["0/p"]
    assert "internalField   uniform 280;" in f["0/T"] and "type            inletOutlet;" in f["0/T"]
    assert "compressible::alphatWallFunction" in f["0/alphat"]
    thermo = f["constant/thermophysicalProperties"]
    assert "hePsiThermo" in thermo and "perfectGas" in thermo
    assert f"mu          {1.225 * 1.46e-5:.6g};" in thermo
    assert "application     rhoSimpleFoam;" in f["system/controlDict"]
    assert "transonic       yes;" in f["system/fvSolution"] and "div(phid,p)" in f["system/fvSchemes"]
    assert "rho             0.01;" in f["system/fvSolution"]
    assert "rho             rho;" in f["system/controlDict"]  # kuvvet: gerçek yoğunluk alanı


def test_rho_central_files_lts():
    f = _files("rhoCentralFoam", compressible={"max_co": 0.4})
    assert "application     rhoCentralFoam;" in f["system/controlDict"]
    assert "maxCo           0.4;" in f["system/controlDict"]
    assert "fluxScheme      Kurganov;" in f["system/fvSchemes"]
    assert "default         localEuler;" in f["system/fvSchemes"]
    assert '"(rho|rhoU|rhoE)"' in f["system/fvSolution"] and "diagonal" in f["system/fvSolution"]
    assert "div(phi,k)" in f["system/fvSchemes"]


def test_incompressible_unchanged_and_decompose():
    f = _files("simpleFoam")
    assert "0/T" not in f and "constant/transportProperties" in f
    assert "rho             rhoInf;" in f["system/controlDict"]
    assert "system/decomposeParDict" not in f
    par = _files("simpleFoam", control={"n_procs": 4})
    assert "numberOfSubdomains 4;" in par["system/decomposeParDict"]
    assert "numberOfSubdomains 8;" in _files("rhoCentralFoam", control={"n_procs": 8})["system/decomposeParDict"]


def test_decompose_count_and_parallel_script(monkeypatch, tmp_path):
    adapter = of.OpenFoamAdapter()
    art = adapter.build_input({"output_dir": str(tmp_path), "case": {
        "nu_m2_s": 1e-5, "patches": [{"name": "inlet", "kind": "inlet", "velocity_m_s": [1, 0, 0]}, {"name": "outlet", "kind": "outlet"}],
        "control": {"n_procs": 4},
    }})
    assert of.decompose_count(tmp_path) == 4
    seen: dict[str, str] = {}

    def fake(image, case_dir, script):
        seen["script"] = script
        log = "Time = 1\n\nEnd\n"
        code = f"import sys, pathlib\npathlib.Path({str(case_dir)!r}, 'log.simpleFoam').write_text({log!r})\nsys.stdout.write({log!r})\n"
        return [sys.executable, "-c", code]

    monkeypatch.setenv("OPENFOAM_DOCKER_IMAGE", "fake")
    monkeypatch.setattr(of, "docker_command", fake)
    adapter.submit(InputArtifact(path=Path(art.path), kind="directory"))
    s = seen["script"]
    assert "decomposePar -force" in s and "mpirun --oversubscribe -np 4 simpleFoam -parallel" in s
    assert "reconstructPar -latestTime" in s and "OMPI_ALLOW_RUN_AS_ROOT=1" in s


def test_docker_command_has_shm():
    cmd = of.docker_command("img", Path("."), "x")
    assert cmd[cmd.index("--shm-size") + 1] == "1g"
