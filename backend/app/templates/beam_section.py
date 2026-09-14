"""Profil kesit ataletleri — Grup 2 ankastre eğilme (mm⁴)."""

from __future__ import annotations


def i_beam_inertia(height: float, flange_width: float, web: float, flange: float) -> float:
    """I_z: eğilme y doğrultusunda (yük −y, kesit yz)."""
    inner_h = height - 2.0 * flange
    inner_b = flange_width - web
    return (flange_width * height**3 - inner_b * inner_h**3) / 12.0


def box_tube_inertia(height: float, width: float, wall: float) -> float:
    hi = height - 2.0 * wall
    wi = width - 2.0 * wall
    return (width * height**3 - wi * hi**3) / 12.0


def circular_tube_inertia(outer_r: float, inner_r: float) -> float:
    """I = π/4 (R⁴ − r⁴)."""
    from math import pi

    return pi / 4.0 * (outer_r**4 - inner_r**4)


def equal_l_angle_inertia_and_c(leg: float, thickness: float) -> tuple[float, float]:
    """Eşit L: I_z (yük −y) ve gerilme için max |y − cy|."""
    a, t = leg, thickness
    a1 = a * t
    y1 = a / 2.0
    a2 = (a - t) * t
    y2 = t / 2.0
    area = a1 + a2
    cy = (a1 * y1 + a2 * y2) / area
    i1 = t * a**3 / 12.0 + a1 * (y1 - cy) ** 2
    i2 = (a - t) * t**3 / 12.0 + a2 * (y2 - cy) ** 2
    c = max(cy, a - cy)
    return i1 + i2, c


def cantilever_fl_over_ei(
    length: float,
    inertia: float,
    c: float,
    force_n: float,
    youngs_modulus_pa: float,
) -> dict[str, float]:
    """δ = FL³/3EI [mm], σ = Mc/I [MPa]. F [N], E [Pa], mm."""
    e_mpa = youngs_modulus_pa / 1e6
    tip = force_n * length**3 / (3.0 * e_mpa * inertia)
    stress = force_n * length * c / inertia
    return {"max_displacement": tip, "max_von_mises": stress}
