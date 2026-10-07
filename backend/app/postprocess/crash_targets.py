"""Crash vekil model hedefleri — 1.19a.

Bir crash koşusunun (`uploads/crash/<job_id>/job.json` içeriği) skalerleri ve
eğrilerinden ML hedeflerini çıkarır. Saf fonksiyon: DB / dosya erişimi yok.
Birimler kg–mm–ms: kuvvet kN, enerji J, mesafe mm.

Hedef listesi mühendisin; `TARGETS` buradan genişletilir. Hesaplanamayan hedef
(ör. rijit duvarsız senaryoda duvar kuvveti) `None` döner — korpus o satırı
o hedef için boş bırakır, tahmin uydurmaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.postprocess.crash_validation import contact_window, plateau_kn, sled_crush


@dataclass(frozen=True)
class CrashTarget:
    key: str
    label: str
    unit: str
    definition: str


TARGETS: tuple[CrashTarget, ...] = (
    CrashTarget(
        "peak_force_kn", "Tepe duvar kuvveti", "kN",
        "max |F_rwall(t)| (rwall_force_max)",
    ),
    CrashTarget(
        "mean_force_kn", "Ortalama duvar kuvveti", "kN",
        "F_rwall zaman ortalaması, temas penceresi (F > %5 tepe) içinde",
    ),
    CrashTarget(
        "energy_absorbed_j", "Yutulan enerji", "J",
        "iç enerji son değeri (internal_energy_final)",
    ),
    CrashTarget(
        "crush_mm", "Ezilme mesafesi", "mm",
        "∫ v dt, v = v0 − I_rwall(t)/m_model, hız sıfıra inene kadar (rijit duvar; "
        "koşu sonunda hız > 0 ise boş)",
    ),
)

TARGET_KEYS: tuple[str, ...] = tuple(t.key for t in TARGETS)


def _finite(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def crash_targets(job: dict[str, Any]) -> dict[str, float | None]:
    """job.json sözlüğü → {hedef anahtarı: değer | None}."""
    scalars: dict[str, Any] = job.get("scalars") or {}
    curves: dict[str, Any] = job.get("curves") or {}
    out: dict[str, float | None] = {k: None for k in TARGET_KEYS}

    out["peak_force_kn"] = _finite(scalars.get("rwall_force_max"))
    out["energy_absorbed_j"] = _finite(scalars.get("internal_energy_final"))

    time = curves.get("time") or []
    force = curves.get("rwall_force") or []
    if len(time) >= 2 and len(force) == len(time):
        t0, t1 = contact_window(time, force)
        if t1 > t0:
            out["mean_force_kn"] = _finite(plateau_kn(time, [abs(f) for f in force], t0, t1))

    impulse = curves.get("rwall_impulse") or []
    mass = _finite(scalars.get("mass_model"))
    v0 = _finite((job.get("barrier") or {}).get("speed_m_s"))
    if (
        job.get("use_rigid_wall")
        and len(time) >= 2
        and len(impulse) == len(time)
        and mass and mass > 0
        and v0 and v0 > 0
        # Koşu durmadan bittiyse (t_end kısa) δ ezilme değil, o ana kadarki
        # yol olurdu — hedef boş kalır.
        and any(v0 - i / mass <= 0.0 for i in impulse)
    ):
        out["crush_mm"] = _finite(sled_crush(time, impulse, mass, v0)["crush_mm"])

    return out
