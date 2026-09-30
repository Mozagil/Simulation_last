"""Plastisite: malzeme kütüphanesinden `*PLASTIC` tablosu (Faz 0.6.4).

Kütüphanede akma (Re), çekme dayanımı (Rm) ve kopma uzaması (A%) var; tam
gerilme–şekil değiştirme eğrisi yok. Buradan **iki noktalı izotropik
pekleşme** türetilir:

    (σ_y, ε_p = 0)                         akma
    (σ_u,true, ε_p,true)                   Rm noktası, gerçek gerilme/şekil değ.

CalculiX `*PLASTIC` GERÇEK (Cauchy) gerilme ve gerçek plastik şekil
değiştirme ister; mühendislik değerlerinden dönüşüm:
    σ_true = σ_eng · (1 + ε_eng),   ε_true = ln(1 + ε_eng),   ε_p = ε_true − σ_true/E

KABUL (belgeli, karar mühendisin): Rm'nin **tekdüze uzama** noktasında
olduğu varsayılır ve kütüphanedeki A% (kopma uzaması) tekdüze uzama yerine
kullanılır — gerçekte tekdüze uzama A%'den küçüktür (boyun verme), yani
pekleşme eğimi biraz DÜŞÜK tahmin edilir. Tabloyu açıkça veren
(`plastic_curve`) bu kabulü atlar. Tablo son noktadan sonra CalculiX'te
sabit gerilmeyle (mükemmel plastik) devam eder.

A% yoksa: tek nokta (σ_y, 0) → mükemmel plastik (pekleşme yok).
"""

from __future__ import annotations

import math
from typing import Any

#: A% verilmediğinde tekdüze uzama yerine kullanılacak değer YOK — mükemmel
#: plastik yazılır. Sessiz bir varsayılan (örn. %15) yanlış pekleşme uydururdu.


def bilinear_plastic_curve(
    yield_pa: float,
    ultimate_pa: float | None,
    elongation_pct: float | None,
    youngs_pa: float,
) -> list[tuple[float, float]]:
    """[(σ_true_MPa, ε_plastic_true)] — CalculiX `*PLASTIC` satırları.

    `yield_pa` ≤ 0 ise plastisite tanımsız → boş liste (kart yazılmaz).
    """
    if yield_pa is None or yield_pa <= 0:
        return []
    sy = float(yield_pa) / 1e6
    e_mpa = float(youngs_pa) / 1e6
    rows: list[tuple[float, float]] = [(sy, 0.0)]
    if ultimate_pa and elongation_pct and float(ultimate_pa) > yield_pa and float(elongation_pct) > 0:
        su_eng = float(ultimate_pa) / 1e6
        eps_eng = float(elongation_pct) / 100.0
        su_true = su_eng * (1.0 + eps_eng)
        eps_true = math.log1p(eps_eng)
        eps_p = eps_true - su_true / e_mpa
        if eps_p > 1e-6 and su_true > sy:
            rows.append((su_true, eps_p))
    return rows


def plastic_table_for_material(m: dict[str, Any]) -> list[tuple[float, float]]:
    """Malzeme sözlüğünden (snapshot ya da ORM alanları) `*PLASTIC` tablosu.

    Açık `plastic_curve` ([[σ_true_MPa, ε_p], …]) varsa o kullanılır; yoksa
    Re/Rm/A%'den iki noktalı eğri.
    """
    curve = m.get("plastic_curve")
    if curve:
        rows = [(float(s), float(e)) for s, e in curve]
        if any(e < 0 for _, e in rows) or rows[0][1] != 0.0:
            raise ValueError("plastic_curve ilk satırı ε_p = 0 ile başlamalı, ε_p artan olmalı.")
        return rows
    return bilinear_plastic_curve(
        m.get("yield_strength") or 0.0,
        m.get("ultimate_strength"),
        m.get("elongation"),
        m.get("youngs_modulus") or 210e9,
    )
