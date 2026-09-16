"""HIC (Head Injury Criterion) — FMVSS 208 / SAE J211.

HIC = max ( (1/Δt ∫ a dt )^2.5 · Δt )  for 0 < Δt ≤ window
a: resultant acceleration in g, Δt in seconds.
HIC15 window=15 ms, HIC36 window=36 ms.
"""

from __future__ import annotations

import math


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
    t = [float(x) for x in time_s[:n]]
    a = [float(x) for x in acc_g[:n]]
    best = 0.0
    for i in range(n - 1):
        for j in range(i + 1, n):
            dt = t[j] - t[i]
            if dt <= 1e-9 or dt > window_s + 1e-15:
                continue
            integral = 0.0
            for k in range(i, j):
                integral += 0.5 * (a[k] + a[k + 1]) * (t[k + 1] - t[k])
            mean = integral / dt
            if mean < 0:
                mean = abs(mean)
            score = (mean**2.5) * dt
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
