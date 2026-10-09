"""V-C4 — Ahmed gövdesi, otomotiv dış akış (Faz 2.6c).

Şablon ``ahmed_body`` (özgün ölçüler, bacaksız) → zeminli rüzgâr tüneli (önde 2L,
arkada 4L, yanlarda / üstte 1.5L; zemin sabit duvar, gövde altı 50 mm) →
snappyHexMesh (sınır tabakalı) → k-ω SST, U = 40 m/s (Re_L ≈ 2.8·10⁶) → Cd
(A_ref = W·H). Referans: Ahmed vd. (1984) deney Cd (60 m/s, bacaklı).
Sonuç veri; kabul ölçütü mühendisin.

Kullanım (backend klasöründen):
    .venv/Scripts/python.exe scripts/cfd_validation_ahmed.py [açı ...]   (varsayılan 25)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.postprocess.ahmed_drag import ahmed_cd_experiment  # noqa: E402

U = 40.0
NU = 1.5e-5
TUNNEL = {"upstream": 2, "downstream": 4, "lateral": 1.5, "ground": True, "ground_clearance_m": 0.05, "base_cell_m": 0.16}
SNAPPY = {
    "surface_level_min": 4, "surface_level_max": 5, "feature_level": 5, "wake_level": 2, "wake_length": 1.0,
    "n_layers": 3, "expansion_ratio": 1.2, "stl_size_mm": 8, "max_global_cells": 3_000_000,
}


def run_angle(client: TestClient, phi: float) -> dict:
    geo = client.post("/templates/ahmed_body/create", json={"params": {"slant_angle_deg": phi}}).json()
    gid = geo["geometry_id"]
    t = time.time()
    m = client.post("/cfd/mesh", json={"geometry_id": gid, "tunnel": TUNNEL, "snappy": SNAPPY, "wait": True}).json()
    check = m.get("check") or {}
    row: dict = {"phi_deg": phi, "mesh_status": m["status"], "cells": check.get("cells"), "mesh_ok": check.get("mesh_ok"),
                 "mesh_s": round(time.time() - t, 1), "layers": (m.get("snappy") or {}).get("layers")}
    print(f"φ {phi}: mesh {m['status']} · {check.get('cells')} hücre · {row['mesh_s']} s · checkMesh {check.get('mesh_ok')}", flush=True)
    if m["status"] != "meshed":
        row["message"] = m.get("message")
        return row
    w, h, length = 0.389, 0.288, 1.044
    case = {
        "nu_m2_s": NU,
        "rho_kg_m3": 1.225,
        "patches": [
            {"name": "inlet", "kind": "inlet", "velocity_m_s": [U, 0, 0]},
            {"name": "outlet", "kind": "outlet"},
            {"name": "sides", "kind": "slip"},
            {"name": "ground", "kind": "wall"},
            {"name": "ahmed", "kind": "wall"},
        ],
        "turbulence": {"model": "kOmegaSST", "intensity": 0.002, "length_scale_m": 0.01},
        "control": {"iterations": 1500, "write_interval": 1500, "residual_p": 1e-4, "residual_u": 1e-5,
                    "residual_turbulence": 1e-5, "relax_u": 0.7, "relax_other": 0.5},
        "forces": {"patches": ["ahmed"], "u_ref_m_s": U, "l_ref_m": length, "a_ref_m2": w * h, "average_last": 200},
    }
    t = time.time()
    s = client.post("/cfd/solve", json={"case": case, "mesh_id": m["mesh_id"], "wait": True, "name": f"V-C4 Ahmed φ{phi}"}).json()
    sc = s.get("scalars") or {}
    exp = ahmed_cd_experiment(phi)
    cd = sc.get("Cd_mean")
    row.update({
        "status": s.get("status"), "message": s.get("message"), "iterations": sc.get("iterations"), "converged": sc.get("converged"),
        "cd": sc.get("Cd"), "cd_mean": cd, "cd_std": sc.get("Cd_std"), "cl_mean": sc.get("Cl_mean"),
        "cd_experiment": exp, "diff_percent": (100 * (cd - exp) / exp) if (cd and exp) else None,
        "solve_s": round(time.time() - t, 1), "run_id": s.get("run_id"),
    })
    print(f"   Cd {cd} (deney {exp}) · {row['iterations']} it · {row['solve_s']} s · {s.get('message')}", flush=True)
    return row


def main() -> int:
    angles = [float(a) for a in sys.argv[1:]] or [25.0]
    client = TestClient(app)
    rows = [run_angle(client, phi) for phi in angles]
    out = Path("uploads/reports/cfd_validation_ahmed.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"u_m_s": U, "nu": NU, "tunnel": TUNNEL, "snappy": SNAPPY, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("rapor:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
