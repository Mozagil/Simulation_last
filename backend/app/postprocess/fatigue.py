"""Yorulma ömrü (fatigue life) ve güvenlik faktörü (safety factor) hesabı.

ROADMAP.md "6. Post-process (fatigue)": pyLife ile rainflow counting + Miner
kuralı planlanmıştı. Bizim durumumuz TEK bir statik yük durumu (sabit
genlikli, R-oranı belirtilmemiş basit durum) — gerçek rainflow counting
(değişken genlikli zaman serisi gerektirir) burada uygulanamaz, çünkü
elimizde zaman serisi yok, tek bir statik çözüm sonucu var.

Bu yüzden basitleştirilmiş yaklaşım: malzemenin S-N eğrisinden (ARCHITECTURE.md
#malzeme-kütüphanesi'nde tanımlı, `estimate_sn_from_rm` ile üretilen 3 noktalı
log-log eğri), maksimum von Mises gerilmesini TEK bir gerilme genliği olarak
kabul edip, o genlikte kaç çevrimde (N) hasar oluşacağını log-log doğrusal
interpolasyonla buluyoruz. Bu, ROADMAP'in kendi "tahmini/gerçek ayrımı" ilkesine
uygun: gerçek yorulma testinin yerini TUTMAZ, kaba bir başlangıç noktası verir.
"""

from __future__ import annotations

import math
from typing import Any


def estimate_fatigue_life(
    stress_amplitude: float, sn_points: list[dict[str, float]]
) -> dict[str, Any]:
    """S-N eğrisi noktalarından (log-log parçalı doğrusal interpolasyon)
    verilen gerilme genliği için tahmini çevrim sayısını (N) hesaplar.

    `sn_points`: [{"N": çevrim_sayısı, "sigma": gerilme_MPa}, ...] — en az 2
    nokta gerekir. Sıralama önemli değil, fonksiyon kendi sıralar.
    """
    if not sn_points or len(sn_points) < 2:
        return {"cycles": None, "note": "S-N eğrisi yok/yetersiz nokta."}
    if stress_amplitude <= 0:
        return {"cycles": None, "note": "Gerilme sıfır/negatif — yorulma hesabı anlamsız."}

    # Yüksek gerilme (kısa ömür) önce gelecek şekilde sırala.
    pts = sorted(sn_points, key=lambda p: p["sigma"], reverse=True)

    if stress_amplitude >= pts[0]["sigma"]:
        return {
            "cycles": pts[0]["N"],
            "note": "Gerilme S-N eğrisinin en üst (en kısa ömür) noktasının üzerinde — ekstrapole edilmedi, en kötü durum noktası döndürüldü.",
            "runout": False,
        }
    if stress_amplitude <= pts[-1]["sigma"]:
        return {
            "cycles": pts[-1]["N"],
            "note": "Gerilme yorulma sınırının (fatigue limit) altında/civarında — pratikte sonsuz ömür (runout) kabul edilir.",
            "runout": True,
        }

    for i in range(len(pts) - 1):
        s_hi, n_hi = pts[i]["sigma"], pts[i]["N"]
        s_lo, n_lo = pts[i + 1]["sigma"], pts[i + 1]["N"]
        if s_lo <= stress_amplitude <= s_hi:
            log_n_hi = math.log10(n_hi)
            log_n_lo = math.log10(n_lo)
            log_s_hi = math.log10(s_hi)
            log_s_lo = math.log10(s_lo)
            t = (math.log10(stress_amplitude) - log_s_hi) / (log_s_lo - log_s_hi)
            log_n = log_n_hi + t * (log_n_lo - log_n_hi)
            return {
                "cycles": 10**log_n,
                "note": "S-N eğrisi log-log doğrusal interpolasyon (Basquin benzeri).",
                "runout": False,
            }

    # Buraya düşülmemeli (yukarıdaki iki uç-durum kontrolü kapsıyor olmalı)
    # ama güvenlik için:
    return {"cycles": pts[-1]["N"], "note": "Aralık dışı — en yakın nokta kullanıldı."}


def compute_safety_factor(max_von_mises: float, yield_strength: float | None) -> float | None:
    """Statik güvenlik faktörü: akma dayanımı / maksimum von Mises gerilmesi.
    (Yorulma güvenlik faktörü DEĞİL — basit statik akma kıstası.)
    """
    if yield_strength is None or yield_strength <= 0 or max_von_mises <= 0:
        return None
    return yield_strength / max_von_mises
