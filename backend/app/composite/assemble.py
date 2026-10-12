"""Layup + ply kütüphanesi + rozet → CalculiXAdapter `composite_layup`."""

from __future__ import annotations

from typing import Any


def assemble_composite_layup(
    *,
    part_id: int,
    plies: list[dict[str, Any]],
    materials: dict[int, dict[str, Any]],
    dir0: list[float] | None = None,
) -> dict[str, Any]:
    """`plies[0]` alt. materials[id] = {name, e1…e3, nu12…, g12…, density}."""
    if not plies:
        raise ValueError("En az bir katman gerekli.")
    out: list[dict[str, Any]] = []
    for raw in plies:
        mid = int(raw["material_id"])
        mat = materials.get(mid)
        if mat is None:
            raise ValueError(f"Ply malzemesi bulunamadı: {mid}")
        t = float(raw["thickness_mm"])
        if t <= 0:
            raise ValueError("Katman kalınlığı pozitif olmalı.")
        out.append(
            {
                "name": mat["name"],
                "e1": float(mat["e1"]),
                "e2": float(mat["e2"]),
                "e3": float(mat["e3"]),
                "nu12": float(mat["nu12"]),
                "nu13": float(mat["nu13"]),
                "nu23": float(mat["nu23"]),
                "g12": float(mat["g12"]),
                "g13": float(mat["g13"]),
                "g23": float(mat["g23"]),
                "density": float(mat["density"]),
                "thickness_mm": t,
                "angle_deg": float(raw.get("angle_deg", 0.0)),
            }
        )
    return {
        "part_id": int(part_id),
        "dir0": list(dir0 or [1.0, 0.0, 0.0]),
        "plies": out,
    }


def stack_thickness_mm(layup: dict[str, Any]) -> float:
    return sum(float(p["thickness_mm"]) for p in layup.get("plies") or [])
