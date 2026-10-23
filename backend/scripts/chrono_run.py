#!/usr/bin/env python
"""Chrono worker — Faz 5.0. Ayrı conda env'de ya da Docker'da koşar; FastAPI ortamı bunu import etmez.

Kullanım: python chrono_run.py <case_dir>
Okur: <case_dir>/chrono_case.json  Yazar: results.csv, summary.json
Senaryolar:
  quarter_car_bump — 2 serbestlikli çeyrek araç (ChBody + ChLinkTSDA), yol
    profili tabana kinematik olarak verilir (ChLinkMotorLinearPosition).
  suspension_test_rig — düzlemsel çift salıncak (dört çubuk). Alt kol açısı
    sinüs motoruyla verilir; mafsal tepkileri dünya çerçevesinde yazılır.
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


def _world_force(link, frame):
    """GetReaction2 kuvveti mafsal çerçevesindedir; dünya bileşenlerine çevir."""
    w = link.GetReaction2()
    f = frame.TransformDirectionLocalToParent(w.force)
    return f.x, f.y, f.z


def run_suspension_rig(case_dir: Path, case: dict, chrono) -> int:
    """Düzlemsel çift salıncak. Mafsal ekseni: çerçeve Z → dünya −Y (X etrafında +90°).

    Şasi sabit. Alt kol–şasi mafsalının yerinde dönme motoru var (açı sinüs).
    Üç döner mafsal döngüyü kapatır. Yay, şasi ile alt kol arasında; serbest boy
    tasarım boyudur. Kuvvetler ikinci gövdeye etkiyen tepkinin dünya bileşenleri.
    """
    p = case["params"]
    sys_ = chrono.ChSystemNSC()
    sys_.SetGravitationalAcceleration(chrono.ChVector3d(0, 0, -9.81))
    ground = chrono.ChBody()
    ground.SetFixed(True)
    sys_.Add(ground)

    axis = chrono.QuatFromAngleX(math.pi / 2)
    pivot_l = chrono.ChVector3d(0.0, 0.0, 0.30)
    pivot_u = chrono.ChVector3d(0.02, 0.0, 0.55)
    outer_l = chrono.ChVector3d(0.40, 0.0, 0.30)
    outer_u = chrono.ChVector3d(0.40, 0.0, 0.55)

    def body(mass: float, pos: chrono.ChVector3d):
        b = chrono.ChBody()
        b.SetMass(mass)
        b.SetInertiaXX(chrono.ChVector3d(0.05, 0.05, 0.05))
        b.SetPos(pos)
        sys_.Add(b)
        return b

    lower = body(float(p["lower_arm_mass_kg"]), chrono.ChVector3d(0.20, 0.0, 0.30))
    upper = body(float(p["upper_arm_mass_kg"]), chrono.ChVector3d(0.21, 0.0, 0.55))
    upright = body(float(p["upright_mass_kg"]), chrono.ChVector3d(0.40, 0.0, 0.425))

    def revolute(a, b, pos):
        frame = chrono.ChFramed(pos, axis)
        j = chrono.ChLinkLockRevolute()
        j.Initialize(a, b, frame)
        sys_.Add(j)
        return j, frame

    motor_frame = chrono.ChFramed(pivot_l, axis)
    motor = chrono.ChLinkMotorRotationAngle()
    motor.Initialize(lower, ground, motor_frame)
    angle_fn = chrono.ChFunctionSine(float(p["angle_amp_rad"]), float(p["angle_freq_hz"]))
    motor.SetAngleFunction(angle_fn)
    sys_.Add(motor)

    upper_chassis, upper_chassis_frame = revolute(upper, ground, pivot_u)
    lower_outer, lower_outer_frame = revolute(upright, lower, outer_l)
    upper_outer, upper_outer_frame = revolute(upright, upper, outer_u)

    mount = chrono.ChVector3d(0.10, 0.0, 0.70)
    on_arm = chrono.ChVector3d(0.28, 0.0, 0.30)
    spring = chrono.ChLinkTSDA()
    spring.Initialize(ground, lower, False, mount, on_arm)
    spring.SetRestLength(math.hypot(0.28 - 0.10, 0.30 - 0.70))
    spring.SetSpringCoefficient(float(p["spring_k_n_per_m"]))
    spring.SetDampingCoefficient(float(p["spring_c_n_s_per_m"]))
    sys_.Add(spring)

    dt, t_end, every = float(p["dt_s"]), float(p["t_end_s"]), int(p["output_every"])
    out = case_dir / case["outputs"]["csv"]
    t0 = time.time()
    n = 0
    header = [
        "time_s", "arm_angle_rad", "spindle_z_m", "spring_force_n", "spring_defl_m",
        "upper_chassis_fx_n", "upper_chassis_fy_n", "upper_chassis_fz_n",
        "lower_outer_fx_n", "lower_outer_fy_n", "lower_outer_fz_n",
        "upper_outer_fx_n", "upper_outer_fy_n", "upper_outer_fz_n",
        "motor_torque_nm",
    ]
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        while sys_.GetChTime() < t_end:
            sys_.DoStepDynamics(dt)
            n += 1
            if n % every == 0:
                t = sys_.GetChTime()
                uc = _world_force(upper_chassis, upper_chassis_frame)
                lo = _world_force(lower_outer, lower_outer_frame)
                uo = _world_force(upper_outer, upper_outer_frame)
                w.writerow([
                    f"{t:.6f}",
                    f"{angle_fn.GetVal(t):.6e}",
                    f"{upright.GetPos().z:.6e}",
                    f"{spring.GetForce():.6e}",
                    f"{spring.GetLength() - spring.GetRestLength():.6e}",
                    f"{uc[0]:.6e}", f"{uc[1]:.6e}", f"{uc[2]:.6e}",
                    f"{lo[0]:.6e}", f"{lo[1]:.6e}", f"{lo[2]:.6e}",
                    f"{uo[0]:.6e}", f"{uo[1]:.6e}", f"{uo[2]:.6e}",
                    f"{motor.GetReaction2().torque.z:.6e}",
                ])
    (case_dir / case["outputs"]["summary"]).write_text(json.dumps({
        "scenario": "suspension_test_rig",
        "chrono_version": getattr(chrono, "__version__", "?"),
        "steps": n, "wall_s": round(time.time() - t0, 3),
        "dt_s": dt, "t_end_s": t_end,
        "joint_force_frame": "world",
        "joint_force_on": "second body of the link",
        "motor_axis": "link Z = world -Y",
    }, indent=2), encoding="utf-8")
    return 0


def run_quarter_car(case_dir: Path, case: dict, chrono) -> int:
    p = case["params"]
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
    # Motor ekseni çerçevenin Z'si. Birim döndürme = dünya Z (yol yüksekliği).
    # Y etrafında -90° ekseni dünya X'e yatırıyordu; düşey tepki ~10 kat küçük kalıyordu.
    motor.Initialize(base, ground, chrono.ChFramed(chrono.ChVector3d(0, 0, 0), chrono.QuatFromAngleY(0)))
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


def main(case_dir: Path) -> int:
    case = json.loads((case_dir / "chrono_case.json").read_text(encoding="utf-8"))
    scenario = case["params"].get("scenario")
    if scenario not in ("quarter_car_bump", "suspension_test_rig"):
        print(f"bilinmeyen senaryo: {scenario}", file=sys.stderr)
        return 2
    try:
        import pychrono as chrono  # type: ignore
    except ImportError:
        print("PyChrono yok: conda create -n chrono -c projectchrono -c conda-forge pychrono", file=sys.stderr)
        return 3
    if scenario == "quarter_car_bump":
        return run_quarter_car(case_dir, case, chrono)
    return run_suspension_rig(case_dir, case, chrono)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("kullanım: chrono_run.py <case_dir>", file=sys.stderr)
        sys.exit(1)
    sys.exit(main(Path(sys.argv[1])))
