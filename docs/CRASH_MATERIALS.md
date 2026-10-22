# Crash malzeme verisi — açık literatür (1.24e)

> Yalnız doküman. Kütüphaneye giriş ayrı adım (1.24f `crash_jc`; ek setler sonraki seed adımı). Ticari / lisanslı
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

## Doğrulanan setler — ek (2026-10-22)

Aynı kural: birincil kaynağın kendi tablosundan / metninden okundu (tam metin; taranmış
raporlarda OCR, şüpheli rakam şekil etiketiyle karşılaştırıldı). Birim MPa, K; "—" kaynakta yok.

### Lesuer (1999) — Ti-6Al-4V (UCRL-ID-134691, Table 6 / 7 / 8)

Aynı rapor (yukarıda 2024-T3). Table 8 "yeni" sabitler (LLNL Hopkinson, ~5000 1/s), Table 6
orijinal Johnson / NSWC seti; Table 7 fiziksel. T* = (T − 298)/(T_m − 298), ε̇₀ = 1 s⁻¹. FAA
yayını DOT/FAA/AR-00/25 (2000) Table 8 aynı değerler.

| Set | A | B | n | C | m | D₁ | D₂ | D₃ | D₄ | D₅ |
|---|---|---|---|---|---|---|---|---|---|---|
| Ti-6Al-4V (Table 8, yeni) | 1098 | 1092 | 0.93 | 0.014 | 1.1 | −0.09 | 0.25 | −0.50 | 0.014 | 3.87 |
| Ti-6Al-4V (Table 6, orijinal) | 862 | 331 | 0.34 | 0.012 | 0.8 | −0.09 | 0.25 | −0.5 | 0.014 | 3.87 |

Table 7: T_m = 1878 K, T_r = 298 K, ρ = 4428 kg/m³, c_p = 580 J/kgK (AMS 4911, tavlı).

### Kay (2003) — Ti-6Al-4V ve 2024-T3 kopma yeniden kalibrasyonu (DOT/FAA/AR-03/57)

G. Kay, *Failure Modeling of Titanium 6Al-4V and Aluminum 2024-T3 With the Johnson-Cook
Material Model*, DOT/FAA/AR-03/57 (LLNL), Eylül 2003 — Ti s. 6–7, 2024-T3 s. 13 (numaralı tablo
yok, metin). Dayanım sabitleri Lesuer Table 8 ile aynı; yalnız D₁–D₃ yeniden uydurulmuş (D₄, D₅
önceki çalışmadan). Ti: çentikli Hopkinson çekme (4300–6800 1/s) + kanat parçası çarpma
doğrulaması; 2024-T3: 1/3 ölçek balistik limit.

| Set | D₁ | D₂ | D₃ (Kay işareti) | D₃ (σ* = σm/σeq) | D₄ | D₅ |
|---|---|---|---|---|---|---|
| Ti-6Al-4V | −0.090 | 0.270 | +0.480 | **−0.48** | 0.014 | 3.870 |
| 2024-T3 | 0.112 | 0.123 | +1.500 | **−1.5** | 0.007 | 0.0 |

**İşaret uyarısı:** Kay σ*'ı basınç / eşdeğer gerilme olarak tanımlar (standart üç eksenliliğin
tersi). /FAIL/JOHNSON için standart işaret (σm/σeq) sütunu kullanılır.

### Lesuer, Kay, LeBlanc (2001) — 6061-T6 (UCRL-JC-134118, Table 1)

*Modeling Large-Strain, High-Rate Deformation in Metals*, UCRL-JC-134118 (Third Biennial Tri-Lab
Engineering Conf., 1999) — Table 1 (OSTI 15005327). Yaygın kopyalanan 6061-T6 setinin birincil
yeri; makale sabitlerin kökenini yazmaz (muhtemelen Johnson & Holmquist 1989) ve JC modelinin
6061-T6'da ~10³ 1/s üstünde yetersiz kaldığını raporlar. ε̇₀ = 1 s⁻¹ ("typically").

| Malzeme | A | B | n | C | m | D₁ | D₂ | D₃ | D₄ | D₅ |
|---|---|---|---|---|---|---|---|---|---|---|
| 6061-T6 | 324 | 114 | 0.42 | 0.002 | 1.34 | −0.77 | 1.45 | −0.47 | 0.0 | 1.60 |

T_m, T_r, ρ, c_p kaynakta yok.

### Chen ve ark. (2017) — 6082-T6 haddelenmiş sac (PLoS ONE, CC BY)

X. Chen, Y. Peng, S. Peng, S. Yao, C. Chen, P. Xu, *Flow and fracture behavior of aluminum
alloy 6082-T6 at different tensile strain rates and triaxialities*, PLoS ONE 12(7): e0181983
(2017), doi:10.1371/journal.pone.0181983 — Table 3 (dayanım), Table 5 (m, fiziksel), Table 7
(D₁–D₃). Çekme 10⁻⁴–3400 1/s, yalnız oda sıcaklığı. **ε̇₀ = 10⁻⁴ s⁻¹** (alışılmadık; C buna göre).

| Malzeme | A | B | n | C | ε̇₀ | m | D₁ | D₂ | D₃ |
|---|---|---|---|---|---|---|---|---|---|
| 6082-T6 (kalibre) | 277.33 | 307.93 | 0.69 | 0.0032 | 1e-4 | 1.28 | 0.21125 | 3.91116 | −4.72526 |
| 6082-T6 (yaygın yöntem) | aynı | aynı | aynı | aynı | aynı | aynı | 0.26862 | 9.20158 | −10.6552 |

Table 5: ρ = 2710 kg/m³, c_p = 960 J/kgK, E = 71 GPa, ν = 0.3. D₄ / D₅ yok (sıcaklık test edilmedi).

### Gray ve ark. (1994) — 5083 (LANL LA-12669-MS, Şekil 11–16)

G. T. Gray III, S. R. Chen, W. Wright, M. F. Lopez, *Constitutive Equations for Annealed Metals
Under Compression at High Strain Rates and High Temperatures*, LA-12669-MS (1994) — sabitler
şekil altlarında (s. 20–25; taranmış kopya, OCR). Hopkinson basma 0.001–7000 1/s, −196…200 °C;
temper belirtilmemiş, T_m = 933 K. Yalnız orijinal T* = (T − 298)/(T_m − 298) kullanan iki
uydurma OpenRadioss LAW2 ile uyumlu (diğer dördü T/T_m kullanır, buraya yazılmadı):

| Uydurma | A | B | n | C | m |
|---|---|---|---|---|---|
| Şekil 14 — oda sıcaklığı ve üstü, tüm hızlar | 270 | 470 | 0.6 | 0.0105 | 1.2 |
| Şekil 16 — oda sıcaklığı üstü, yüksek hız | 170 | 425 | 0.42 | 0.0335 | 1.225 |

Yazarlar oda sıcaklığında dinamik yaşlanma (DSA) raporlar. Aynı rapor OFE bakırda JC'nin
uymadığını yazar (bakır seti yok).

### Holmquist (1987) — HY-80 / HY-100 / HY-130 (NSWC TR 88-252, Table 1–2)

T. J. Holmquist, *Strength and Fracture Characteristics of HY-80, HY-100, and HY-130 Steels
Subjected to Various Strains, Strain Rates, Temperatures, and Pressures*, NSWC TR 88-252
(DTIC AD-A233061), 1987 — Table 2 (s. 33) sabitler, Table 1 fiziksel; taranmış kopya. HY-80 C
değeri tabloda OCR'da bozuk; şekil eğri etiketinden ("672 + 425 … 1 + .014 ln ε̇*") 0.014 okundu.
Burulma + Hopkinson çekme + çentikli çekme; ε̇₀ = 1 s⁻¹, sıcaklık oda sıcaklığına göre.
Deniz yapısı HSLA çelikleri (otomotiv sacı değil).

| Malzeme | A | B | n | C | m | T_m | D₁ | D₂ | D₃ | D₄ | D₅ | ρ | c_p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HY-80 | 672 | 425 | 0.36 | 0.014 | 1.14 | 1793 | −0.85 | 2.70 | −0.50 | 0.006 | 0.0 | 7746 | 502 |
| HY-100 | 758 | 402 | 0.26 | 0.011 | 1.13 | 1793 | −0.61 | 2.07 | −0.50 | 0.010 | 0.0 | 7748 | 502 |
| HY-130 | 920 | 333 | 0.39 | 0.008 | 1.15 | 1793 | −0.69 | 2.39 | −0.50 | 0.004 | 0.0 | 7885 | 489 |

E = 207 GPa, ν = 0.30 (Table 1).

### Ryu ve ark. (2025) — DP590 sac (Materials, CC BY)

J.-C. Ryu, M.-G. Kim, J.-Y. Seo, C.-J. Lee, D.-H. Shin, D.-C. Ko, *Structural Evaluation of
Steel/CFRP Hybrid Part Using Progressive Damage Model and Cohesive Zone Model*, Materials 18(23):
5382 (2025), doi:10.3390/ma18235382 — §2.2 metin. DP590 sac, ASTM E8 çekme 0.001–200 1/s, oda
sıcaklığı; ısıl terim yok. **ε̇₀ = 10⁻³ s⁻¹.**

| Malzeme | A | B | n | C | ε̇₀ |
|---|---|---|---|---|---|
| DP590 | 412.9 | 882.8 | 0.5233 | 0.025 | 1e-3 |

### Corona & Orient (2014) — 7075-T651, delinme kalibrasyonu (SAND2014-1550, Table 2–3)

E. Corona, G. Orient, SAND2014-1550 (Sandia, kamuya açık) — Table 3 (s. 41) + Table 2. Plaka
delinmesine kalibre; **ε̇₀ = 1.6e-4 s⁻¹**. D₁/D₂ için raporun "orta" durumu (düşük 0.025/0.15,
yüksek 0.005/0.34).

| Malzeme | A | B | n | C | ε̇₀ | m | D₁ | D₂ | D₃ | D₄ | D₅ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 7075-T651 | 517 | 405 | 0.41 | 0.0075 | 1.6e-4 | 1.1 | 0.015 | 0.24 | −1.5 | −0.039 | 8.0 |

E = 71.7 GPa, ν = 0.33, c_p = 960 J/kgK, T_m = 750 K, T_r = 293 K, ρ = 2810 kg/m³, Taylor–Quinney 0.95.

### Ortak uyarılar

- **ε̇₀ setler arasında farklı** (1, 10⁻³, 10⁻⁴, 1.6·10⁻⁴ s⁻¹) — C o referansla anlamlı; kart
  doldurulurken setin kendi ε̇₀'ı kullanılır.
- **D₃ işareti** kaynaklarda farklı tanımlanabilir; bu belgede tüm D₃ σ* = σm/σeq işaretiyle.

## Doğrulanmadı — sayı yazılmadı

| Malzeme grubu | Durum | Bakılacak birincil kaynak (öneri değil, iz) |
|---|---|---|
| OFHC bakır D₁–D₅ (ve 4340 / Armco D'leri) | Yalnız ikincil kaynakta; birincil ücretli | Johnson & Cook 1985, Eng. Fract. Mech. 21:31–48 |
| OFHC bakır dayanım | JC 1983 taramasında A, B, ρ okunamıyor (n .31, C .025, m 1.09 okunuyor) | JC 1983 Table 1 (daha iyi kopya) |
| 23 malzemelik derleme | Açık kopya bulunamadı | Johnson & Holmquist, LA-11463-MS (1989) |
| 5083-H116 (Børvik grubu) | İkincil kaynakta yuvarlanmış | Clausen, Børvik, Hopperstad, Benallal, MSEA 364 (2004) — ücretli |
| Weldox 460E | Açık kopya yok | Børvik ve ark., Eur. J. Mech. A/Solids 20 (2001) |
| DP600 / DP780 / DP980 | DP600 indirilemedi (telifli, basit JC); DP780/980 raporu "OFFICIAL USE ONLY / CRADA" damgalı — kullanılmadı | Topilla & Toros, Trans. FAMENA 47 (2023); PNNL-21604 |
| 304 / 316 paslanmaz (crash) | Açık birincil crash seti yok (bulunan 304 seti talaşlı işleme ters kalibrasyonu, CC BY-NC-ND) | — |
| AISI 1045 | Bulunan set sıcak şekillendirme (650–950 °C) — crash için değil | Murugesan & Jung, Materials 12:609 (2019) |
| PP / ABS / PC | Aranmadı; termoplastiklerde JC yerine genelde tablolu (LAW36) ya da polimere özgü modeller | — |

Bu satırlar doldurulmadan kütüphaneye bu malzemeler için crash verisi girilmez.

## Belgenin kendisi

- Kaynaklar sayfa görüntüsünden ya da yazarların özet metninden okundu; hangisi olduğu her
  bölümde yazılı. Okuma tarihi 2026-10-15; ek setler 2026-10-22.
- Yeni set eklemek: birincil kaynak + tablo / sayfa no + okunduğu yer; ikincil kaynaktaki sayı
  "Doğrulanmadı"ya gider.
