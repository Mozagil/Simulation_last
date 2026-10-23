"""CLT analitik referansları — Faz 3.10 (V-P1).

- Zar (membran): serbest laminatta orta düzlem şekil değiştirmesi
      [ε0; κ] = ABD⁻¹ · [N; M]
- Navier: dört kenarı basit mesnetli, özel ortotrop (B = 0, D16 = D26 = 0)
  dikdörtgen plaka, düzgün yayılı basınç q (Reddy, "Mechanics of Laminated
  Composite Plates and Shells", 2. baskı, §5.2):
      w(x, y) = Σ_{m,n tek} 16 q / (π⁶ m n) · sin(mπx/a) sin(nπy/b) / d_mn
      d_mn = D11 (m/a)⁴ + 2 (D12 + 2 D66) (m/a)²(n/b)² + D22 (n/b)⁴
  Kayma şekil değiştirmesi yok (ince plaka varsayımı).

- Katman gerilmesi (3.11): σ̄ = Q̄ (ε0 + z κ) → ply eksenleri.

Birimler: A N/mm, B N, D N·mm, N N/mm, M N, q MPa, a/b mm → w mm, σ MPa.
Yalnız referans veri; ccx ile karşılaştırma doğrulama raporunda.
"""

from __future__ import annotations

import math

import numpy as np

from app.composite.layup import ABD, Ply, reduced_stiffness, transform_q


def midplane_response(
    abd: ABD,
    n: tuple[float, float, float] = (0.0, 0.0, 0.0),
    m: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict[str, list[float]]:
    """[Nx, Ny, Nxy] (N/mm), [Mx, My, Mxy] (N) → ε0 (γ mühendislik), κ (1/mm)."""
    full = np.block([[abd.A, abd.B], [abd.B, abd.D]])
    sol = np.linalg.solve(full, np.array([*n, *m], dtype=float))
    return {"eps0": sol[:3].tolist(), "kappa": sol[3:].tolist()}


def navier_deflection(
    abd: ABD,
    a_mm: float,
    b_mm: float,
    q_mpa: float,
    x_mm: float | None = None,
    y_mm: float | None = None,
    terms: int = 99,
) -> float:
    """SS özel ortotrop plaka sehimi (mm); varsayılan nokta merkez."""
    if a_mm <= 0 or b_mm <= 0:
        raise ValueError("Plaka kenarları pozitif olmalı.")
    if terms < 1:
        raise ValueError("terms pozitif olmalı.")
    x = 0.5 * a_mm if x_mm is None else float(x_mm)
    y = 0.5 * b_mm if y_mm is None else float(y_mm)
    d = abd.D
    d11, d12, d22, d66 = d[0, 0], d[0, 1], d[1, 1], d[2, 2]
    w = 0.0
    for mi in range(1, terms + 1, 2):
        am = mi / a_mm
        sx = math.sin(mi * math.pi * x / a_mm)
        for ni in range(1, terms + 1, 2):
            bn = ni / b_mm
            dmn = d11 * am**4 + 2.0 * (d12 + 2.0 * d66) * am**2 * bn**2 + d22 * bn**4
            w += sx * math.sin(ni * math.pi * y / b_mm) / (mi * ni * dmn)
    return 16.0 * q_mpa / math.pi**6 * w


def ply_stresses(
    plies: list[Ply],
    eps0: list[float],
    kappa: list[float] | None = None,
) -> list[list[float]]:
    """Katman orta düzleminde ply eksenli [σ1, σ2, τ12] (MPa), alt → üst.

    σ̄ = Q̄ (ε0 + z κ), sonra laminat → ply dönüşümü (θ, CCW).
    """
    k = np.zeros(3) if kappa is None else np.asarray(kappa, dtype=float)
    e0 = np.asarray(eps0, dtype=float)
    h = sum(p.thickness_mm for p in plies)
    z = -0.5 * h
    out: list[list[float]] = []
    for p in plies:
        zm = z + 0.5 * p.thickness_mm
        z += p.thickness_mm
        q = transform_q(reduced_stiffness(p.e1, p.e2, p.g12, p.nu12), p.angle_deg) / 1e6
        sx, sy, txy = q @ (e0 + zm * k)
        c = math.cos(math.radians(p.angle_deg))
        s = math.sin(math.radians(p.angle_deg))
        out.append(
            [
                c * c * sx + s * s * sy + 2 * c * s * txy,
                s * s * sx + c * c * sy - 2 * c * s * txy,
                -c * s * sx + c * s * sy + (c * c - s * s) * txy,
            ]
        )
    return out
