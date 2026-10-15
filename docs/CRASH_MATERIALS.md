# Crash malzeme verisi — açık literatür (1.24e)

> Yalnız doküman. Kütüphaneye girmez (o 1.24f — şema kararı bekliyor). Ticari / lisanslı
> malzeme kartı (vendor kartları, GRANTA vb.) kopyalanmaz. **Araç değer önermez:** hangi set,
> hangi sıcaklık / hız aralığında, hangi kalınlıkta geçerli — karar mühendisin.

## Doğrulama kuralı

Bu belgeye yalnız **birincil kaynakta okunarak doğrulanan** değerler yazıldı (tablo ya da
yazarların kendi özet metni). Yaygın atıfla dolaşan ama birincil kaynağı okunamayan değerler
**yazılmadı**; "Doğrulanmadı" bölümünde kaynak adıyla listelendi. Aynı malzeme için farklı
kaynaklar farklı sabitler verir (malzeme partisi, test tipi — çekme / burulma / basma, uydurma
aralığı); bir seti başka bir partiye taşımak mühendisin değerlendirmesidir.

## Model ve birimler (OpenRadioss LAW2 ile)

Johnson–Cook akma gerilmesi:

σ = (A + B·εₚⁿ) · (1 + C·ln ε̇*) · (1 − T*ᵐ),  ε̇* = ε̇ / ε̇₀,  T* = (T − T_r) / (T_m − T_r)

Arayüzdeki LAW2 kartına eşleme (3 · Material → LAW2): **σy = A** (alan Pa — MPa × 10⁶),
**b = B** (MPa), **n**, **c = C**, **ε̇₀** (1/s), **m**, **T_melt = T_m** (K), **T_r** (K),
**ρCp** = yoğunluk × özgül ısı (J/m³K). Sıcaklık terimi kullanılacaksa ρCp ve T_r girilmeli
(adyabatik ısınma). Kopma sabitleri (D₁–D₅) → /FAIL/JOHNSON kartı.

## Doğrulanan setler

### Johnson & Cook (1983) — orijinal tablo

Kaynak: G. R. Johnson, W. H. Cook, *A constitutive model and data for metals subjected to large
strains, high strain rates and high temperatures*, 7th International Symposium on Ballistics
(1983), bildiri P4.5 (Honeywell / Air Force Armament Laboratory) — **Table 1** (sayfa
görüntüsünden okundu; açık kopya: archive.org "A Constitutive Model And Data For Metals").
ε̇₀ = 1.0 s⁻¹ (makalede belirtilmiş), T_r = oda sıcaklığı. Sabitler burulma, statik çekme,
Hopkinson çekme ve yüksek sıcaklık Hopkinson verisinden.

| Malzeme | ρ (kg/m³) | c_p (J/kgK) | T_m (K) | A (MPa) | B (MPa) | n | C | m |
|---|---|---|---|---|---|---|---|---|
| 2024-T351 alüminyum | 2770 | 875 | 775 | 265 | 426 | 0.34 | 0.015 | 1.00 |
| 7039 alüminyum | 2770 | 875 | 877 | 337 | 343 | 0.41 | 0.010 | 1.00 |
| 1006 çelik | 7890 | 452 | 1811 | 350 | 275 | 0.36 | 0.022 | 1.00 |
| 4340 çelik (C-30) | 7830 | 477 | 1793 | 792 | 510 | 0.26 | 0.014 | 1.03 |
| Armco demir | 7890 | 452 | 1811 | 175 | 380 | 0.32 | 0.060 | 0.55 |

Not: 4340 için ikincil kaynaklarda farklı m (ör. 0.55) ve farklı A / B görülür; yukarıdaki
satır orijinal tablodandır (sertlik Rockwell C-30).

### Lesuer (1999) — 2024-T3 (LLNL, uçak motoru parçacık çarpması programı)

Kaynak: D. Lesuer, *Experimental Investigations of Material Models for Ti-6Al-4V and 2024-T3*,
Lawrence Livermore National Laboratory, **UCRL-ID-134691**, 3 Mayıs 1999 — **Table 8** (yeni
sabitler, LLNL Hopkinson çubuğu verisi; C ve m literatür + LLNL verisi) ve **Table 7** (fiziksel
özellikler). Sayfa görüntüsünden okundu (UNT Digital Library kopyası).

| Malzeme | A (MPa) | B (MPa) | n | C | m | D₁ | D₂ | D₃ | D₄ | D₅ |
|---|---|---|---|---|---|---|---|---|---|---|
| 2024-T3 | 369 | 684 | 0.73 | 0.0083 | 1.7 | 0.13 | 0.13 | −1.5 | 0.011 | 0.0 |

Table 7: 2024-T3 T_m = 502 °C (775 K), ρ = 2770 kg/m³, c_p = 875 J/kgK. Aynı raporun Table 6'sı
2024-T351 için 1983 sabitlerini (265 / 426 / 0.34 / 0.015 / 1) ve D₁–D₅ = 0.13 / 0.13 / −1.5 /
0.011 / 0.0 verir. ε̇₀ raporda Johnson–Cook tanımıyla (1 s⁻¹) kullanılır.

### Brar, Joshi, Harris (2009) — 7075-T651 ve 7075-T6

Kaynak: N. S. Brar (UDRI), V. S. Joshi (NSWC Indian Head), B. W. Harris (UDRI), *Constitutive
Model Constants for Al7075-T651 and Al7075-T6*, APS Shock Compression of Condensed Matter 2009;
AIP Conference Proceedings 1195, 945 (2009). Değerler **yazarların özet metninden** (APS
toplantı arşivi); tam bildiri metni okunmadı. Sabitler oda sıcaklığı ile 250 °C arası çekme
eğrilerinden uydurulmuş; özette ε̇₀ ve T_m yazılı değil.

| Malzeme | A (MPa) | B (MPa) | n | C | m |
|---|---|---|---|---|---|
| 7075-T651 | 527 | 676 | 0.71 | 0.017 | 1.61 |
| 7075-T6 | 546 | 674 | 0.72 | 0.059 | 1.56 |

Uyarı (veri): 7075-T6 için çevrimiçi örneklerde bu bildiriye atıfla farklı bir set dolaşıyor
(B 678, n 0.71, C 0.024). Özet metniyle uyuşmuyor; kullanmadan önce tam bildiri kontrol edilmeli.

## Doğrulanmadı — sayı yazılmadı

| Malzeme grubu | Durum | Bakılacak birincil kaynak (öneri değil, iz) |
|---|---|---|
| 6061-T6 | Yaygın atıflı set (Lesuer, Kay, LeBlanc 2001) birincil kaynakta okunamadı | LLNL UCRL-JC-134118 (2001); Scapin & Manes, Mater. Sci. Eng. A (2018) |
| 5xxx (ör. 5083-H116) | Aranmadı / okunmadı | Clausen, Børvik, Hopperstad, Benallal, Int. J. Plasticity (2004) — Voce tipi pekleşme, JC değil |
| DP590 / DP600 | Sabitler özetlerde yok | Vedantam, Bajaj, Brar, APS SCCM 2005; Thompson, Univ. of Waterloo tezi (DP600) |
| HSLA çelikler | Aranmadı | — |
| PP / ABS / PC | Aranmadı; termoplastiklerde JC yerine genelde tablolu (LAW36) ya da polimere özgü modeller | — |

Bu satırlar doldurulmadan kütüphaneye (1.24f) bu malzemeler için crash verisi girilmez.

## Belgenin kendisi

- Kaynaklar sayfa görüntüsünden ya da yazarların özet metninden okundu; hangisi olduğu her
  bölümde yazılı. Okuma tarihi 2026-10-15.
- Yeni set eklemek: birincil kaynak + tablo / sayfa no + okunduğu yer; ikincil kaynaktaki sayı
  "Doğrulanmadı"ya gider.
