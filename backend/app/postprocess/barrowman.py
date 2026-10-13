"""Barrowman yöntemi — roket basınç merkezi (CP) ve normal kuvvet eğimi CNα (Faz 2, R2).

Sesaltı, küçük hücum açısı, ince gövde kabulleri (Barrowman & Barrowman 1966,
"The Theoretical Prediction of the Center of Pressure", NARAM-8). CFD sonucunun
yanında ANALİTİK REFERANS olarak gösterilir (durability'deki kiriş tablosu
deseni) — veri, karar mühendisin. Formüller literatürden; OpenRocket kodu
kullanılmaz.

Referans alan A_ref = π·d²/4 (d = gövde çapı); uzunluklar burun ucundan (x = 0).

Bileşenler:
- Burun (ince gövde kuramı, her profil için): CNα = 2·A_taban/A_ref,
  X = Ln − V_burun/A_taban (koni → 2/3·Ln, ogive ≈ 0.466·Ln).
- Gövde tüpü: CNα = 0 (Barrowman: silindirik gövdenin normal kuvveti ihmal).
- Konik geçiş / boat-tail (d1 → d2, boy Lt, başlangıç x_t):
  CNα = 2·[(d2/d)² − (d1/d)²],
  X = x_t + Lt/3·[1 + (1 − d1/d2)/(1 − (d1/d2)²)].
- Kanatçıklar (N adet, açıklık s, kök Cr, uç Ct, hücum kenarı ok mesafesi Xs):
  l_m = √(s² + (Xs + Ct/2 − Cr/2)²),
  CNα = K·4N(s/d)² / [1 + √(1 + (2·l_m/(Cr + Ct))²)],  K = 1 + R/(s + R),
  X = X_b + Xs/3·(Cr + 2Ct)/(Cr + Ct) + 1/6·[Cr + Ct − Cr·Ct/(Cr + Ct)].
  4N terimi Barrowman'da 3 ve 4 kanatçık için türetilmiştir; N > 4 sonuçta
  işaretlenir (veri).

Toplam: CNα = Σ CNα_i, X_cp = Σ(CNα_i·X_i)/CNα. Ağırlık merkezi verilirse
kararlılık payı (X_cp − X_cg)/d kalibre olarak — yalnız veri.
"""

from __future__ import annotations

import math
from typing import Any

from app.templates.rocket import RocketParams, nose_radius

_NOSE_STEPS = 2000


def nose_volume_mm3(p: RocketParams) -> float:
    """Burun hacmi (mm³), r(x) profilinin sayısal integrali (Simpson)."""
    n = _NOSE_STEPS
    h = p.nose_length / n
    total = 0.0
    for i in range(n + 1):
        x = i * h
        a = math.pi * nose_radius(p.nose_shape, x, p.nose_length, p.radius) ** 2
        w = 1 if i in (0, n) else (4 if i % 2 else 2)
        total += w * a
    return total * h / 3.0


def barrowman(p: RocketParams, cg_mm: float | None = None) -> dict[str, Any]:
    """Bileşen tablosu + toplam CNα (1/rad) ve X_cp (mm, burun ucundan)."""
    d = p.body_diameter
    R = p.radius
    a_ref = math.pi * d * d / 4.0
    parts: list[dict[str, Any]] = []

    a_base = math.pi * R * R
    x_nose = p.nose_length - nose_volume_mm3(p) / a_base
    parts.append({"name": "burun", "cn_alpha": 2.0 * a_base / a_ref, "x_mm": x_nose})
    parts.append({"name": "govde", "cn_alpha": 0.0, "x_mm": p.nose_length + p.body_length / 2.0})

    if p.boattail_length > 0:
        d1, d2, lt = d, p.boattail_aft_diameter, p.boattail_length
        ratio = d1 / d2
        cn = 2.0 * ((d2 / d) ** 2 - (d1 / d) ** 2)
        x = p.body_end_x + lt / 3.0 * (1.0 + (1.0 - ratio) / (1.0 - ratio**2))
        parts.append({"name": "boattail", "cn_alpha": cn, "x_mm": x})

    s, cr, ct, xs, n = p.fin_span, p.fin_root_chord, p.fin_tip_chord, p.fin_sweep, p.fin_count
    l_m = math.sqrt(s * s + (xs + ct / 2.0 - cr / 2.0) ** 2)
    k_fb = 1.0 + R / (s + R)
    cn_f = k_fb * 4.0 * n * (s / d) ** 2 / (1.0 + math.sqrt(1.0 + (2.0 * l_m / (cr + ct)) ** 2))
    x_b = p.body_end_x - p.fin_offset - cr
    x_f = x_b + xs / 3.0 * (cr + 2.0 * ct) / (cr + ct) + (cr + ct - cr * ct / (cr + ct)) / 6.0
    parts.append({"name": "kanatcik", "cn_alpha": cn_f, "x_mm": x_f, "interference_k": k_fb, "midchord_mm": l_m})

    cn_total = sum(c["cn_alpha"] for c in parts)
    x_cp = sum(c["cn_alpha"] * c["x_mm"] for c in parts) / cn_total
    out: dict[str, Any] = {
        "method": "barrowman_1966",
        "a_ref_m2": a_ref * 1e-6,
        "reference_diameter_mm": d,
        "components": parts,
        "cn_alpha": cn_total,
        "x_cp_mm": x_cp,
        "x_cp_calibers": x_cp / d,
        "notes": ["Sesaltı, küçük hücum açısı, ince gövde kabulleri."],
    }
    if n > 4:
        out["notes"].append("Kanatçık terimi (4N) Barrowman'da 3–4 kanatçık için türetilmiştir; N > 4.")
    if cg_mm is not None:
        out["x_cg_mm"] = cg_mm
        out["stability_calibers"] = (x_cp - cg_mm) / d
    return out
