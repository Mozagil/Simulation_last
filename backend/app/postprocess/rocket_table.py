"""Roket aerodinamik tablosu — R5.

Mach × α taramasının nokta sonuçlarından (her biri bir R3 koşusu) Mach başına
özet: CD(α = en küçük |α|), CNα (CN–α doğrusal en küçük kareler eğimi, α
radyan; tek α'da CN/α), x_cp ortalaması. Uçuş simülasyonu araçlarına girdi
olarak CSV. Yalnız veri; eğri uydurma / ara değerleme yok.
"""

from __future__ import annotations

import csv
import io
import math
from typing import Any

POINT_COLUMNS = ["mach", "alpha_deg", "speed_m_s", "status", "CA", "CN", "CD", "CL", "Cm", "x_cp_m", "stability_calibers", "job_id"]
TABLE_COLUMNS = ["mach", "n_points", "CD_alpha_min", "alpha_min_deg", "CN_alpha_per_rad", "x_cp_m_mean"]


def _slope(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n == 0:
        return None
    if n == 1:
        return ys[0] / xs[0] if xs[0] != 0 else None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def aero_table(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Başarılı noktalar (CN, CD sayısal) → Mach başına satır (Mach artan)."""
    by_mach: dict[float, list[dict[str, Any]]] = {}
    for p in points:
        if isinstance(p.get("CN"), (int, float)) and isinstance(p.get("CD"), (int, float)):
            by_mach.setdefault(round(float(p["mach"]), 6), []).append(p)
    rows = []
    for m in sorted(by_mach):
        pts = sorted(by_mach[m], key=lambda p: p["alpha_deg"])
        p0 = min(pts, key=lambda p: abs(p["alpha_deg"]))
        xcp = [p["x_cp_m"] for p in pts if isinstance(p.get("x_cp_m"), (int, float)) and p["alpha_deg"] != 0]
        rows.append({
            "mach": m,
            "n_points": len(pts),
            "CD_alpha_min": p0["CD"],
            "alpha_min_deg": p0["alpha_deg"],
            "CN_alpha_per_rad": _slope([math.radians(p["alpha_deg"]) for p in pts], [p["CN"] for p in pts]),
            "x_cp_m_mean": sum(xcp) / len(xcp) if xcp else None,
        })
    return rows


def to_csv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})
    return buf.getvalue()
