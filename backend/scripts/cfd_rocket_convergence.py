"""Roket ağ yakınsaması (R3): 3 snappy ağı × α 0 / 4° → CN, CD, CNα, x_cp.

Roket şablonu varsayılanı (ogive, D 100 mm, L 1.5 m, 4 kanatçık) → rüzgâr tüneli
(önde 3L, arkada 6L, yanlarda 3L; sınır katmanı yok) → taban / yüzey seviyesi
0.3 m · 2–3, 0.2 m · 3–4, 0.15 m · 4–5 → her ağda 40 m/s, CG 900 mm, simpleFoam
k-ω SST, gevşetme 0.5 / 0.3, residual hedefi p 1e-5 / U 1e-6, 2500 iterasyon,
son 200 iterasyon ortalaması. CNα iki yoldan: eğim (α 0 ve 4°) ve tek nokta (CN/α).
Referans Barrowman (koşu cevabında).

Yerelde 3. ağ (≈ 470 bin hücre) bellek yetmediği için Codespace'te koşulur;
sonuçlar ``docs/CFD_VALIDATION.md`` "Roket ağ yakınsaması" tablosuna işlenir.

Sonuç: ``uploads/reports/cfd_rocket_convergence.json`` ve ekrana tablo.
Değerler veridir; kabul ölçütü mühendisin.

Kullanım (backend klasöründen; Postgres + Docker açık):
    python scripts/cfd_rocket_convergence.py            # 3 ağ
    python scripts/cfd_rocket_convergence.py --only 3   # yalnız 3. ağ
    python scripts/cfd_rocket_convergence.py --procs 4  # paralel çözüm
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

SPEED = 40.0
CG_MM = 900.0
ALPHAS = (0.0, 4.0)
TUNNEL = {"upstream": 3, "downstream": 6, "lateral": 3}
#: (taban hücre m, yüzey seviyesi min, max, STL boyu mm)
LEVELS = [(0.3, 2, 3, 15), (0.2, 3, 4, 8), (0.15, 4, 5, 5)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, choices=(1, 2, 3), help="yalnız bu ağ (1-tabanlı)")
    ap.add_argument("--procs", type=int, default=1, help="çözüm çekirdek sayısı")
    args = ap.parse_args()
    client = TestClient(app)
    gid = client.post("/templates/rocket/create", json={"params": {}}).json()["geometry_id"]
    rows = []
    for i, (base, lmin, lmax, stl) in enumerate(LEVELS, start=1):
        if args.only and i != args.only:
            continue
        t = time.time()
        m = client.post(
            "/cfd/mesh",
            json={
                "geometry_id": gid,
                "mesher": "snappy",
                "wait": True,
                "tunnel": {**TUNNEL, "base_cell_m": base},
                "snappy": {
                    "surface_level_min": lmin,
                    "surface_level_max": lmax,
                    "feature_level": lmax,
                    "wake_level": 0,
                    "n_layers": 0,
                    "stl_size_mm": stl,
                    "max_global_cells": 6_000_000,
                },
            },
        ).json()
        cells = (m.get("check") or {}).get("cells")
        print(f"ağ {i} ({base} m · {lmin}–{lmax}): {m['status']} · {cells} hücre · {time.time() - t:.0f} s", flush=True)
        row: dict = {"mesh": i, "base_cell_m": base, "levels": [lmin, lmax], "cells": cells, "mesh_id": m.get("mesh_id"), "alphas": {}}
        rows.append(row)
        if m["status"] != "meshed":
            row["message"] = m.get("message")
            continue
        for alpha in ALPHAS:
            t = time.time()
            s = client.post(
                "/cfd/rocket/solve",
                json={
                    "mesh_id": m["mesh_id"], "speed_m_s": SPEED, "alpha_deg": alpha, "cg_mm": CG_MM,
                    "iterations": 2500, "average_last": 200, "relax_u": 0.5, "relax_other": 0.3,
                    "residual_p": 1e-5, "residual_u": 1e-6, "n_procs": args.procs, "wait": True,
                    "name": f"Roket ağ yakınsaması · ağ {i} · α {alpha:g}",
                },
            ).json()
            row["barrowman"] = {k: s.get("barrowman", {}).get(k) for k in ("cn_alpha", "x_cp_mm")}
            job = client.get(f"/cfd/jobs/{s['job_id']}").json()
            aero = job.get("rocket_aero") or {}
            row["alphas"][f"{alpha:g}"] = {
                "status": job.get("status"), "message": job.get("message"),
                "CN": aero.get("CN"), "CD": aero.get("CD"), "x_cp_m": aero.get("x_cp_m"),
                "iterations": (job.get("scalars") or {}).get("iterations"), "solve_s": round(time.time() - t, 1),
            }
            print(f"   α {alpha:g}: {job.get('status')} · CN {aero.get('CN')} · CD {aero.get('CD')} · x_cp {aero.get('x_cp_m')} · {time.time() - t:.0f} s", flush=True)
        a0, a4 = row["alphas"].get("0", {}), row["alphas"].get("4", {})
        if a0.get("CN") is not None and a4.get("CN") is not None:
            row["cn_alpha_slope"] = (a4["CN"] - a0["CN"]) / math.radians(4.0)
            row["cn_alpha_single"] = a4["CN"] / math.radians(4.0)
    out = Path("uploads/reports/cfd_rocket_convergence.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"speed_m_s": SPEED, "cg_mm": CG_MM, "tunnel": TUNNEL, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n| Ağ | Hücre | CN α0 | CN α4 | CD α0 | CNα eğim | CNα tek | x_cp α4 (mm) |")
    for r in rows:
        a0, a4 = r["alphas"].get("0", {}), r["alphas"].get("4", {})
        f = lambda v, n=3: "—" if v is None else f"{v:.{n}f}"  # noqa: E731
        xcp = a4.get("x_cp_m")
        print(f"| {r['base_cell_m']} · {r['levels'][0]}–{r['levels'][1]} | {r['cells']} | {f(a0.get('CN'))} | {f(a4.get('CN'))} | "
              f"{f(a0.get('CD'))} | {f(r.get('cn_alpha_slope'), 2)} | {f(r.get('cn_alpha_single'), 2)} | {f(xcp * 1000 if xcp else None, 1)} |")
    print("rapor:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
