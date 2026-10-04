# Crash validasyon seti — 1.17f (2026-10-04)

Üretici: `backend/scripts/crash_validation.py` (çalışan backend'e senaryo koşuları
gönderir). Ham veri: `crash_validation.json`. **Kabul kriteri yok** — oranlar
veridir; eşikler mühendisin kararıdır.

Ortak kurulum: `crash_box_shell` 300 × 50 × 40 mm, t = 3 mm (orta yüzey
47 × 37 mm, kesit alanı A = 2·(47+37)·3 = 504 mm²), S235 (ρ 7850 kg/m³,
E 210 GPa, ν 0.3, σy 235 MPa), v0 = 10 m/s, rijit duvar x = 0, kabuk 5 mm quad
(V3'te 5 / 4 / 3 / 2.5 mm).

## V1 — Elastik kutu rijit duvara (LAW1), 0.4 ms, TH 0.001 ms — koşu #51

| Büyüklük | Sim | Referans | Oran |
|---|---|---|---|
| Plato kuvveti (kN) | 204.54 | ρ·c₀·v·A = 204.63 (c₀ = √(E/ρ) = 5172 m/s) | 0.9995 |
| — | | ρ·c_p·v·A = 214.51 (c_p = √(E/(ρ(1−ν²)))) | 0.954 |
| Temas süresi (ms) | 0.1182 | 2L/c₀ = 0.1160 | 1.019 |
| Duvar impulsu (N·s) | 22.93 | 2·M·v0 = 23.74 (tam elastik geri sekme) | 0.966 |

Enerji dengesi 0.51 %, hourglass / IE_son 8.4 % (IE_son küçük — elastik geri
sekme sonrası).

Gözlem: plato çubuk dalga hızıyla (c₀) neredeyse birebir; levha hızı (c_p)
%4.6 uzak — ince cidarlı kutu eksenel dalgada çubuk gibi davranıyor.

## V2 — Elasto-plastik kutu (LAW2, σy 235 MPa), 0.4 ms — koşu #52

| Büyüklük | Sim | Referans | Oran |
|---|---|---|---|
| Plato kuvveti (kN) | 118.89 | σy·A = 118.44 | 1.004 |
| Duvar impulsu (N·s) | 14.39 | M·(v0 + v_son) = 14.78, v_son = √(2·KE_son/M) | 0.974 |
| Temas süresi (ms) | 0.124 | — (plastik dalga; basit analitik yok) | — |

Enerji dengesi 0.07 %, hourglass / IE 0.08 %.

## V3 — Kızaklı eksenel ezilme + mesh yakınsaması — koşular #53–#56

Rijit gövde `kutu_arka` + 50 kg (TEST değeri — Pm teoride kütleden bağımsız;
gerçek kızak kütlesi mühendisin), 15 ms, TH 0.01 ms. Ezilme δ = ∫(v0 − I(t)/M) dt
(duvar impulsundan, mesh'ten bağımsız), Pm = IE(durma) / δ.

Referans (açık literatür), C = (47+37)/2 = 42 mm, σ0 = σy:
- Wierzbicki & Abramowicz (1983): Pm = 9.56·σ0·t^(5/3)·C^(1/3) = **48.73 kN**
- Abramowicz & Jones (1984, etkin ezilme mesafesi dahil): 13.06·… = **66.57 kN**

| Eleman (mm) | δ (mm) | Durma (ms) | Pm = IE/δ (kN) | /W&A | /A&J | Tepe (kN) | HG/IE | Süre (s) |
|---|---|---|---|---|---|---|---|---|
| 5.0 | 41.1 | 8.53 | 59.53 | 1.222 | 0.894 | 126.7 | 0.046 | 39 |
| 4.0 | 41.6 | 8.36 | 59.01 | 1.211 | 0.886 | 127.3 | 0.043 | 83 |
| 3.0 | 43.8 | 8.73 | 56.36 | 1.157 | 0.847 | 127.4 | 0.038 | 167 |
| 2.5 | 43.9 | 9.41 | 55.97 | 1.148 | 0.841 | 127.1 | 0.039 | 228 |

Enerji dengesi her koşuda ≤ 0.18 %.

Gözlem (veri): Pm mesh inceldikçe 59.5 → 56.0 kN, 3 → 2.5 mm farkı %0.7
(yakınsıyor); iki literatür formülünün arasında. Yarım katlanma dalga boyu
H ≈ 0.99·t^(1/3)·C^(2/3) ≈ 17 mm — 5 mm elemanla dalga başına ~3.4 eleman.
Dikdörtgen kesitte C = (b+d)/2 kullanımı ve formüllerin (statik, kare tüp)
geçerlilik varsayımları mühendis tarafından değerlendirilmeli.

## 1.18e — Plaka–küre (2026-10-04)

`scripts/crash_validation.py --only V4,V5` (rapor JSON'unda diğer vakalar korunur).
Kabul kriteri yok — oranlar veri.

### V4 · Elastik yarı-statik (koşu #72)

S235 LAW1, plaka 300 × 300 × 5 (kenarlar /BCS 111111), küre D50 + 50 kg TEST
kütlesi (toplam 50.34 kg), 1 m/s, eleman 5 mm. Referans: ankastre kare plaka
merkez yükü (Timoshenko & Woinowsky-Krieger, α = 0.00560, ν = 0.3)
k = D/(α·a²) = 4770 N/mm; kütle–yay F = v·√(k·m), δ = v·√(m/k), T = π·√(m/k).
Varsayım: küre kütlesi ≫ plaka etkin kütlesi (plaka 3.5 kg).

| büyüklük | sim | referans | oran |
|---|---|---|---|
| Temas tepe kuvveti, ham (kN) | 20.85 | 15.50 | 1.346 |
| Temas tepe kuvveti, CFC60 (kN) | 15.13 | 15.50 | 0.977 |
| Küre en büyük ilerlemesi (mm) | 3.268 | 3.249 | 1.006 |
| Temas süresi (ms) | 10.30 | 10.21 | 1.009 |
| Temas impulsu (N·s) | 99.57 | 100.68 (2·m·v0) | 0.989 |

Enerji dengesi 0.021, hourglass / IE 0.222 (Ishell 0). Ham tepe plaka
modlarının yüksek frekanslı salınımını taşır; yarı-statik tepe (temel ~50 Hz)
CFC60 ile. Kontrol koşusu #73 (aynı, Ishell 24): HG / IE 0, denge 0.0056,
CFC60 tepe 14.56 kN (0.940), impuls 96.23 (0.956) — rapora girmedi, veri.

### V5 · Recht–Ipson uydurması (1.18d tarama, TEST değerleri)

v_r = a·√(v0² − v_bl²), v_r² ~ v0² en küçük kareler, delinmiş 4 nokta
(50–200 m/s): a = 0.988, v_bl = 28.75 m/s, R² = 0.9998; v_bl tarama
aralığında (25 geri sekti – 50 delindi). Nokta oranları 0.928 (50 m/s,
eşiğe yakın), 1.007, 1.006, 0.998. Tutarlılık verisidir; delinmenin mutlak
doğruluğu malzeme / FAIL verisine bağlı — deney benchmark'ı mühendisin seçimi.

## K1 — Taylor çubuğu (2026-10-04)

### V6 · Rijit duvara dolu silindir (koşular #75–#77)

`taylor_bar` L0 50 / D0 10 mm, S235 LAW2 (σy 235 MPa, b = 0), solid tet4
(Gmsh'te bu geometride hex seçeneği tet üretti — ölçüldü), rijit duvar x = 0,
0.5 ms. Son şekil animasyonun son karesinden (yalnız yüz düğümleri).
Referans: Wilkins & Guinan (1973) L1/L0 = h/L0 + (1 − h/L0)·exp(−ρ·v0²/(2·σ0)),
h = 0 alt sınır (h deneysel). Kabul kriteri yok.

| v0 m/s | eleman mm | koşu | L1/L0 sim | WG (h = 0) | oran | D1/D0 | impuls oranı |
|---|---|---|---|---|---|---|---|
| 100 | 1.5 | #75 | 0.8675 | 0.8462 | 1.025 | 1.289 | 0.999 |
| 150 | 1.5 | #76 | 0.7356 | 0.6867 | 1.071 | 1.584 | 0.999 |
| 100 | 1.0 | #77 | 0.8678 | 0.8462 | 1.026 | 1.312 | 0.996 |

Mesh 1.5 → 1.0 mm: L1/L0 değişimi 0.0003 (yakınsamış). Oranın > 1 olması h = 0
alt sınırla tutarlı (h > 0 L1/L0'ı artırır). Enerji dengesi ≤ 0.0007, HG/IE 0.

## K2 — Düşme testi (2026-10-04)

### V7 · 1 m düşme, yüzey + köşe (koşular #80, #81)

`drop_box_shell` 200 × 150 × 50 kapalı kabuk, t 2, S235 LAW2, eleman 10 mm,
zemin rijit duvar z = 0, /GRAV −9.81 m/s² Z (yeni kart, hm_cfg r51), H 1000 mm
→ v0 = √(2·g·H) = 4.429 m/s, boşluk 1 mm, 5 ms. Ağırlık merkezi hızı TH
/PART VZ. Kabul kriteri yok.

| büyüklük | yüzey #80 | köşe #81 |
|---|---|---|
| KE₀ / m·g·H | 1.0006 | 1.0013 |
| Temas anı sim / serbest düşme (0.2257 ms) | 1.0002 | 0.9996 |
| Zemin impulsu / [m·(vz_son − vz₀) + m·g·t] | 0.9997 | 1.0003 |
| Tepe kuvvet (kN) | 471.6 | 11.0 |
| Enerji dengesi | 0.071 | 0.005 |
| HG / IE | 0.165 | 0.058 |

Yüzey düşmesinde tüm taban aynı anda rijit duvara vurur (çok kısa, sert
darbe): enerji dengesi %7.1 — momentum yine tutuyor. Veri; düzeltme /
eleman seçimi mühendisin.

## K3 — Direk yan çarpması (2026-10-04)

### V8 · Ø254 silindirik rijit direk (koşular #83, #84)

`pole_beam_shell` L 800, h 60 (çarpma yönü), b 40, t 2 kabuk tüp, S235 LAW2;
uç halkaları rijit gövde + 10 kg TEST kütlesi (her biri, toplam 22.41 kg),
5 m/s; direk /RWALL/CYL (yeni kart, hm_cfg radioss110 r51) eksen z, Ø254,
kirişin ortasında. δ ve durma anı duvar impulsundan (V3 deseni), Pm = IE/δ.
Referans rijit-plastik üç nokta eğilme P = 4·Mp/L, Mp = σy·Zp, Zp = 7772 mm³
→ 9.13 kN. Kabul kriteri yok.

| eleman mm | koşu | δ mm | Pm kN | Pm / 4Mp/L | impuls oranı | denge | HG/IE |
|---|---|---|---|---|---|---|---|
| 10 | #83 | 36.7 | 7.35 | 0.805 | 0.999 | 0.002 | 0.036 |
| 7.5 | #84 | 39.1 | 6.89 | 0.755 | 0.999 | 0.0006 | 0.038 |

İnce cidarlı kesit direk altında yerel ezilip burkulur (kesit çökmesi);
kiriş teorisi bunu içermez — oran < 1 ve mesh incelince düşüyor (yakınsamadı;
5 mm adımı veri için açık). Uyarı 446: uç rijit gövde düğümleri (40) rijit
duvardan çıkarıldı (Ikrem = 0) — direğe değmiyorlar.

## K4 — ROPS portal yanal yavaş itme (2026-10-04)

### V9 · bükülmüş tüp portal (koşular #86, #87)

`rops_frame_shell` W 1000, H 1200, kesit 80 × 60 t 4, büküm R 150, S235
LAW2; tabanlar /BCS 111111, dikme 1 üst bükümü rijit gövde + /IMPVEL +y
1 m/s, 100 ms (δ = v·t = 100 mm); kuvvet iki dikmeyi z = H/2'de kesen
/SECT'ten. Hareketli parça yok (yeni: yük yalnız zorlanmış hızdan). Mp =
σy·t·(d·e + d²/2) = 7.520 kN·m. Kabul kriteri yok; ISO 3471 mühendisin.

| eleman mm | koşu | plato δ 40–95 (kN) | / 4Mp/H (25.07) | / 4Mp/(H − R) (28.65) | ∫F dδ / (IE + HG) | denge | HG/IE |
|---|---|---|---|---|---|---|---|
| 15 | #86 | 28.53 | 1.138 | 0.996 | 1.005 | 0.0002 | 0.008 |
| 10 | #87 | 28.09 | 1.120 | 0.980 | 1.005 | 0.0002 | 0.006 |

Mafsallar taban ve rijit büküm altında (dikme üstü, z ≈ H − R) oluşur —
deforme şekilde plastik bölgeler orada; plato 4·Mp/(H − R) ile örtüşüyor.
Emilen enerji 100 mm'de ~2.7 kJ. Düzeltme: zorlanmış hızla sürülen koşuda
enerji dengesi paydası KE₀ ≈ 0 olduğundan oran hep 1 çıkıyordu → payda
sorunun enerji ölçeği (en büyük IE / KE / |dış iş|); eski IMPVEL koşuları
(1.17c) yeniden işlendi (0.023 → 0.0004).

## K5 — Kaput / kafa impaktörü (2026-10-04)

### V10 · Ø165 / 4.5 kg, 11.1 m/s (koşu #88)

`plate_ball_shell` (katalog örneği `head_impactor`): kaput 600 × 600 × 0.8
S235 LAW2 (kenar sabit), kafa formu rijit küre Ø165 kabuk 1 mm + ek kütle
(toplam 4.5 kg: ek = toplam − π·D²·t·ρ); kafa ana düğüm ivmesi /TH/NODE
(yeni `th_accel`), CFC1000. Kabul kriteri yok; HIC eşiği mühendisin.

| büyüklük | sim | referans | oran |
|---|---|---|---|
| Kafa Δv: ∫\|a\| dt (m/s) | 14.348 | I/m = 14.355 | 0.9995 |
| Kütle 2·KE₀/v0² (kg) | 4.498 | 4.5 | 0.9995 |
| HIC15 ham / CFC1000 | 4795 / 4782 | — | — |
| Tepe ivme CFC1000 (g) | 355 | — | — |

İvme kanalı momentumla tutarlı (Δv). HIC yüksek: kenarı sabit düz sac,
altında boşluk / motor yok — gerçek kaput rijitliği ve destek noktaları
mühendisin. Enerji dengesi 0.0035, HG/IE 0.002.

## K6 — FOPS düşen cisim (2026-10-04)

### V11 · 227 kg Ø250 küre, H 5.21 m (koşu #89)

`plate_ball_shell` (katalog örneği `fops`): tavan 1200 × 1200 × 6 S235 LAW2
(kenar sabit), rijit küre Ø250 kabuk 2 mm, toplam 227 kg, H 5210 mm → v0 =
10.11 m/s, KE₀ = m·g·H = 11.6 kJ, /GRAV −9.81 Z, 40 ms. ISO 3449 kriterleri
(DLV girişi vb.) mühendisin.

| büyüklük | sim | referans | oran |
|---|---|---|---|
| KE₀ (J) | 11606 | m·g·H = 11602 | 1.0003 |
| Temas anına kadar düşülen mesafe (mm) | 2.24 | — (orta yüzeyler arası 5 mm − TYPE7 temas boşluğu) | — |
| Cisim en büyük ilerlemesi (mm) | 97.0 | — | — |
| Tavan iç enerjisi (J) | 11123 | — | — |

Not: temas geometrik g = 1 mm'de değil, kabuk orta yüzeyleri ve TYPE7 temas
boşluğuna göre başlıyor (kalınlıkların yarısı) — veri. Enerji dengesi
0.0004, HG/IE 0.001.

## K7 — S-kiriş (2026-10-04)

### V12 · kılavuzlu kızak 50 kg, 5 m/s (koşu #92)

`s_rail_shell` L1 100, L2 200, R 150, θ 45°, kesit 60 × 40 t 2, S235 LAW2,
eleman 8 mm; ön uç rijit duvar x = 0, arka halka kızak (rijit gövde 50 kg
TEST) — kızak yalnız x'te serbest (/BCS ana düğüm 011111, yeni: BCS rijit
gövdeye). Yönlendirmesiz ilk koşu (#90, 10 m/s) yana kırılıp dönerek
duvardan ayrıldı (enerjinin ~%20'si emildi) — gerçek testte kızak
kılavuzludur. 45 ms sonunda kızak hâlâ 0.71 m/s ileri gidiyor.

| büyüklük | sim | referans | oran |
|---|---|---|---|
| Duvar impulsu (N·s) | 222.0 | M·(v0 − v_son) = 221.7 | 1.001 |
| Ortalama kuvvet IE/δ (kN) | 6.05 | düz tüp W&A 25.92 | 0.234 |
| δ (mm) / tepe kuvvet (kN) | 95.3 / 81.1 | — | — |

Ortalama kuvvet aynı kesitli düz tüpün eksenel ezilmesinin ~%23'ü: S kiriş
ikinci bükümde plastik mafsalla eğilerek çöker (eksenel katlanma yok) —
beklenen davranış, veri. Enerji dengesi 0.0002, HG/IE 0.097.

## K8 — Kapı intrüzyonu (2026-10-04)

### V13 · darbe kirişi + Ø305 silindir, yavaş itme (koşu #95)

`door_beam_shell` kiriş L 800, 40 × 30 t 1.5 S235 LAW2, uçlar ankastre;
impaktör yarım silindir Ø305 (rijit gövde, yalnız x — /BCS 011111 ana
düğüm) zorlanmış +x 1 m/s, 120 ms; TYPE7 impaktör → kiriş. Kılavuzsuz ilk
koşular (#93 TYPE7, #94 TYPE24) eğri temasta z'ye kayıp dönerek ~25 mm'de
kirişten ayrıldı (kuvvet 0) — temas tipi değil kılavuz eksikti.

| büyüklük | sim | referans | oran |
|---|---|---|---|
| Kuvvet platosu δ 5–20 mm (kN) | 6.83 | 8·Mp/L = 6.48 | 1.054 |
| ∫F dδ (J) | 1685 | IE + HG = 1688 | 0.998 |
| Kuvvet δ 120 mm (kN) | 24.96 | — (membran sertleşmesi) | — |

Enerji dengesi 0.00005, HG/IE 0.008. FMVSS 214 kriterleri mühendisin.

## K9 — Hopkinson çubuğu (2026-10-05)

### V14 · çarpıcı → giriş çubuğu, 10 m/s (koşu #96)

`hopkinson_bar` Ø20, çarpıcı Ls 100, giriş Li 500, boşluk 0.5 mm; S235
elastik LAW1, tet4 3 mm; giriş çubuğu serbest, çarpıcı → giriş TYPE7, kuvvet
x = Li/4 kesitinden (yansıma dönmeden); TH 0.5 µs. c₀ = √(E/ρ) = 5172 m/s.

| büyüklük | sim | referans | oran |
|---|---|---|---|
| Kesit kuvveti platosu (kN) | 62.69 | ρ·c₀·v0·A/2 = 63.78 | 0.983 |
| Darbe süresi, yarı genlik (ms) | 0.0376 | 2·Ls/c₀ = 0.0387 | 0.972 |
| Dalga yolu temas → Li/4 (ms) | 0.0254 | (Li/4)/c₀ = 0.0242 | 1.051 |

Enerji dengesi 0.005, HG 0. Temas, geometrik 0.5 mm boşluk tam kapanmadan
(TYPE7 boşluğu) başlıyor — varış süresi temas anından ölçüldü.

## K10 — Patlama yüklü plaka (2026-10-05)

### V15 · Friedlander darbesi (koşular #99 ankastre, #100 serbest kontrol)

`blast_plate_shell` 400 × 400 × 3 S235 LAW2; /PLOAD (yeni kart, hm_cfg
radioss2021) plaka kabuk yüzeyine Friedlander p(t) = Ps(1 − t/td)e^(−b·t/td),
Ps 2 MPa, td 0.2 ms, b 1; uygulanan impuls A·∫p dt = 23.544 N·s (kapalı form).

| büyüklük | sim | referans | oran |
|---|---|---|---|
| Serbest plaka momentumu t = td (N·s) (#100) | 23.551 | 23.544 | 1.0003 |
| Ankastre plaka momentumu t = td (N·s) | 15.32 | 23.544 | 0.651 (veri) |
| En büyük çökme (mm) / son kare (mm) | 8.4 / 1.3 | — | — |
| Plaka iç enerjisi son (J) | 53.1 | — | — |

Basınç kartı ve Friedlander fonksiyonu doğru (serbest plakada momentum =
impuls). Ankastre kenarlar darbe sırasında momentumun ~1/3'ünü mesnetlere
aktarır — fiziksel, veri. Bu yükte yanıt büyük ölçüde elastik (8.4 mm → 1.3
mm). Kalıcı çökme referansı (Nurick vb.) mühendisin.

## K11 — Kepçe / taş darbesi (2026-10-05)

### V16 · taş Ø200 / 300 kg, 5 m/s (koşu #101)

`bucket_rock_shell` kavisli taban R 500, φ 90°, W 600, t 10 S235 LAW2
(uzun kenarlar sabit), taş rijit küp-küre Ø200 kabuk 2 mm, toplam 300 kg,
−z 5 m/s, eleman 20 mm, 20 ms; taş ana düğüm ivmesi TH'de.

| büyüklük | sim | referans | oran |
|---|---|---|---|
| Taş Δv: ∫\|a\| dt (m/s) | 7.783 | I/m = 7.680 | 1.013 |
| Taş kütlesi 2·KE₀/v0² (kg) | 299.99 | 300 | 1.000 |
| Taş en büyük ilerlemesi (mm) | 8.8 | — | — |
| Taban iç enerjisi (J) / temas tepe (kN) | 2751 / 1242 | — | — |

Taş ~2.7 m/s geri sekiyor. Enerji dengesi 0.037 (kalın sac + rijit taş,
sert temas tepesi 1242 kN — eleman 20 mm kaba); HG/IE 0.008. Veri.

## K12 — Kuş çarpması, SPH (2026-10-05)

### V17 · 1.82 kg kuş, 150 m/s (koşular #104 ankastre plaka, #105 rijit hedef)

Yeni: SPH mermi — kapsül (silindir + yarım küreler) içinde kübik kafes
parçacıklar, /SPHCEL + /PROP/SPH (hm_cfg r2019) + /MAT/HYDRO (LAW6, P = C1·μ,
C1 2.2 GPa, ρ 950, Pmin −0.1 MPa), SPH düğümleri → hedef yüzeyi TYPE7.
Kuş 1.82 kg, L/D 2 → Ø113.5 × L227.1 mm, aralık 11.4 mm; plaka 600² × 6
S235 ankastre. Wilbeck bağıntıları rijit hedef içindir (kontrol #105: plakanın
tüm düğümleri sabit).

| büyüklük | sim | referans | oran |
|---|---|---|---|
| Rijit hedef: kararlı akış kuvveti (kN) | 204.5 | ρ·A·v² = 216.4 | 0.945 |
| Rijit hedef: darbe süresi (ms) | 1.398 | L/v = 1.514 | 0.924 |
| Rijit hedef: aktarılan impuls (N·s) | 290.5 | m·v = 277.3 | 1.047 |
| Kuş kütlesi (SPH kafes) (kg) | 1.849 | 1.82 | 1.016 |
| Ankastre plaka: akış kuvveti / süre / impuls | 170.9 / 2.49 / 308.8 | — | 0.79 / 1.64 / 1.11 (veri) |

Tepe kuvveti (Hugoniot evresi) ~1.5–2.1 MN (veri). Enerji dengesi 0.009.
Not: deforme şekil görüntüleyici yalnız yüzeyleri çizer — SPH parçacıkları
animasyonda görünmez (kuvvet / enerji grafikleri tam).

## K13 — Mayın / araç altı patlama, ampirik PBLAST (2026-10-05)

### V18 · 6 kg TNT eşdeğeri, 500 mm (koşular #108–#110)

Yeni: /LOAD/PBLAST (hm_cfg radioss2022, TM5-1300 / Kingery–Bulmash, zemin
yansımalı yarım küre — OpenRadioss hesaplar). Yük yüzeyi /SURF/SEG ile her
segment patlama noktasına bakacak şekilde yönlendirilir (ilk koşu #106'da
kabuk normali uzağa bakıyordu, plaka yüke doğru itildi). Taban 1000² × 10
S235. Tam ALE (yakıt / hava / zemin etkileşimi) kapsam dışı.

| büyüklük | sim | referans | oran |
|---|---|---|---|
| İmpuls oranı (W, R, a) / (W/8, R/2, a/2) | 8.000 | 8 (Hopkinson–Cranz) | 1.000 |
| Varış süresi oranı | 2.000 | 2 (t ∝ W^1/3) | 1.000 |
| Serbest plaka impulsu 6 kg (N·s) | 5335 | — | — |
| Ankastre taban en büyük çökme (mm) | 182.6 | — | — |
| Ankastre taban iç enerjisi (kJ) | 205.6 | — | — |

Ölçekleme birebir: PBLAST'ın ampirik yasası ölçekten bağımsız olduğu için bu
test kurulumun (birim, koordinat, yüzey yönü) tutarlılığını doğrular;
ampirik modelin deneye göre doğruluğu ayrı benchmark ister (mühendisin).
