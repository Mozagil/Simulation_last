"""Crash validasyon hesapları (1.17f) — analitik / literatür referansları ve
koşu eğrilerinden ölçülen büyüklükler. Saf fonksiyonlar; kabul kriteri YOK
(mühendisin): oranlar veri olarak raporlanır.

Birimler: zaman ms, kuvvet kN, uzunluk mm, kütle kg, hız m/s (= mm/ms),
gerilme MPa, yoğunluk kg/m³.

Referanslar (açık literatür; formüller ve varsayımlar rapora yazılır):
- Elastik çubuğun rijit duvara çarpması (1B dalga): σ = ρ·c·v, F = σ·A,
  temas süresi 2L/c; c₀ = √(E/ρ) (çubuk), c_p = √(E/(ρ(1−ν²))) (levha). İnce
  cidarlı kutu iki uç arasında — ikisi de raporlanır.
- Elasto-plastik: dalga önü gerilmesi akmayla sınırlı → plato ≈ σy·A.
- Kare / dikdörtgen tüp ortalama ezilme kuvveti: Wierzbicki & Abramowicz
  (1983) Pm = 9.56·σ0·t^(5/3)·C^(1/3); Abramowicz & Jones (1984, etkin ezilme
  mesafesi dahil) Pm = 13.06·σ0·t^(5/3)·C^(1/3); dikdörtgende C = (b + d)/2
  (orta yüzey kenarları). σ0 = σy (b = 0, hız etkisi yok).
"""

from __future__ import annotations

import math


def wave_speeds(e_pa: float, rho: float, nu: float) -> dict[str, float]:
    """m/s: çubuk c0 ve levha c_p."""
    return {"c0": math.sqrt(e_pa / rho), "cp": math.sqrt(e_pa / (rho * (1.0 - nu * nu)))}


def elastic_impact_force_kn(rho: float, c_m_s: float, v_m_s: float, area_mm2: float) -> float:
    """F = ρ·c·v·A (kN)."""
    return rho * c_m_s * v_m_s * area_mm2 * 1e-6 / 1e3


def contact_duration_ms(length_mm: float, c_m_s: float) -> float:
    """2L/c (ms); c m/s = mm/ms."""
    return 2.0 * length_mm / c_m_s


def tube_mean_crush_force_kn(sigma0_mpa: float, t_mm: float, c_mm: float) -> dict[str, float]:
    """Literatür ortalama ezilme kuvvetleri (kN)."""
    base = sigma0_mpa * t_mm ** (5.0 / 3.0) * c_mm ** (1.0 / 3.0) / 1e3
    return {"wierzbicki_abramowicz_1983": 9.56 * base, "abramowicz_jones_1984": 13.06 * base}


def contact_window(time_ms: list[float], force_kn: list[float], frac: float = 0.05) -> tuple[float, float]:
    """Kuvvetin tepe değerin `frac` katını aştığı ilk ve son an (ms)."""
    peak = max(abs(f) for f in force_kn) if force_kn else 0.0
    idx = [i for i, f in enumerate(force_kn) if abs(f) > frac * peak]
    if not idx:
        return 0.0, 0.0
    return time_ms[idx[0]], time_ms[idx[-1]]


def plateau_kn(time_ms: list[float], force_kn: list[float], t0: float, t1: float) -> float:
    """[t0, t1] aralığında kuvvetin zaman ortalaması (kN)."""
    pts = [(t, f) for t, f in zip(time_ms, force_kn) if t0 <= t <= t1]
    if len(pts) < 2:
        return float("nan")
    area = sum(0.5 * (pts[k][1] + pts[k + 1][1]) * (pts[k + 1][0] - pts[k][0]) for k in range(len(pts) - 1))
    return area / (pts[-1][0] - pts[0][0])


def sled_crush(
    time_ms: list[float], impulse_ns: list[float], mass_kg: float, v0_m_s: float
) -> dict[str, float]:
    """Rijit duvarda kızak: v(t) = v0 − I(t)/M (I N·s, kütle kg → m/s = mm/ms),
    ezilme δ(t) = ∫ v dt (mm) hız sıfıra inene kadar. Kutu kütlesi M'ye dahil
    (tüm momentum duvardan geçer). Mesh'ten bağımsız.
    """
    delta = 0.0
    t_stop = time_ms[-1]
    v_prev = v0_m_s - impulse_ns[0] / mass_kg
    for k in range(1, len(time_ms)):
        v = v0_m_s - impulse_ns[k] / mass_kg
        dt = time_ms[k] - time_ms[k - 1]
        if v <= 0.0 < v_prev:
            # sıfır geçişine doğrusal: kalan parça
            frac = v_prev / (v_prev - v)
            delta += 0.5 * v_prev * dt * frac
            t_stop = time_ms[k - 1] + dt * frac
            break
        delta += 0.5 * (v_prev + v) * dt
        v_prev = v
    return {"crush_mm": delta, "t_stop_ms": t_stop}


def ratio(sim: float, ref: float) -> float:
    return sim / ref if ref else float("nan")
