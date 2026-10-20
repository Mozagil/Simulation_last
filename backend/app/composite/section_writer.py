"""CalculiX kompozit kesit kartları (Faz 3.8).

Yalnız `*ELASTIC, TYPE=ENGINEERING CONSTANTS` + `*ORIENTATION` +
`*SHELL SECTION, COMPOSITE`. Yeni solver değil. Birimler: E/G Pa → MPa,
ρ kg/m³ → tonne/mm³, t mm. `plies[0]` alt katman.

Araç dizilim veya nint önermez — verilen sayıları yazar.
"""

from __future__ import annotations

import math
from typing import Any


def _sanitize_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:64] or "MAT"


def _unit3(vec: list[float] | tuple[float, ...]) -> tuple[float, float, float]:
    x, y, z = float(vec[0]), float(vec[1]), float(vec[2])
    n = math.sqrt(x * x + y * y + z * z)
    if n <= 0:
        raise ValueError("dir0 sıfır olamaz.")
    return (x / n, y / n, z / n)


def _companion(dir0: tuple[float, float, float]) -> tuple[float, float, float]:
    """Yerel xy düzleminde dir0'a paralel olmayan ikinci vektör."""
    dx, dy, dz = dir0
    if abs(dx) <= abs(dy) and abs(dx) <= abs(dz):
        return (1.0, 0.0, 0.0)
    if abs(dy) <= abs(dz):
        return (0.0, 1.0, 0.0)
    return (0.0, 0.0, 1.0)


def _fmt(v: float) -> str:
    return f"{float(v):.6g}"


def write_composite_section(spec: dict[str, Any]) -> str:
    """Tek parça kesiti: malzemeler + rozet + COMPOSITE satırları."""
    plies = list(spec.get("plies") or [])
    if not plies:
        raise ValueError("En az bir katman gerekli.")
    part_id = int(spec.get("part_id", 0))
    elset = _elset(spec)
    or_name = _sanitize_name(str(spec.get("orientation_name") or f"OR_{part_id}"))
    dir0 = _unit3(spec.get("dir0") or [1.0, 0.0, 0.0])
    nint = int(spec.get("nint") or 3)
    if nint < 1:
        raise ValueError("nint pozitif olmalı.")

    lines: list[str] = []
    seen: set[str] = set()
    for ply in plies:
        t = float(ply["thickness_mm"])
        if t <= 0:
            raise ValueError("Katman kalınlığı pozitif olmalı.")
        mname = _sanitize_name(str(ply["name"]))
        if mname in seen:
            continue
        e1 = float(ply["e1"]) / 1e6
        e2 = float(ply["e2"]) / 1e6
        e3 = float(ply["e3"]) / 1e6
        g12 = float(ply["g12"]) / 1e6
        g13 = float(ply["g13"]) / 1e6
        g23 = float(ply["g23"]) / 1e6
        nu12 = float(ply["nu12"])
        nu13 = float(ply["nu13"])
        nu23 = float(ply["nu23"])
        rho = float(ply["density"]) * 1e-12
        lines.append(f"*MATERIAL, NAME={mname}")
        lines.append("*ELASTIC, TYPE=ENGINEERING CONSTANTS")
        lines.append(
            f"{_fmt(e1)}, {_fmt(e2)}, {_fmt(e3)}, {_fmt(nu12)}, "
            f"{_fmt(nu13)}, {_fmt(nu23)}, {_fmt(g12)}, {_fmt(g13)},"
        )
        lines.append(f"{_fmt(g23)}")
        lines.append("*DENSITY")
        lines.append(f"{rho:.6e}")
        seen.add(mname)

    # ccx COMPOSITE satırının 4. alanı açı değil, *ORIENTATION ADI (sayı
    # yazılırsa "nonexistent orientation" ile durur — V-P1'de bulundu).
    # Her farklı ply açısı için rozet + yerel 3 ekseni etrafında ek dönme.
    bx, by, bz = _companion(dir0)
    base = (
        f"{_fmt(dir0[0])}, {_fmt(dir0[1])}, {_fmt(dir0[2])}, "
        f"{_fmt(bx)}, {_fmt(by)}, {_fmt(bz)}"
    )
    ply_or: dict[float, str] = {}
    for ply in plies:
        ang = float(ply.get("angle_deg", 0.0))
        if ang in ply_or:
            continue
        name = f"{or_name}_{len(ply_or)}"
        ply_or[ang] = name
        lines.append(f"*ORIENTATION, NAME={name}, SYSTEM=RECTANGULAR")
        lines.append(base)
        lines.append(f"3, {_fmt(ang)}")
    lines.append(f"*SHELL SECTION, ELSET={elset}, COMPOSITE")
    for ply in plies:
        mname = _sanitize_name(str(ply["name"]))
        t = float(ply["thickness_mm"])
        ang = float(ply.get("angle_deg", 0.0))
        lines.append(f"{_fmt(t)}, {nint}, {mname}, {ply_or[ang]}")
    return "\n".join(lines) + "\n"


def _sections(layup: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(layup, list):
        sections = layup
    elif isinstance(layup, dict) and isinstance(layup.get("sections"), list):
        sections = layup["sections"]
    else:
        sections = [layup]
    if not sections:
        raise ValueError("En az bir kesit gerekli.")
    return sections


def _elset(spec: dict[str, Any]) -> str:
    return str(spec.get("elset") or f"PART_{int(spec.get('part_id', 0))}")


def write_composite_inp(layup: dict[str, Any] | list[dict[str, Any]]) -> str:
    """`params['composite_layup']`: tek kesit dict veya kesit listesi."""
    return "".join(write_composite_section(s) for s in _sections(layup))


def composite_plies_by_elset(
    layup: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, int]:
    """Kesit ELSET adı → katman sayısı (3.11 katman gerilmesi okuması için)."""
    return {_elset(s): len(s.get("plies") or []) for s in _sections(layup)}
