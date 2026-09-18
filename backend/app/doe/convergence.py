"""Mesh yakınsama (convergence) taraması — Faz 0.6.

Neden ayrı bir modül: DOE parametre uzayını tarar, convergence ise TEK bir
geometriyi sabit tutup yalnız eleman boyutunu değiştirir. Amaç fizik öğrenmek
değil, "hangi çözünürlükten sonra cevap değişmiyor" sorusuna cevap vermek.

Bu neden önemli: `element_size` surrogate'in skaler girdilerinden biri
(scalar_features.py). Yakınsamamış bir bantta örnek toplarsak model
"eleman boyutu değişince gerilme değişir" ilişkisini FİZİK sanıp öğrenir —
oysa o, ayrıklaştırma hatasıdır. Yakınsamış bandı ölçüp DOE'yi oraya
hapsetmek, veri setinin gürültüsünü doğrudan düşürür.

Modülün saf (DB/solver bağımsız) kısmı burada; koşturma `runner.py`'de.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

#: Yakınsamış sayılmak için ardışık iki basamak arasındaki bağıl değişim
#: eşiği. Deplasman gerilmeden çok daha hızlı yakınsar; ayrı eşik veriyoruz.
DEFAULT_TOL_DISP = 0.02  # %2
DEFAULT_TOL_STRESS = 0.05  # %5


class ConvergenceSpec(BaseModel):
    """Tek geometri, sabit malzeme/BC; yalnız eleman boyutu taranır."""

    template_id: str
    #: Şablon parametreleri (L, T, W…) — SABİT, taranmaz.
    geometry_params: dict[str, Any] = Field(default_factory=dict)
    material_id: int
    scenario_name: str
    bcs: list[dict[str, Any]] = Field(min_length=1)
    #: Karakteristik uzunluğun (kirişte T) katları olarak basamaklar.
    #: Kabadan inceye sıralanır; her basamak bir çözüm demek.
    ratios: list[float] = Field(
        default=[1.5, 1.2, 1.0, 0.8, 0.6, 0.5, 0.4, 0.3], min_length=2
    )
    #: Oranların çarpılacağı uzunluk (mm). Kirişte kalınlık T.
    characteristic_length: float = Field(gt=0)
    #: Mutlak alt sınır — çok ince mesh'te ccx dakikalarca koşar.
    min_element_size: float = Field(default=1.0, gt=0)
    dimension: int = 3
    element_scheme: str = "tet"
    tol_disp: float = Field(default=DEFAULT_TOL_DISP, gt=0)
    tol_stress: float = Field(default=DEFAULT_TOL_STRESS, gt=0)
    name: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "ConvergenceSpec":
        if any(r <= 0 for r in self.ratios):
            raise ValueError("ratios pozitif olmalı.")
        if len(set(self.ratios)) != len(self.ratios):
            raise ValueError("ratios tekrarsız olmalı.")
        return self


def element_size_ladder(spec: ConvergenceSpec) -> list[float]:
    """Oranlardan mutlak eleman boyutu merdiveni (kabadan inceye).

    `min_element_size` altına düşen basamaklar elenir — yoksa ccx'te
    saatlerce koşan bir mesh üretiriz. Eleme sonrası 2'den az basamak
    kalırsa hata; tek noktayla yakınsama ölçülemez.
    """
    sizes = sorted(
        {
            round(r * spec.characteristic_length, 4)
            for r in spec.ratios
            if r * spec.characteristic_length >= spec.min_element_size
        },
        reverse=True,
    )
    if len(sizes) < 2:
        raise ValueError(
            "min_element_size çok yüksek: en az 2 basamak kalmalı "
            f"(karakteristik uzunluk {spec.characteristic_length} mm)."
        )
    return sizes


def _rel_change(prev: float | None, cur: float | None) -> float | None:
    """|cur-prev| / |prev|. Payda ~0 ise oransal hata anlamsız → None."""
    if prev is None or cur is None:
        return None
    if abs(prev) < 1e-12:
        return None
    return abs(cur - prev) / abs(prev)


def _tail_band(values: list[float], k: int = 4) -> float | None:
    """En ince k çözümün bağıl yayılımı = (max-min)/ortalama.

    Bu sayı *gürültü tabanı*: mesh incelterek bunun altına inilemiyor.
    Surrogate'in ulaşabileceği doğruluğun tavanını da bu belirler —
    hedefin kendisi ±%X oynuyorsa model bunun altına inemez.
    """
    tail = [v for v in values[-k:] if v is not None]
    if len(tail) < 2:
        return None
    mean = sum(tail) / len(tail)
    if abs(mean) < 1e-12:
        return None
    return (max(tail) - min(tail)) / abs(mean)


def _converged_at(
    sizes: list[float], values: list[float | None], tol: float
) -> float | None:
    """En ince çözümü referans alıp, ondan itibaren tol içinde kalınan en
    KABA eleman boyutunu döndürür.

    ÖLÇTÜK, İKİ KEZ DÜZELTTİK: (1) "tek adım eşiğin altına düştü" kriteri
    salınımı yakınsama sanıyordu. (2) "ardışık iki adım" kriteri de
    yetmedi — ankastre kiriş taramasında σ'nın adım-adım değişimlerinin
    neredeyse hepsi %5 eşiğinin altındaydı, ama dizi 315–346 arasında
    salınıyordu. Adımlar arası fark küçük olabilir, dizi yine de hiçbir
    yere oturmayabilir. Doğru soru: "en ince çözüme göre ne kadar
    sapıyorum ve inceldikçe bu sapma kalıcı olarak küçülüyor mu".
    """
    pairs = [(s, v) for s, v in zip(sizes, values) if v is not None]
    if len(pairs) < 2:
        return None
    ref = pairs[-1][1]
    if abs(ref) < 1e-12:
        return None
    hit: float | None = None
    # Kabadan inceye: bir kez tol dışına çıkıldıysa, o noktadan önceki
    # iddia geçersiz — bu yüzden en kabadan tarayıp son bozulmayı buluyoruz.
    for size, val in pairs:
        if abs(val - ref) / abs(ref) <= tol:
            if hit is None:
                hit = size
        else:
            hit = None
    # En ince çözüm referansın kendisi; yalnız o banda giriyorsa hiçbir şey
    # kanıtlanmamıştır (tek nokta yakınsama göstermez).
    if hit is not None and hit == pairs[-1][0]:
        return None
    return hit


def assess_convergence(
    steps: list[dict[str, Any]],
    tol_disp: float = DEFAULT_TOL_DISP,
    tol_stress: float = DEFAULT_TOL_STRESS,
) -> dict[str, Any]:
    """Basamak tablosundan yakınsama kararı + gürültü tabanı üretir.

    `steps`: kabadan inceye sıralı, her biri en az
    {element_size, node_count, max_displacement, max_von_mises} içeren
    sözlükler. Çözülemeyen basamaklar tabloda kalır ama hesaba girmez.

    İki ayrı çıktı veriyoruz ve ikisi de gerekli:
    - `*_converged_at`: en ince çözümden tol kadar sapmadan durulan en kaba
      mesh. "Bundan daha ince meshe gerek yok" demek.
    - `*_noise_floor`: en ince 4 çözümün yayılımı. "Bu değerin altına mesh
      inceltmekle inilemez" demek. Eşikle kıyaslanabilir büyüklükteyse
      yakınsama iddiası anlamsızdır; sonuç sadece gürültü bandındadır.
    """
    table: list[dict[str, Any]] = []
    prev_u: float | None = None
    prev_s: float | None = None

    for st in steps:
        u = st.get("max_displacement")
        s = st.get("max_von_mises")
        row = dict(st)
        row["rel_change_disp"] = _rel_change(prev_u, u)
        row["rel_change_stress"] = _rel_change(prev_s, s)
        table.append(row)
        if u is not None:
            prev_u = u
        if s is not None:
            prev_s = s

    sizes = [r.get("element_size") for r in table]
    us = [r.get("max_displacement") for r in table]
    ss = [r.get("max_von_mises") for r in table]

    # En ince çözüme göre sapma — tabloya da yazıyoruz, okunur olsun.
    for key, vals in (("dev_from_finest_disp", us), ("dev_from_finest_stress", ss)):
        ref = next((v for v in reversed(vals) if v is not None), None)
        for row, v in zip(table, vals):
            row[key] = (
                abs(v - ref) / abs(ref)
                if (v is not None and ref not in (None, 0))
                else None
            )

    disp_at = _converged_at(sizes, us, tol_disp)
    stress_at = _converged_at(sizes, ss, tol_stress)
    disp_floor = _tail_band([v for v in us if v is not None])
    stress_floor = _tail_band([v for v in ss if v is not None])

    solved = [r for r in table if r.get("max_displacement") is not None]
    finest = solved[-1] if solved else None

    notes: list[str] = []
    if disp_at is None:
        notes.append("Deplasman yakınsamadı: daha ince mesh gerekiyor.")
    elif solved and disp_at == solved[0].get("element_size"):
        notes.append(
            "Deplasman en kaba mesh'te bile yakınsamış — merdiven yakınsamamış "
            "bölgeyi hiç yakalamadı. Pratik sonuç: bu büyüklükte mesh boyutu "
            "deplasmanı etkilemiyor, DOE'de en kaba (en ucuz) mesh kullanılabilir."
        )
    if disp_floor is not None and disp_floor > tol_disp:
        notes.append(
            f"Deplasman gürültü tabanı (%{disp_floor * 100:.1f}) toleransın "
            f"(%{tol_disp * 100:.0f}) üstünde — yakınsama iddiası anlamsız."
        )
    if stress_at is None:
        notes.append(
            "Gerilme yakınsamadı. Ankastre köşe tekil bir nokta; max σ düğüm "
            "bazında alındığı için hangi düğümün köşeye düştüğü mesh'ten "
            "mesh'e değişiyor."
        )
    if stress_floor is not None and stress_floor > tol_stress:
        notes.append(
            f"Gerilme gürültü tabanı %{stress_floor * 100:.1f} — mesh "
            f"inceltmekle bunun altına inilemiyor. max σ'yı surrogate hedefi "
            f"yaparsan modelin doğruluk tavanı da bu civarıdır; hedefi "
            f"tekillikten uzak bir konumdan ölçmek gerekir."
        )
    if len(solved) < len(table):
        notes.append(f"{len(table) - len(solved)} basamak çözülemedi.")

    return {
        "table": table,
        "disp_converged_at": disp_at,
        "stress_converged_at": stress_at,
        "disp_noise_floor": disp_floor,
        "stress_noise_floor": stress_floor,
        "tol_disp": tol_disp,
        "tol_stress": tol_stress,
        "finest": finest,
        "recommended_element_size": disp_at,
        "recommended_ratio": None,
        "notes": notes,
    }


def recommended_ratio(
    assessment: dict[str, Any], characteristic_length: float
) -> float | None:
    """Önerilen eleman boyutunu karakteristik uzunluğa oranla ifade eder.

    DOE `element_ratio` ile tarıyor; öneriyi de aynı birimde vermek gerekir
    ki doğrudan kullanılabilsin.
    """
    size = assessment.get("recommended_element_size")
    if size is None or characteristic_length <= 0:
        return None
    return round(float(size) / characteristic_length, 4)
