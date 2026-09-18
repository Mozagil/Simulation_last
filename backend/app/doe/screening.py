"""DOE örneklerinin fiziksel geçerlilik ön elemesi (Faz 0.6).

SORUN — ölçtük: DOE parametreleri bağımsız örneklendiği için, üretilen
örneklerin bir kısmı LİNEER analizin geçerli olmadığı bölgeye düşüyor.
Eski kalite seti (alüminyum, L 450–700, uç yükü 0.4–1.6 × 500 N) ile
çözülmüş 22 kirişten yalnız 8'i korpus kapısından geçebildi:

    no_template: 14 · large_displacement: 13 · analytic_warn: 1

Yani ccx 13 kez koştu, sonuç üretti, sonra korpus onları attı. Boşa
harcanan çözüm. Referans vakanın kendisi bile (L=500, T=10, W=50,
F=500 N) alüminyumla u/L = 0.146 → kapıdan geçemiyor.

Kök sebep: `sampling._params_valid` yalnız ŞABLONUN GEOMETRİK kısıtına
bakıyor (L ≥ 5T gibi). Fiziksel geçerliliğe — büyük deformasyon,
akma — bakan kimse yok. Kapı (corpus.py) ve DOE birbirine bakmıyor.

ÇÖZÜM: Örneği koşmadan ÖNCE analitik çözümle ön ele. Analitik zaten var
(`template.analytic`), maliyeti sıfır. Elenen örnek yerine yenisi
çekilir — rejection sampling mekanizması `sample_spec` içinde hazır.

Böylece: geniş bir kutu tanımlanır, filtre geçerli bölgeyi oyar. Kutuyu
elle daraltmaya çalışmaktan daha sağlam — köşelerin hangisinin ihlal
ettiğini elle hesaplamak gerekmez.
"""

from __future__ import annotations

import logging
from typing import Any

from app.templates import UnknownTemplateError, get_template
from app.templates.base import AnalyticInput

logger = logging.getLogger(__name__)

#: u/L üst sınırı. corpus.py kapısı 0.10; burada MARJLA 0.06 kullanıyoruz.
#: Sebep: analitik tahmin lineer, FEA biraz daha büyük deplasman verir
#: (kesme etkisi). 0.10'a dayanan örnekler kapıda elenebilir.
DEFAULT_MAX_U_OVER_L = 0.06

#: Akma gerilmesinin ne kadarına kadar izin verilir. 0.8 = %20 marj.
#: Üstünde plastik davranış başlar; lineer çözücü sessizce yanlış verir.
DEFAULT_YIELD_UTILISATION = 0.8


class ScreenResult:
    __slots__ = ("ok", "reason", "u_over_l", "sigma_mpa", "u_mm")

    def __init__(
        self,
        ok: bool,
        reason: str | None = None,
        u_over_l: float | None = None,
        sigma_mpa: float | None = None,
        u_mm: float | None = None,
    ) -> None:
        self.ok = ok
        self.reason = reason
        self.u_over_l = u_over_l
        self.sigma_mpa = sigma_mpa
        self.u_mm = u_mm

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "u_over_l": self.u_over_l,
            "sigma_mpa": self.sigma_mpa,
            "u_mm": self.u_mm,
        }


def _reference_length(params: Any, geometry_params: dict[str, Any]) -> float | None:
    """u/L oranı için referans uzunluk.

    Kirişte `length`. Şablonda böyle bir alan yoksa oransal deplasman
    kriteri uygulanamaz (None döner) — o durumda yalnız akma kontrolü
    yapılır.
    """
    for key in ("length", "span", "L"):
        val = geometry_params.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
    val = getattr(params, "length", None)
    return float(val) if isinstance(val, (int, float)) and val > 0 else None


def screen_sample(
    template_id: str,
    geometry_params: dict[str, Any],
    force_n: float,
    youngs_modulus_pa: float,
    yield_strength_pa: float | None,
    max_u_over_l: float = DEFAULT_MAX_U_OVER_L,
    yield_utilisation: float = DEFAULT_YIELD_UTILISATION,
) -> ScreenResult:
    """Analitik çözümle örneğin lineer-elastik bölgede olup olmadığına bakar.

    Şablonun analitik çözümü yoksa örnek GEÇER — eleyemediğimiz için
    reddetmek, veri setini sebepsiz daraltır. Kapı (corpus) yine de
    çözümden sonra son sözü söyler.
    """
    try:
        tpl = get_template(template_id)
    except UnknownTemplateError:
        return ScreenResult(True, reason="bilinmeyen şablon — elenmedi")

    if tpl.analytic is None:
        return ScreenResult(True, reason="analitik yok — elenmedi")

    try:
        params = tpl.parse_params(geometry_params)
    except Exception as exc:  # noqa: BLE001
        return ScreenResult(False, reason=f"geometrik kısıt: {exc}")

    try:
        ref = tpl.analytic(
            params,
            AnalyticInput(
                force_n=abs(float(force_n)),
                youngs_modulus_pa=float(youngs_modulus_pa),
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("analitik hesaplanamadı (%s): %s", template_id, exc)
        return ScreenResult(True, reason="analitik hata — elenmedi")

    u = float(ref.get("max_displacement") or 0.0)
    sigma = float(ref.get("max_von_mises") or 0.0)

    length = _reference_length(params, geometry_params)
    u_over_l = (u / length) if length else None

    if u_over_l is not None and u_over_l > max_u_over_l:
        return ScreenResult(
            False,
            reason=f"büyük deformasyon: u/L={u_over_l:.3f} > {max_u_over_l}",
            u_over_l=u_over_l,
            sigma_mpa=sigma,
            u_mm=u,
        )

    if yield_strength_pa:
        limit = (float(yield_strength_pa) / 1e6) * yield_utilisation
        if sigma > limit:
            return ScreenResult(
                False,
                reason=f"akma aşımı: σ={sigma:.0f} > {limit:.0f} MPa",
                u_over_l=u_over_l,
                sigma_mpa=sigma,
                u_mm=u,
            )

    return ScreenResult(True, u_over_l=u_over_l, sigma_mpa=sigma, u_mm=u)
