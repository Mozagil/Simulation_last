"""Faz 5.1 V-M1: çeyrek araç tümsek geçişi — Chrono worker vs bağımsız ODE çözümü.

Referans: 2 serbestlikli lineer çeyrek araç, statik denge etrafında
(yerçekimi denge ile sadeleşir), scipy `solve_ivp` (Radau, sıkı tolerans):

    m_s z_s'' = −k_s (z_s − z_u) − c_s (z_s' − z_u')
    m_u z_u'' =  k_s (z_s − z_u) + c_s (z_s' − z_u') − k_t (z_u − r(t))

r(t) = yol profili (x = v·t), worker'daki `road_z` ile aynı. Chrono modeli
aynı yapıyı ChBody + ChLinkTSDA + ChLinkMotorLinearPosition ile kurar;
karşılaştırma iki bağımsız çözüm arasındadır (öneri / eşik yok).

Kullanım (Chrono yapılandırılmışsa, CHRONO_DOCKER_IMAGE ya da CHRONO_PYTHON):
    python -m scripts.mbd_validation_qc
Yazar: uploads/reports/mbd_validation_qc.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

from app.solvers.chrono import ChronoAdapter, ChronoQuarterCarParams
from scripts.chrono_run import road_z

REPORT = Path("uploads") / "reports" / "mbd_validation_qc.json"

#: Karşılaştırılan sütunlar: Chrono CSV adı → referans dizisi anahtarı
COMPARED = ("body_z_m", "wheel_z_m", "body_acc_m_s2")


def quarter_car_reference(params: dict[str, Any], t: np.ndarray) -> dict[str, np.ndarray]:
    """Verilen zaman noktalarında z_s, z_u (dengeden) ve z_s'' (m, m/s²)."""
    p = ChronoQuarterCarParams.model_validate(params)
    ms, mu = p.sprung_mass_kg, p.unsprung_mass_kg
    ks, cs, kt = p.suspension_k_n_per_m, p.suspension_c_n_s_per_m, p.tire_k_n_per_m
    v, rd = p.speed_m_s, p.road
    h = rd.height_mm / 1000.0

    def road(tt: float) -> float:
        return road_z(rd.kind, v * tt, h, rd.length_m, rd.start_m)

    def rhs(tt: float, y: np.ndarray) -> list[float]:
        zs, vs, zu, vu = y
        fs = ks * (zs - zu) + cs * (vs - vu)
        return [vs, -fs / ms, vu, (fs - kt * (zu - road(tt))) / mu]

    # Tümsek başlangıç/bitişi süreksiz türev → adım sınırı
    sol = solve_ivp(rhs, (0.0, float(t[-1])), [0.0, 0.0, 0.0, 0.0], method="Radau",
                    t_eval=t, rtol=1e-9, atol=1e-12, max_step=min(p.dt_s, 1e-3))
    zs, vs, zu, vu = sol.y
    acc = np.array([rhs(tt, y)[1] for tt, y in zip(sol.t, sol.y.T)])
    return {"body_z_m": zs, "wheel_z_m": zu, "body_acc_m_s2": acc}


def compare(curves: dict[str, list[float]], params: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Her sütun için tepe (|maks|) farkı ve RMS hata / referans tepe (%)."""
    t = np.asarray(curves["time"], dtype=float)
    ref = quarter_car_reference(params, t)
    out: dict[str, dict[str, float]] = {}
    for key in COMPARED:
        sim = np.asarray(curves[key], dtype=float)
        r = ref[key]
        peak_ref = float(np.max(np.abs(r)))
        peak_sim = float(np.max(np.abs(sim)))
        out[key] = {
            "peak_ref": peak_ref,
            "peak_chrono": peak_sim,
            "peak_diff_pct": 100.0 * (peak_sim - peak_ref) / peak_ref,
            "rms_err_pct_of_peak": 100.0 * float(np.sqrt(np.mean((sim - r) ** 2))) / peak_ref,
        }
    return out


CASES: dict[str, dict[str, Any]] = {
    "bump_10ms": {"t_end_s": 3.0, "dt_s": 1e-3, "speed_m_s": 10.0},
    "bump_20ms_dt5e-4": {"t_end_s": 2.0, "dt_s": 5e-4, "speed_m_s": 20.0},
}


def main() -> int:
    adapter = ChronoAdapter()
    report: dict[str, Any] = {}
    for name, params in CASES.items():
        job = adapter.submit(adapter.build_input({**params, "job_id": f"vm1_{name}"}))
        status = adapter.poll_status(job)
        if status.state != "done":
            print(name, "başarısız:", status.message, file=sys.stderr)
            return 1
        rs = adapter.parse_results(job)
        report[name] = {"params": params, "summary": rs.diagnostics.get("summary"),
                        "compare": compare(rs.curves, params)}
        print(name, json.dumps(report[name]["compare"], indent=1))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
