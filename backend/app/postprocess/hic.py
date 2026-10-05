"""HIC (Head Injury Criterion) — FMVSS 208 / SAE J211.

HIC = max ( (1/Δt ∫ a dt )^2.5 · Δt )  for 0 < Δt ≤ window
a: resultant acceleration in g, Δt in seconds.
HIC15 window=15 ms, HIC36 window=36 ms.

1.17e: integral birikimli (trapez önek toplamı) — eski üçlü döngü O(n³)
2000 TH örneğinde dakikalar sürüyor, sunucuyu kilitliyordu; tanım aynı.
"""

from __future__ import annotations

import math

import numpy as np


def hic(
    time_s: list[float],
    acc_g: list[float],
    window_s: float,
) -> float:
    if window_s <= 0:
        raise ValueError("HIC penceresi pozitif olmalı.")
    n = min(len(time_s), len(acc_g))
    if n < 2:
        return 0.0
    t = np.asarray(time_s[:n], dtype=float)
    a = np.asarray(acc_g[:n], dtype=float)
    # C[k] = ∫_{t0}^{tk} a dt (trapez) → ∫_{ti}^{tj} = C[j] − C[i]
    cum = np.concatenate(([0.0], np.cumsum(0.5 * (a[1:] + a[:-1]) * np.diff(t))))
    best = 0.0
    for i in range(n - 1):
        dt = t[i + 1 :] - t[i]
        ok = (dt > 1e-9) & (dt <= window_s + 1e-15)
        if not ok.any():
            continue
        mean = np.abs((cum[i + 1 :][ok] - cum[i]) / dt[ok])
        score = float(np.max(mean**2.5 * dt[ok]))
        if score > best:
            best = score
    return best


def hic15(time_s: list[float], acc_g: list[float]) -> float:
    return hic(time_s, acc_g, 0.015)


def hic36(time_s: list[float], acc_g: list[float]) -> float:
    return hic(time_s, acc_g, 0.036)


def resultant_g(ax: list[float], ay: list[float], az: list[float]) -> list[float]:
    n = min(len(ax), len(ay), len(az))
    return [math.sqrt(ax[i] ** 2 + ay[i] ** 2 + az[i] ** 2) for i in range(n)]
