"""Ply hasar ölçütleri (Faz 3.12): Tsai-Wu + Hashin → IRF.

Girdi ply eksenli düzlem gerilmesi (σ1, σ2, τ12; MPa) ve dayanımlar (MPa).
Çıktı **IRF** (inverse reserve factor): yük λ ile ölçeklendiğinde ölçütün
1'e ulaştığı λ = R için IRF = 1/R. IRF ≥ 1 → ölçüt sağlandı (hasar
başlangıcı). Her ölçüt a·λ² + b·λ = 1 biçimindedir:

- Tsai-Wu (1971), düzlem gerilme:
      F1 = 1/Xt − 1/Xc, F2 = 1/Yt − 1/Yc,
      F11 = 1/(Xt Xc), F22 = 1/(Yt Yc), F66 = 1/S12²,
      F12 = F12* · √(F11 F22)   (F12* parametre; varsayılan −0.5)
      a = F11σ1² + F22σ2² + F66τ12² + 2F12σ1σ2,  b = F1σ1 + F2σ2
- Hashin (1980), düzlem gerilme, dört kip:
      lif çekme (σ1 ≥ 0):    (σ1/Xt)² + (τ12/S12)²
      lif basma (σ1 < 0):    (σ1/Xc)²
      matris çekme (σ2 ≥ 0): (σ2/Yt)² + (τ12/S12)²
      matris basma (σ2 < 0): (σ2/2S23)² + [(Yc/2S23)² − 1]·σ2/Yc + (τ12/S12)²
  S23 kütüphanede yoksa matris basma (σ2/Yc)² + (τ12/S12)² ile hesaplanır
  (`hashin_mc_s23` scalar'ı hangisinin kullanıldığını kaydeder).
  Hashin IRF = dört kipin en büyüğü; kip numarası ayrıca verilir.

Puck / LaRC yok (Dalga 2+). Araç eşik veya öneri koymaz — sayıyı verir.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HASHIN_MODES = ("fiber_tension", "fiber_compression", "matrix_tension", "matrix_compression")


@dataclass(frozen=True)
class Strength:
    """Dayanımlar MPa, pozitif büyüklük (Xc, Yc de pozitif)."""

    xt: float
    xc: float
    yt: float
    yc: float
    s12: float
    s23: float | None = None

    def __post_init__(self) -> None:
        for name in ("xt", "xc", "yt", "yc", "s12"):
            if not getattr(self, name) > 0:
                raise ValueError(f"{name} pozitif olmalı.")
        if self.s23 is not None and not self.s23 > 0:
            raise ValueError("s23 pozitif olmalı.")


def _irf(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a λ² + b λ = 1 için en küçük pozitif kök R → IRF = 1/R (R yoksa 0).

    IRF = (b + √(b² + 4a)) / 2 (a ≥ 0); a = 0 iken b > 0 ise IRF = b.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    disc = np.maximum(b * b + 4.0 * a, 0.0)
    return np.maximum(0.5 * (b + np.sqrt(disc)), 0.0)


def tsai_wu_irf(
    s1: np.ndarray, s2: np.ndarray, t12: np.ndarray, st: Strength, f12_star: float = -0.5
) -> np.ndarray:
    f1 = 1.0 / st.xt - 1.0 / st.xc
    f2 = 1.0 / st.yt - 1.0 / st.yc
    f11 = 1.0 / (st.xt * st.xc)
    f22 = 1.0 / (st.yt * st.yc)
    f66 = 1.0 / st.s12**2
    f12 = f12_star * np.sqrt(f11 * f22)
    a = f11 * s1**2 + f22 * s2**2 + f66 * t12**2 + 2.0 * f12 * s1 * s2
    b = f1 * s1 + f2 * s2
    return _irf(a, b)


def hashin_irf(
    s1: np.ndarray, s2: np.ndarray, t12: np.ndarray, st: Strength
) -> np.ndarray:
    """(..., 4) IRF: lif çekme, lif basma, matris çekme, matris basma (kip dışı 0)."""
    s1 = np.asarray(s1, dtype=float)
    s2 = np.asarray(s2, dtype=float)
    shear = (np.asarray(t12, dtype=float) / st.s12) ** 2
    zero = np.zeros_like(s1)
    ft = np.where(s1 >= 0, _irf((s1 / st.xt) ** 2 + shear, zero), 0.0)
    fc = np.where(s1 < 0, _irf((s1 / st.xc) ** 2, zero), 0.0)
    mt = np.where(s2 >= 0, _irf((s2 / st.yt) ** 2 + shear, zero), 0.0)
    if st.s23 is not None:
        a_mc = (s2 / (2.0 * st.s23)) ** 2 + shear
        b_mc = ((st.yc / (2.0 * st.s23)) ** 2 - 1.0) * s2 / st.yc
    else:
        a_mc = (s2 / st.yc) ** 2 + shear
        b_mc = zero
    mc = np.where(s2 < 0, _irf(a_mc, b_mc), 0.0)
    return np.stack([ft, fc, mt, mc], axis=-1)


def strength_from_material(mat: dict) -> Strength:
    """Kütüphane satırı (Pa) → Strength (MPa)."""
    s23 = mat.get("s23")
    return Strength(
        xt=float(mat["xt"]) / 1e6,
        xc=float(mat["xc"]) / 1e6,
        yt=float(mat["yt"]) / 1e6,
        yc=float(mat["yc"]) / 1e6,
        s12=float(mat["s12"]) / 1e6,
        s23=float(s23) / 1e6 if s23 else None,
    )
