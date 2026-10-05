"""SAE J211-1 / ISO 6487 CFC kanal filtresi (1.17e).

4 kutuplu fazsız Butterworth: 2 kutuplu süzgeç ileri, sonra geri (J211-1
Ek C). Sınıflar 60, 180, 600, 1000 (Hz). Seçim mühendisin; ham veri korunur.
Doğrulama (test): CFC frekansında −0.45 dB (geçiş bandı +0.5 / −1 dB),
1.65·CFC'de ≈ −3 dB, 10·CFC'de < −50 dB.

TH örnekleri tam eşit aralıklı değil (Radioss yazma anı zaman adımına bağlı):
süzgeç eşit aralıklı ızgarada (ortalama adım) uygulanır, sonuç doğrusal
aradeğerle özgün zamanlara geri taşınır.
"""

from __future__ import annotations

import math

CFC_CLASSES = (60, 180, 600, 1000)


def _two_pole(x: list[float], a0: float, a1: float, a2: float, b1: float, b2: float) -> list[float]:
    # Başlangıç geçici rejimi yerine ilk değerle başlat (yaygın uygulama).
    y = [x[0], x[0]] + [0.0] * (len(x) - 2)
    for i in range(2, len(x)):
        y[i] = a0 * x[i] + a1 * x[i - 1] + a2 * x[i - 2] + b1 * y[i - 1] + b2 * y[i - 2]
    return y


def cfc_filter_uniform(x: list[float], dt_s: float, cfc: int) -> list[float]:
    """Eşit aralıklı örnekler (adım dt_s, saniye) → CFC süzülmüş."""
    if cfc not in CFC_CLASSES:
        raise ValueError(f"CFC sınıfı {CFC_CLASSES} olmalı.")
    if len(x) < 3:
        return list(x)
    wd = 2.0 * math.pi * cfc * 2.0775
    wa = math.sin(wd * dt_s / 2.0) / math.cos(wd * dt_s / 2.0)
    d = 1.0 + math.sqrt(2.0) * wa + wa * wa
    a0 = wa * wa / d
    a1 = 2.0 * a0
    b1 = -2.0 * (wa * wa - 1.0) / d
    b2 = (-1.0 + math.sqrt(2.0) * wa - wa * wa) / d
    fwd = _two_pole(list(x), a0, a1, a0, b1, b2)
    return _two_pole(fwd[::-1], a0, a1, a0, b1, b2)[::-1]


def _interp(xs: list[float], ys: list[float], q: list[float]) -> list[float]:
    out, j = [], 0
    for t in q:
        while j + 1 < len(xs) - 1 and xs[j + 1] < t:
            j += 1
        x0, x1 = xs[j], xs[min(j + 1, len(xs) - 1)]
        y0, y1 = ys[j], ys[min(j + 1, len(ys) - 1)]
        out.append(y0 if x1 == x0 else y0 + (y1 - y0) * (t - x0) / (x1 - x0))
    return out


def cfc_filter(time_ms: list[float], values: list[float], cfc: int) -> list[float]:
    """Zaman (ms) + değerler → aynı zamanlarda CFC süzülmüş değerler."""
    n = min(len(time_ms), len(values))
    if n < 3:
        return list(values[:n])
    t, v = time_ms[:n], values[:n]
    dt = (t[-1] - t[0]) / (n - 1)
    if dt <= 0:
        return list(v)
    grid = [t[0] + i * dt for i in range(n)]
    filt = cfc_filter_uniform(_interp(t, v, grid), dt * 1e-3, cfc)
    return _interp(grid, filt, t)


def sample_ratio(time_ms: list[float], cfc: int) -> float:
    """Örnekleme frekansı / CFC (veri olarak raporlanır; eşik mühendisin)."""
    if len(time_ms) < 2:
        return 0.0
    dt_s = (time_ms[-1] - time_ms[0]) / (len(time_ms) - 1) * 1e-3
    return (1.0 / dt_s) / cfc if dt_s > 0 else 0.0
