"""V-C3 — pitzDaily geri basamak: yeniden bağlanma uzunluğu (Faz 2.6b).

Resmi pitzDaily ağı (blockMeshDict öğreticiden), case yazıcımız: k-ω SST,
U = 10 m/s, ν = 1e-5 (Re_h ≈ 25 400, h = 25.4 mm), sıkı residual hedefi.
Koşu sonrası ``wallShearStress`` ve yüz merkezleri (``writeCellCentres``)
yazılır; alt duvarda basamaktan sonra (0 < x < 206 mm) τ_x'in son işaret
değişimi yeniden bağlanma noktası x_r. Referans: Pitz & Daily (1983) deneyi
x_r/h ≈ 7.0. Sonuç veri; kabul ölçütü mühendisin.

Kullanım (backend klasöründen):
    .venv/Scripts/python.exe scripts/cfd_validation_pitzdaily.py [hedef_klasör]
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.postprocess.openfoam_fields import patch_vectors, reattachment_x  # noqa: E402
from app.solvers.openfoam import DEFAULT_IMAGE, OpenFoamAdapter, docker_command, resolve_openfoam_image  # noqa: E402

H = 0.0254
X_R_EXP = 7.0  # Pitz & Daily (1983), x_r/h


def run(case_dir: Path, image: str) -> dict:
    case = {
        "nu_m2_s": 1e-5,
        "patches": [
            {"name": "inlet", "kind": "inlet", "velocity_m_s": [10, 0, 0]},
            {"name": "outlet", "kind": "outlet"},
            {"name": "upperWall", "kind": "wall"},
            {"name": "lowerWall", "kind": "wall"},
            {"name": "frontAndBack", "kind": "empty"},
        ],
        "turbulence": {"model": "kOmegaSST", "intensity": 0.05, "length_scale_m": 0.0025},
        "control": {"iterations": 4000, "write_interval": 4000, "residual_p": 1e-5, "residual_u": 1e-6, "residual_turbulence": 1e-6},
    }
    adapter = OpenFoamAdapter()
    art = adapter.build_input({"output_dir": str(case_dir), "case": case})
    subprocess.run(
        docker_command(image, case_dir, "cp $FOAM_TUTORIALS/incompressible/simpleFoam/pitzDaily/system/blockMeshDict system/"),
        check=True, capture_output=True,
    )
    t = time.time()
    handle = adapter.submit(art)
    res = adapter.parse_results(handle)
    solve_s = time.time() - t
    post = (
        "simpleFoam -postProcess -func wallShearStress -latestTime > log.wallShearStress 2>&1 && "
        "postProcess -func writeCellCentres -latestTime > log.cellCentres 2>&1 && "
        "foamListTimes -latestTime"
    )
    out = subprocess.run(docker_command(image, case_dir, post), capture_output=True, text=True)
    latest = out.stdout.strip().splitlines()[-1].strip()
    tdir = case_dir / latest
    shear = patch_vectors((tdir / "wallShearStress").read_text(), "lowerWall")
    centres = patch_vectors((tdir / "C").read_text(), "lowerWall")
    x_r = reattachment_x(centres, shear, 0.001, 0.206)
    return {
        "iterations": res.scalars.get("iterations"),
        "converged": res.scalars.get("converged"),
        "solve_s": round(solve_s, 1),
        "latest_time": latest,
        "lower_wall_faces": len(centres),
        "x_r_m": x_r,
        "x_r_over_h": (x_r / H) if x_r is not None else None,
        "x_r_over_h_experiment": X_R_EXP,
        "diff_percent": (100 * (x_r / H - X_R_EXP) / X_R_EXP) if x_r is not None else None,
    }


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="pitzDaily_vc3_"))
    result = run(target, resolve_openfoam_image() or DEFAULT_IMAGE)
    out = Path("uploads/reports/cfd_validation_pitzdaily.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
