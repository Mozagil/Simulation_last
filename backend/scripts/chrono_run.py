#!/usr/bin/env python
"""Chrono worker — Faz 5.0. Ayrı conda env'de ya da Docker'da koşar; FastAPI ortamı bunu import etmez.

Kullanım: python chrono_run.py <case_dir>
Okur: <case_dir>/chrono_case.json  Yazar: results.csv, summary.json
Senaryo quarter_car_bump: 2 serbestlikli çeyrek araç (ChBody + ChLinkTSDA), yol
profili tabana kinematik olarak verilir (ChLinkMotorLinearPosition + ChFunction).
PyChrono yoksa açık hata ile çıkar (sessiz sahte sonuç YOK).
"""
from __future__ import annotations

import csv
import json
import math
import sys
import time
from pathlib import Path


def road_z(kind: str, x: float, h: float, L: float, x0: float) -> float:
    if kind == "step":
        return h if x >= x0 else 0.0
    if x < x0 or x > x0 + L:
        return 0.0
    return 0.5 * h * (1.0 - math.cos(2.0 * math.pi * (x - x0) / L))  # cosine bump


def main(case_dir: Path) -> int:
    case = json.loads((case_dir / "chrono_case.json").read_text(encoding="utf-8"))
    p = case["params"]
    if p["scenario"] != "quarter_car_bump":
        print(f"bilinmeyen senaryo: {p['scenario']}", file=sys.stderr)
        return 2
    try:
        import pychrono as chrono  # type: ignore
    except ImportError:
        print("PyChrono yok: conda create -n chrono -c projectchrono -c conda-forge pychrono", file=sys.stderr)
        return 3

    sys_ = chrono.ChSystemNSC()
    sys_.SetGravitationalAcceleration(chrono.ChVector3d(0, 0, -9.81))

    ground = chrono.ChBody()
    ground.SetFixed(True)
    sys_.Add(ground)

    # Yol: hareketli taban gövdesi; z(t) = yol profili (x = v·t)
    base = chrono.ChBody()
    base.SetMass(1.0)
    sys_.Add(base)
    v = float(p["speed_m_s"])
    rd = p["road"]
    h, L, x0 = rd["height_mm"] / 1000.0, rd["length_m"], rd["start_m"]

    class RoadFn(chrono.ChFunction):
        def GetVal(self, t: float) -> float:  # noqa: N802 (Chrono API)
            return road_z(rd["kind"], v * t, h, L, x0)

    road_fn = RoadFn()
    motor = chrono.ChLinkMotorLinearPosition()
    motor.Initialize(base, ground, chrono.ChFramed(chrono.ChVector3d(0, 0, 0), chrono.QuatFromAngleY(-math.pi / 2)))
    motor.SetMotionFunction(road_fn)
    sys_.Add(motor)

    # Tekerlek (unsprung) ve gövde (sprung) kütleleri; yalnız z serbest (prizmatik)
    k_t, k_s, c_s = float(p["tire_k_n_per_m"]), float(p["suspension_k_n_per_m"]), float(p["suspension_c_n_s_per_m"])
    m_u, m_s = float(p["unsprung_mass_kg"]), float(p["sprung_mass_kg"])
    z_u0 = 0.3
    z_s0 = z_u0 + 0.5
    wheel = chrono.ChBody(); wheel.SetMass(m_u); wheel.SetPos(chrono.ChVector3d(0, 0, z_u0)); sys_.Add(wheel)
    body = chrono.ChBody(); body.SetMass(m_s); body.SetPos(chrono.ChVector3d(0, 0, z_s0)); sys_.Add(body)
    for b in (wheel, body):
        pr = chrono.ChLinkLockPrismatic()
        pr.Initialize(b, ground, chrono.ChFramed(b.GetPos(), chrono.QuatFromAngleY(0)))  # z ekseni
        sys_.Add(pr)

    tire = chrono.ChLinkTSDA()
    tire.Initialize(wheel, base, False, chrono.ChVector3d(0, 0, z_u0), chrono.ChVector3d(0, 0, 0))
    tire.SetRestLength(z_u0 + m_u * 9.81 / k_t + m_s * 9.81 / k_t)
    tire.SetSpringCoefficient(k_t)
    sys_.Add(tire)

    susp = chrono.ChLinkTSDA()
    susp.Initialize(body, wheel, False, chrono.ChVector3d(0, 0, z_s0), chrono.ChVector3d(0, 0, z_u0))
    susp.SetRestLength(0.5 + m_s * 9.81 / k_s)
    susp.SetSpringCoefficient(k_s)
    susp.SetDampingCoefficient(c_s)
    sys_.Add(susp)

    dt, t_end, every = float(p["dt_s"]), float(p["t_end_s"]), int(p["output_every"])
    out = case_dir / case["outputs"]["csv"]
    t0 = time.time()
    n = 0
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["time_s", "road_z_m", "wheel_z_m", "body_z_m", "body_acc_m_s2", "susp_force_n", "susp_deflection_m", "tire_force_n"])
        while sys_.GetChTime() < t_end:
            sys_.DoStepDynamics(dt)
            n += 1
            if n % every == 0:
                t = sys_.GetChTime()
                w.writerow([
                    f"{t:.6f}",
                    f"{base.GetPos().z:.6e}",
                    f"{wheel.GetPos().z - z_u0:.6e}",
                    f"{body.GetPos().z - z_s0:.6e}",
                    f"{body.GetPosDt2().z:.6e}",
                    f"{susp.GetForce():.6e}",
                    f"{susp.GetLength() - susp.GetRestLength():.6e}",
                    f"{tire.GetForce():.6e}",
                ])
    (case_dir / case["outputs"]["summary"]).write_text(json.dumps({
        "chrono_version": getattr(chrono, "__version__", "?"), "steps": n, "wall_s": round(time.time() - t0, 3),
        "dt_s": dt, "t_end_s": t_end,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("kullanım: chrono_run.py <case_dir>", file=sys.stderr)
        sys.exit(1)
    sys.exit(main(Path(sys.argv[1])))
