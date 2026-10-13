"""V-C2 — küre doğrulaması (Faz 2.6a): düşük Re laminer, ağ yakınsaması, snappy vs cfMesh.

Küre şablonundan (D = 100 mm) geometri → rüzgâr tüneli (önde 5D, arkada 10D,
yanlarda 5D; taban 50 mm, sınır tabakası yok) → snappyHexMesh yüzey seviyesi
2 / 3 / 4 ve cfMesh (seviye 3 karşılığı) → her ağda Re 20 / 40 / 100
(U = 1 m/s, ν = U·D/Re) laminer simpleFoam → Cd, referanslar Schiller–Naumann ve
Clift–Grace–Weber standart sürükleme eğrisi.

Sonuç: ``uploads/reports/cfd_validation_sphere.json`` ve ekrana tablo.
Değerler veridir; kabul ölçütü mühendisin.

Kullanım (backend klasöründen; OPENFOAM_DOCKER_IMAGE cfMesh'li imaj olmalı):
    .venv/Scripts/python.exe scripts/cfd_validation_sphere.py
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.postprocess.sphere_drag import clift_grace_weber, schiller_naumann  # noqa: E402

D = 0.1
U = 1.0
RES = (20, 40, 100)
TUNNEL = {"upstream": 5, "downstream": 10, "lateral": 5, "base_cell_m": 0.05}
MESHES = [
    ("snappy", 2),
    ("snappy", 3),
    ("snappy", 4),
    ("cfmesh", 3),
]


def main() -> int:
    client = TestClient(app)
    gid = client.post("/templates/cfd_sphere/create", json={"params": {"diameter": D * 1000}}).json()["geometry_id"]
    rows = []
    for mesher, level in MESHES:
        t = time.time()
        m = client.post(
            "/cfd/mesh",
            json={
                "geometry_id": gid,
                "mesher": mesher,
                "tunnel": TUNNEL,
                "snappy": {
                    "surface_level_min": level,
                    "surface_level_max": level,
                    "feature_level": level,
                    "wake_level": max(level - 2, 0),
                    "wake_length": 3.0,
                    "n_layers": 0,
                    "stl_size_mm": 2.0,
                },
                "wait": True,
            },
        ).json()
        mesh_s = time.time() - t
        check = m.get("check") or {}
        print(f"{mesher} seviye {level}: {m['status']} · {check.get('cells')} hücre · {mesh_s:.0f} s · checkMesh {check.get('mesh_ok')}", flush=True)
        if m["status"] != "meshed":
            rows.append({"mesher": mesher, "level": level, "status": m["status"], "message": m.get("message")})
            continue
        for re in RES:
            nu = U * D / re
            case = {
                "nu_m2_s": nu,
                "patches": [
                    {"name": "inlet", "kind": "inlet", "velocity_m_s": [U, 0, 0]},
                    {"name": "outlet", "kind": "outlet"},
                    {"name": "sides", "kind": "slip"},
                    {"name": "kure", "kind": "wall"},
                ],
                "control": {"iterations": 3000, "write_interval": 3000, "residual_p": 1e-5, "residual_u": 1e-6,
                            "relax_u": 0.7, "relax_other": 0.3},
                "forces": {"patches": ["kure"], "u_ref_m_s": U, "l_ref_m": D, "a_ref_m2": math.pi * D * D / 4, "average_last": 100},
            }
            t = time.time()
            s = client.post("/cfd/solve", json={"case": case, "mesh_id": m["mesh_id"], "wait": True,
                                                "name": f"V-C2 küre Re {re} · {mesher} s{level}"}).json()
            sc = s.get("scalars") or {}
            ref = schiller_naumann(re)
            cd = sc.get("Cd_mean")
            row = {
                "mesher": mesher, "level": level, "cells": check.get("cells"), "re": re, "status": s.get("status"),
                "iterations": sc.get("iterations"), "converged": sc.get("converged"), "cd": sc.get("Cd"), "cd_mean": cd,
                "cd_std": sc.get("Cd_std"), "cd_ref": ref, "diff_percent": (100 * (cd - ref) / ref) if cd else None,
                "cd_ref_cgw": clift_grace_weber(re),
                "diff_cgw_percent": (100 * (cd - clift_grace_weber(re)) / clift_grace_weber(re)) if cd else None,
                "solve_s": round(time.time() - t, 1), "run_id": s.get("run_id"),
            }
            rows.append(row)
            print(f"   Re {re}: Cd {cd if cd is None else round(cd, 4)} (ref {ref:.3f}, fark {row['diff_percent'] if cd is None else round(row['diff_percent'], 1)} %) · {row['iterations']} it · {row['solve_s']} s", flush=True)
    out = Path("uploads/reports/cfd_validation_sphere.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"diameter_m": D, "u_m_s": U, "tunnel": TUNNEL, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("rapor:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
