"""Faz 2.1 kontrolü: case yazıcının dosyalarıyla resmi pitzDaily ağında koşu.

Mesh yazıcı 2.3'te geleceği için ağ öğreticinin ``blockMeshDict``'inden
alınır; ``0/``, ``constant/``, ``system/`` dosyaları bizim yazıcıdan gelir.

Kullanım (backend klasöründen):
    .venv/Scripts/python.exe scripts/openfoam_case_check.py [laminar|kOmegaSST] [hedef_klasör]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.solvers.openfoam import (  # noqa: E402
    DEFAULT_IMAGE,
    OpenFoamAdapter,
    docker_command,
    parse_solver_log,
    resolve_openfoam_image,
)

SCRIPT = (
    "set -e; cp $FOAM_TUTORIALS/incompressible/simpleFoam/pitzDaily/system/blockMeshDict system/ && "
    "blockMesh > log.blockMesh 2>&1 && simpleFoam > log.simpleFoam 2>&1"
)


def pitzdaily_case(model: str, iterations: int = 2000) -> dict:
    return {
        "nu_m2_s": 1e-5,
        "patches": [
            {"name": "inlet", "kind": "inlet", "velocity_m_s": [10, 0, 0]},
            {"name": "outlet", "kind": "outlet", "pressure": 0},
            {"name": "upperWall", "kind": "wall"},
            {"name": "lowerWall", "kind": "wall"},
            {"name": "frontAndBack", "kind": "empty"},
        ],
        "turbulence": {"model": model, "intensity": 0.05, "length_scale_m": 0.0025},
        "control": {"iterations": iterations},
    }


def run(case_dir: Path, image: str, model: str, iterations: int = 2000) -> int:
    OpenFoamAdapter().build_input({"output_dir": str(case_dir), "case": pitzdaily_case(model, iterations)})
    t0 = time.perf_counter()
    proc = subprocess.run(docker_command(image, case_dir, SCRIPT), capture_output=True, text=True)
    wall = time.perf_counter() - t0
    log_path = case_dir / "log.simpleFoam"
    if not log_path.is_file():
        bm = case_dir / "log.blockMesh"
        print(f"HATA (çıkış {proc.returncode}): {bm.read_text(errors='replace')[-1500:] if bm.is_file() else proc.stderr[-1500:]}")
        return 1
    log = parse_solver_log(log_path.read_text(errors="replace"))
    print(f"model {model}: çıkış {proc.returncode} · {wall:.1f} s · iterasyon {log.last_iteration} · yakınsadı {log.converged} · End {log.finished}")
    for name, values in log.initial_residuals.items():
        print(f"  {name:6s} ilk {values[0]:.3e}  son {values[-1]:.3e}")
    if log.fatal_error:
        print(f"FATAL: {log.fatal_error}")
    return 0 if proc.returncode == 0 and log.finished else 1


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "kOmegaSST"
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(tempfile.mkdtemp(prefix=f"case_{model}_"))
    sys.exit(run(target, resolve_openfoam_image() or DEFAULT_IMAGE, model))
