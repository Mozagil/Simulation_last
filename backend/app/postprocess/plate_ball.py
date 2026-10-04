"""Plaka–küre koşusundan küre büyüklükleri (1.18d) — saf fonksiyonlar.

Küre rijit gövde (1.18b): kütlesi ilk kinetik enerjiden okunur (plaka t = 0'da
durgun, KE₀ = ½·m·v0² → m = 2·KE₀/v0²); kabuk + ek kütle ayrıca hesaplanmaz.
Son hız iki yoldan:
- impuls: z yukarı, küre −z ile gelir → v_son,z = −v0 + I/m. Negatif = hâlâ
  plakaya doğru (temas sürüyor ya da plakayı geçti), pozitif = geri sekti.
- enerji: |v_son| = √(2·(KE_son,global − KE_son,plaka)/m) — işaretsiz kontrol.
Hüküm yok (delinme eşiği mühendisin); veri.
"""

from __future__ import annotations

import math


def ball_mass_kg(ke0_j: float, v0_m_s: float) -> float:
    """KE₀ [J] ve v0 [m/s] → kütle [kg] (kg–mm–ms'de J ve m/s aynı ölçek)."""
    if v0_m_s <= 0:
        raise ValueError("v0 pozitif olmalı.")
    return 2.0 * ke0_j / (v0_m_s * v0_m_s)


def residual_velocity_impulse(v0_m_s: float, impulse_ns: float, mass_kg: float) -> float:
    """İşaretli son hız (m/s, +z yukarı): −v0 + I/m."""
    if mass_kg <= 0:
        raise ValueError("kütle pozitif olmalı.")
    return -v0_m_s + impulse_ns / mass_kg


def residual_speed_energy(ke_final_global_j: float, ke_final_plate_j: float, mass_kg: float) -> float:
    """İşaretsiz son hız (m/s) küre kinetik enerjisinden; negatif fark 0'a kırpılır."""
    if mass_kg <= 0:
        raise ValueError("kütle pozitif olmalı.")
    ke = max(0.0, ke_final_global_j - ke_final_plate_j)
    return math.sqrt(2.0 * ke / mass_kg)
