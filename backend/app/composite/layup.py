"""Klasik laminasyon teorisi (CLT): katman dizilimi → ABD.

Birimler (uygulamanın mm / N / MPa sistemiyle aynı):
- E, G: Pa (kütüphane); içeride MPa = N/mm²
- kalınlık: mm
- A: N/mm, B: N, D: N·mm

`plies[0]` alt katman (z = −h/2). Açı: laminat x → lif 1, derece, CCW.
Araç dizilim önermez — matrisleri sayı olarak üretir.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_VOIGT = 3


@dataclass(frozen=True)
class Ply:
    e1: float  # Pa
    e2: float
    g12: float
    nu12: float
    thickness_mm: float
    angle_deg: float


@dataclass(frozen=True)
class ABD:
    """3×3 A, B, D (Voigt Nx, Ny, Nxy / Mx, My, Mxy)."""

    A: np.ndarray  # N/mm
    B: np.ndarray  # N
    D: np.ndarray  # N·mm

    def as_lists(self) -> dict[str, list[list[float]]]:
        return {
            "A_N_per_mm": self.A.tolist(),
            "B_N": self.B.tolist(),
            "D_N_mm": self.D.tolist(),
        }


def reduced_stiffness(e1: float, e2: float, g12: float, nu12: float) -> np.ndarray:
    """Düzlem gerilme Q (Pa), Voigt 11/22/12."""
    if e1 <= 0 or e2 <= 0 or g12 <= 0:
        raise ValueError("E1, E2, G12 pozitif olmalı.")
    nu21 = nu12 * e2 / e1
    denom = 1.0 - nu12 * nu21
    if denom <= 0:
        raise ValueError("1 − ν12 ν21 ≤ 0; ortotrop sabitler uyumsuz.")
    q11 = e1 / denom
    q22 = e2 / denom
    q12 = nu12 * e2 / denom
    q = np.zeros((3, 3), dtype=float)
    q[0, 0] = q11
    q[1, 1] = q22
    q[0, 1] = q[1, 0] = q12
    q[2, 2] = g12
    return q


def transform_q(q: np.ndarray, angle_deg: float) -> np.ndarray:
    """Q → Q̄ (laminat eksenleri). θ lif açısı, derece."""
    m = float(np.cos(np.deg2rad(angle_deg)))
    n = float(np.sin(np.deg2rad(angle_deg)))
    m2, n2 = m * m, n * n
    m4, n4 = m2 * m2, n2 * n2
    m2n2 = m2 * n2
    q11, q22, q12, q66 = q[0, 0], q[1, 1], q[0, 1], q[2, 2]
    qb = np.zeros((3, 3), dtype=float)
    qb[0, 0] = q11 * m4 + 2.0 * (q12 + 2.0 * q66) * m2n2 + q22 * n4
    qb[1, 1] = q11 * n4 + 2.0 * (q12 + 2.0 * q66) * m2n2 + q22 * m4
    qb[0, 1] = qb[1, 0] = (q11 + q22 - 4.0 * q66) * m2n2 + q12 * (n4 + m4)
    qb[0, 2] = qb[2, 0] = (q11 - q12 - 2.0 * q66) * n * m * m2 + (
        q12 - q22 + 2.0 * q66
    ) * n2 * n * m
    qb[1, 2] = qb[2, 1] = (q11 - q12 - 2.0 * q66) * n2 * n * m + (
        q12 - q22 + 2.0 * q66
    ) * n * m * m2
    qb[2, 2] = (q11 + q22 - 2.0 * q12 - 2.0 * q66) * m2n2 + q66 * (n4 + m4)
    return qb


def abd_matrix(plies: list[Ply]) -> ABD:
    """Alt→üst katman listesinden ABD. Kalınlık mm, E Pa."""
    if not plies:
        raise ValueError("En az bir katman gerekli.")
    thicknesses = [float(p.thickness_mm) for p in plies]
    if any(t <= 0 for t in thicknesses):
        raise ValueError("Katman kalınlığı pozitif olmalı.")
    h = sum(thicknesses)
    z = -0.5 * h
    a = np.zeros((_VOIGT, _VOIGT), dtype=float)
    b = np.zeros((_VOIGT, _VOIGT), dtype=float)
    d = np.zeros((_VOIGT, _VOIGT), dtype=float)
    for ply, t in zip(plies, thicknesses):
        z0, z1 = z, z + t
        q_mpa = (
            transform_q(
                reduced_stiffness(ply.e1, ply.e2, ply.g12, ply.nu12),
                ply.angle_deg,
            )
            / 1e6
        )
        dz = z1 - z0
        dz2 = z1 * z1 - z0 * z0
        dz3 = z1**3 - z0**3
        a += q_mpa * dz
        b += 0.5 * q_mpa * dz2
        d += (1.0 / 3.0) * q_mpa * dz3
        z = z1
    a = 0.5 * (a + a.T)
    b = 0.5 * (b + b.T)
    d = 0.5 * (d + d.T)
    return ABD(A=a, B=b, D=d)
