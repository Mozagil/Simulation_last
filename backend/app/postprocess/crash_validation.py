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
- 1.18e Plaka–küre, elastik yarı-statik (ağır küre, düşük hız): dört kenarı
  ankastre kare plaka, merkez tekil yük (Timoshenko & Woinowsky-Krieger,
  Tablo 55, ν = 0.3): w = α·P·a²/D, α = 0.00560, D = E·t³/(12(1−ν²)) →
  k = D/(α·a²). Tek serbestlik: F_max = v·√(k·m), δ_max = v·√(m/k), temas
  süresi π·√(m/k). Varsayım: küre kütlesi ≫ plaka etkin kütlesi, temas
  rijitliği ≫ k, kayma şekil değiştirmesi yok (a/t büyük).
- Recht & Ipson (1963) son hız: v_r = a·(v0^p − v_bl^p)^(1/p), rijit mermi
  p = 2 → v_r² = a²·v0² − a²·v_bl², v0² üzerinde doğrusal (en küçük kareler).
  Tutarlılık verisi; mutlak doğruluk değil.
- K1 Taylor çubuğu: Taylor (1948) rijit-plastik tek boyutlu kuram; Wilkins
  & Guinan (1973) yaklaşığı L1/L0 = h/L0 + (1 − h/L0)·exp(−ρ·v0²/(2·σ0));
  h = 0 alt sınır olarak raporlanır (h deneysel, malzemeye bağlı).
- K2 düşme: serbest düşme g aralığı: g = v0·t + ½·|a|·t² → temas anı;
  momentum (z yukarı) I_duvar = m·(vz_son − vz_0) + m·|a|·t (yerçekimi
  impulsu); KE₀ = m·|a|·H (H'den hız).
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


# --- 1.18e plaka–küre ----------------------------------------------------------

#: Ankastre kare plaka merkez yükü çökme katsayısı (ν = 0.3; Timoshenko Tablo 55)
CLAMPED_SQUARE_ALPHA = 0.00560


def plate_rigidity_nmm(e_pa: float, nu: float, t_mm: float) -> float:
    """Eğilme rijitliği D (N·mm)."""
    return (e_pa / 1e6) * t_mm**3 / (12.0 * (1.0 - nu * nu))


def clamped_square_plate_stiffness_n_per_mm(e_pa: float, nu: float, t_mm: float, a_mm: float) -> float:
    """Merkez yük rijitliği k = D/(α·a²) (N/mm)."""
    return plate_rigidity_nmm(e_pa, nu, t_mm) / (CLAMPED_SQUARE_ALPHA * a_mm * a_mm)


def quasi_static_impact(k_n_per_mm: float, mass_kg: float, v_m_s: float) -> dict[str, float]:
    """Kütle–yay: F_max (kN), δ_max (mm), temas süresi (ms) — yarım periyot."""
    k = k_n_per_mm * 1e3  # N/m
    w = math.sqrt(k / mass_kg)  # rad/s
    return {
        "force_max_kn": v_m_s * math.sqrt(k * mass_kg) / 1e3,
        "deflection_max_mm": v_m_s / w * 1e3,
        "contact_ms": math.pi / w * 1e3,
    }


def recht_ipson_fit(v0_m_s: list[float], v_res_m_s: list[float]) -> dict[str, float]:
    """p = 2: v_r² = A·v0² + B → a = √A, v_bl = √(−B/A); R² v_r² üzerinde.

    Yalnız delinmiş noktalar (|v_r| > 0) verilmeli; en az 2 nokta."""
    if len(v0_m_s) != len(v_res_m_s) or len(v0_m_s) < 2:
        raise ValueError("en az 2 (v0, v_r) çifti gerekli.")
    x = [v * v for v in v0_m_s]
    y = [v * v for v in v_res_m_s]
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx == 0:
        raise ValueError("v0 değerleri farklı olmalı.")
    slope = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / sxx
    icpt = my - slope * mx
    ss_tot = sum((yi - my) ** 2 for yi in y)
    ss_res = sum((yi - (slope * xi + icpt)) ** 2 for xi, yi in zip(x, y))
    a = math.sqrt(slope) if slope > 0 else float("nan")
    v_bl = math.sqrt(-icpt / slope) if slope > 0 and icpt < 0 else float("nan")
    return {"a": a, "v_bl_m_s": v_bl, "r2": 1.0 - ss_res / ss_tot if ss_tot else float("nan")}


# --- K1 Taylor çubuğu --------------------------------------------------------


def wilkins_guinan_ratio(rho: float, v_m_s: float, sigma0_pa: float, h_over_l0: float = 0.0) -> float:
    """L1/L0 = h/L0 + (1 − h/L0)·exp(−ρ·v²/(2·σ0))."""
    return h_over_l0 + (1.0 - h_over_l0) * math.exp(-rho * v_m_s * v_m_s / (2.0 * sigma0_pa))


def taylor_final_shape(faces: list[list[int]], positions: list[float], axis: int = 0) -> dict[str, float]:
    """Son karedeki çubuk: boy L1 (eksen boyunca) ve çarpma ucu çapı D1.

    Yalnız yüzlerde geçen düğümler kullanılır (anim'deki rijit duvar
    noktaları dışarıda kalır). D1: eksene en yakın uçtaki (min eksen
    koordinatı + 0.5 mm) düğümlerin eksenden en büyük uzaklığının iki katı."""
    ids = sorted({v for f in faces for v in f})
    if not ids:
        raise ValueError("yüz yok.")
    pts = [(positions[3 * i], positions[3 * i + 1], positions[3 * i + 2]) for i in ids]
    ax = [q[axis] for q in pts]
    lo, hi = min(ax), max(ax)
    o = [k for k in range(3) if k != axis]
    front = [math.hypot(q[o[0]], q[o[1]]) for q in pts if q[axis] <= lo + 0.5]
    return {"length_mm": hi - lo, "front_diameter_mm": 2.0 * max(front)}


# --- K2 düşme testi -------------------------------------------------------------


def free_fall_contact_ms(gap_mm: float, v0_m_s: float, g_m_s2: float) -> float:
    """g = v0·t + ½·g·t² (mm, ms; g m/s² = 1e-3 mm/ms²) → t (ms)."""
    a = 0.5 * g_m_s2 * 1e-3
    if a == 0:
        return gap_mm / v0_m_s
    return (-v0_m_s + math.sqrt(v0_m_s * v0_m_s + 4.0 * a * gap_mm)) / (2.0 * a)


def drop_wall_impulse_ns(mass_kg: float, vz0_m_s: float, vz_end_m_s: float, g_m_s2: float, t_ms: float) -> float:
    """z yukarı, yerçekimi −z: I_duvar = m·(vz_son − vz_0) + m·g·t (N·s)."""
    return mass_kg * (vz_end_m_s - vz0_m_s) + mass_kg * g_m_s2 * t_ms * 1e-3
