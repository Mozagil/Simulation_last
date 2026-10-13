"""Küre sürükleme katsayısı referansları — Faz 2.6a (V-C2).

- Schiller & Naumann (1933), Re < 800, deneysel veriye ±%5:
      Cd = 24/Re · (1 + 0.15·Re^0.687)
- Clift, Grace & Weber (1978) standart sürükleme eğrisi ("Bubbles, Drops and
  Particles", Tablo 5.2), daha dar aralıklı uydurma:
      0.01 < Re ≤ 20:  Cd = 24/Re · (1 + 0.1315·Re^(0.82 − 0.05·w)),  w = log10 Re
      20 < Re ≤ 260:   Cd = 24/Re · (1 + 0.1935·Re^0.6305)

Re = U·D/ν. Yalnız referans veri; CFD ile karşılaştırma doğrulama raporunda.
"""

from __future__ import annotations

import math


def schiller_naumann(re: float) -> float:
    if re <= 0:
        raise ValueError("Re pozitif olmalı.")
    return 24.0 / re * (1.0 + 0.15 * re**0.687)


def clift_grace_weber(re: float) -> float:
    if not 0.01 < re <= 260:
        raise ValueError("Clift–Grace–Weber bu uydurması 0.01 < Re ≤ 260 için.")
    if re <= 20:
        w = math.log10(re)
        return 24.0 / re * (1.0 + 0.1315 * re ** (0.82 - 0.05 * w))
    return 24.0 / re * (1.0 + 0.1935 * re**0.6305)
