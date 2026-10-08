"""OpenFOAM duman testi (Faz 2.0): resmi pitzDaily vakası simpleFoam ile.

Vaka imajdaki öğretici klasöründen kopyalanır (``$FOAM_TUTORIALS``),
``blockMesh`` + ``simpleFoam`` koşar, log okunur ve özet yazdırılır.

Kullanım (backend klasöründen):
    OPENFOAM_DOCKER_IMAGE=opencfd/openfoam-default:2412 \
        .venv/Scripts/python.exe scripts/openfoam_smoke.py [hedef_klasör]
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
    docker_command,
    parse_solver_log,
    resolve_openfoam_image,
)

SCRIPT = (
    "set -e; cp -r $FOAM_TUTORIALS/incompressible/simpleFoam/pitzDaily/. . && "
    "blockMesh > log.blockMesh 2>&1 && simpleFoam > log.simpleFoam 2>&1"
)


def run(case_dir: Path, image: str) -> int:
    case_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    proc = subprocess.run(docker_command(image, case_dir, SCRIPT), capture_output=True, text=True)
    wall = time.perf_counter() - t0
    log_path = case_dir / "log.simpleFoam"
    if not log_path.is_file():
        print(f"HATA: log yok (çıkış kodu {proc.returncode})\n{proc.stderr[-2000:]}")
        return 1
    log = parse_solver_log(log_path.read_text(errors="replace"))
    print(f"imaj          : {image}")
    print(f"case          : {case_dir}")
    print(f"çıkış kodu    : {proc.returncode}   süre: {wall:.1f} s")
    print(f"iterasyon     : {log.last_iteration}   yakınsadı: {log.converged}   End: {log.finished}")
    for name, values in log.initial_residuals.items():
        print(f"  {name:8s} ilk {values[0]:.3e}  son {values[-1]:.3e}")
    if log.fatal_error:
        print(f"FATAL: {log.fatal_error}")
    return 0 if proc.returncode == 0 and log.finished else 1


if __name__ == "__main__":
    image = resolve_openfoam_image() or DEFAULT_IMAGE
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="pitzDaily_"))
    sys.exit(run(target, image))
