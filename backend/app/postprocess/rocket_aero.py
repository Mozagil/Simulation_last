"""Roket rüzgâr tüneli sonuçları — Faz 2, R3.

Koşu sonrası kuvvet / moment çıktılarından (``read_forces``) gövde ve rüzgâr
eksenlerinde katsayılar, basınç merkezi ve kararlılık payı. Yalnız veri.

Eksenler: roket ekseni +x (burun ucu x = 0), hücum açısı α x–z düzleminde:
serbest akım U∞ = V·(cos α, 0, sin α). Gövde ekseni: CA = Fx/(q·A),
CN = Fz/(q·A). Rüzgâr ekseni: CD = CA·cos α + CN·sin α,
CL = CN·cos α − CA·sin α. Moment, referans nokta (CG; verilmezse burun ucu)
x_ref etrafında; y bileşeni M_y = −(x_cp − x_ref)·F_z → x_cp = x_ref − M_y/F_z.
Cm = M_y/(q·A·d). α ≈ 0'da F_z ≈ 0 olduğu için x_cp tanımsızdır (None).
CNα (CFD) = CN/α (rad, küçük α) — Barrowman CNα ile aynı tanım.
"""

from __future__ import annotations

import math
from typing import Any

GAMMA_AIR = 1.4
R_AIR = 287.05  # J/(kg·K)


def speed_of_sound(temperature_k: float) -> float:
    return math.sqrt(GAMMA_AIR * R_AIR * temperature_k)


def freestream(speed_m_s: float, alpha_deg: float) -> tuple[float, float, float]:
    a = math.radians(alpha_deg)
    return (speed_m_s * math.cos(a), 0.0, speed_m_s * math.sin(a))


def rocket_aero(
    scalars: dict[str, float],
    *,
    speed_m_s: float,
    alpha_deg: float,
    rho_kg_m3: float,
    diameter_m: float,
    x_ref_m: float,
    cg_given: bool,
) -> dict[str, Any]:
    """Toplam kuvvet (N) / moment (N·m, x_ref'e göre) → katsayılar ve CP."""
    fx = scalars.get("force_total_x")
    fz = scalars.get("force_total_z")
    my = scalars.get("moment_total_y")
    if fx is None or fz is None or my is None:
        return {}
    area = math.pi * diameter_m**2 / 4.0
    q = 0.5 * rho_kg_m3 * speed_m_s**2
    a = math.radians(alpha_deg)
    ca = fx / (q * area)
    cn = fz / (q * area)
    out: dict[str, Any] = {
        "q_pa": q,
        "a_ref_m2": area,
        "CA": ca,
        "CN": cn,
        "CD": ca * math.cos(a) + cn * math.sin(a),
        "CL": cn * math.cos(a) - ca * math.sin(a),
        "Cm": my / (q * area * diameter_m),
        "x_ref_m": x_ref_m,
    }
    if abs(alpha_deg) >= 0.1 and abs(fz) > 1e-12:
        x_cp = x_ref_m - my / fz
        out["x_cp_m"] = x_cp
        out["x_cp_calibers"] = x_cp / diameter_m
        out["CN_alpha_per_rad"] = cn / a
        if cg_given:
            out["stability_calibers"] = (x_cp - x_ref_m) / diameter_m
    return out
