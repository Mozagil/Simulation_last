"""Ahmed gövdesi deney sürükleme katsayıları — Faz 2.6c (V-C4).

Ahmed, Ramm & Faltin (1984), SAE 840300: U = 60 m/s, Re_L ≈ 4.29·10⁶,
A_ref = 0.112 m² (W·H). Deneyde bacaklar ve sabit zemin vardı.
Yalnız referans veri; ara açılar için değer yok (interpolasyon yapılmaz).
"""

from __future__ import annotations

AHMED_CD_EXPERIMENT: dict[float, float] = {
    0.0: 0.250,
    12.5: 0.230,
    25.0: 0.285,
    30.0: 0.378,
    35.0: 0.260,
}


def ahmed_cd_experiment(slant_angle_deg: float) -> float | None:
    """Ölçülmüş açılardan biriyse deney Cd, değilse None."""
    return AHMED_CD_EXPERIMENT.get(round(float(slant_angle_deg), 1))
