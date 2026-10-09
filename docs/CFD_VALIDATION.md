# CFD doğrulama (Faz 2.6)

Sonuçlar veridir; kabul ölçütü mühendisindir. Her vaka yeniden üretilebilir
(betik + parametreler aşağıda), koşular `cfd_runs` tablosunda kayıtlı.

## V-C1 — 2B kanal, laminer Poiseuille (Faz 2.3)

Re 10, L = 20H, 200 × 20 hücre (blockMesh), simpleFoam laminer: basınç düşümü
analitikten %+2.9 (girişteki gelişme bölgesi dahil, L_e ≈ 0.5H), en büyük hız
%−0.5. Test: `backend/tests/test_cfd_channel.py`.

## V-C2 — küre, düşük Re laminer dış akış (Faz 2.6a, 2026-10-09)

**Kurulum:** küre şablonu `cfd_sphere` (D = 100 mm); rüzgâr tüneli önde 5D,
arkada 10D, yanlarda 5D (kesit 1.1 × 1.1 m, tıkanma oranı ≈ %0.65), taban hücre
50 mm, iz kutusu (seviye − 2), sınır tabakası yok; yan duvarlar `slip`.
U = 1 m/s, ν = U·D/Re; simpleFoam laminer, gevşetme 0.7 / 0.3, residual hedefi
p 1e-5, U 1e-6; Cd = son 100 iterasyon ortalaması.
Betik: `backend/scripts/cfd_validation_sphere.py` → `uploads/reports/cfd_validation_sphere.json`.

**Referanslar:** Schiller & Naumann (1933) korelasyonu (deneysel veriye ±%5);
Clift, Grace & Weber (1978) standart sürükleme eğrisi (daha dar uydurma).
(`backend/app/postprocess/sphere_drag.py`)

| Mesh'leyici | Seviye | Hücre | Re | Cd (son 100 ort.) | Schiller–Naumann | fark | Clift–Grace–Weber | fark | İterasyon | Süre (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| snappy | 2 | 17763 | 20 | 2.6179 | 2.610 | +0.3 % | 2.715 | -3.6 % | 176 | 14.2 |
| snappy | 2 | 17763 | 40 | 1.7196 | 1.735 | -0.9 % | 1.788 | -3.8 % | 154 | 6.9 |
| snappy | 2 | 17763 | 100 | 1.0445 | 1.092 | -4.3 % | 1.087 | -3.9 % | 223 | 13.3 |
| snappy | 3 | 23287 | 20 | 2.7327 | 2.610 | +4.7 % | 2.715 | +0.7 % | 309 | 15.3 |
| snappy | 3 | 23287 | 40 | 1.8039 | 1.735 | +4.0 % | 1.788 | +0.9 % | 277 | 12.3 |
| snappy | 3 | 23287 | 100 | 1.1120 | 1.092 | +1.9 % | 1.087 | +2.3 % | 636 | 25.1 |
| snappy | 4 | 40575 | 20 | 2.7553 | 2.610 | +5.6 % | 2.715 | +1.5 % | 525 | 32.7 |
| snappy | 4 | 40575 | 40 | 1.8128 | 1.735 | +4.5 % | 1.788 | +1.4 % | 478 | 31.0 |
| snappy | 4 | 40575 | 100 | 1.1073 | 1.092 | +1.4 % | 1.087 | +1.9 % | 2520 | 151.4 |
| cfmesh | 3 | 24318 | 20 | 2.7526 | 2.610 | +5.5 % | 2.715 | +1.4 % | 364 | 17.7 |
| cfmesh | 3 | 24318 | 40 | 1.8201 | 1.735 | +4.9 % | 1.788 | +1.8 % | 315 | 16.3 |
| cfmesh | 3 | 24318 | 100 | 1.1145 | 1.092 | +2.1 % | 1.087 | +2.5 % | 455 | 25.3 |

**Ağ yakınsaması (snappy, seviye 3 → 4):** Re 20 +%0.8, Re 40 +%0.5,
Re 100 −%0.4. Seviye 2 (yüzeyde 12.5 mm hücre) belirgin biçimde düşük.
**En ince ağ (seviye 4) Clift–Grace–Weber'e göre:** +%1.5, +%1.4, +%1.9.
**cfMesh (seviye 3 karşılığı)** snappy seviye 3'ten %0.2–0.9 farklı.

## V-C3 — pitzDaily geri basamak, yeniden bağlanma (Faz 2.6b, 2026-10-09)

**Kurulum:** resmi pitzDaily ağı (12 225 hücre, alt duvarda 250 yüz), case
yazıcımız: k-ω SST, U = 10 m/s, ν = 1e-5 (Re_h ≈ 25 400, h = 25.4 mm), residual
hedefi p 1e-5, U 1e-6, 4000 iterasyon. Koşu sonrası `wallShearStress` ve yüz
merkezleri; alt duvarda 0 < x < 206 mm aralığında τ_x'in son işaret değişimi.
Betik: `backend/scripts/cfd_validation_pitzdaily.py` → `uploads/reports/cfd_validation_pitzdaily.json`.

**Referans:** Pitz & Daily (1983) deneyi x_r/h ≈ 7.0.

| | x_r (mm) | x_r/h | deney | fark |
|---|---|---|---|---|
| k-ω SST, öğretici ağı | 200.3 | 7.89 | 7.0 | +%12.7 |

**Veri notları:** τ_x profili: basamaktan önce ileri akış (τ_x < 0, OpenFOAM
işaret kuralı), ~0–40 mm köşe girdabı, ~45–197 mm ana geri dönüş bölgesi
(τ_x > 0), ~201 mm'den sonra ileri akış. Yeniden bağlanma noktası alt duvarın
daralmaya başladığı x = 206 mm'ye yakın — daralma etkisi ayrıştırılmadı.
Residual'lar 4000 iterasyonda hedefe inmedi, ~1e-4 – 7e-4'te plato (Ux 2.8e-5,
Uy 2.5e-4, p 7.4e-4). Ağ yakınsaması yapılmadı (tek, öğretici ağı).

## V-C4 — Ahmed gövdesi, φ = 25° (Faz 2.6c, 2026-10-09)

**Kurulum:** şablon `ahmed_body` (özgün ölçüler 1044 × 389 × 288 mm, R 100, S 222,
G 50; **bacaklar yok**); zeminli tünel (önde 2L, arkada 4L, yan/üst 1.5L; zemin
sabit duvar), taban 160 mm, yüzey seviyesi 4–5 (10 / 5 mm), iz kutusu seviye 2,
3 sınır tabakası; k-ω SST, U = 40 m/s (Re_L ≈ 2.8·10⁶), gevşetme 0.7 / 0.5,
1500 iterasyon; Cd = son 200 iterasyon ortalaması, A_ref = W·H = 0.112 m².
Betik: `backend/scripts/cfd_validation_ahmed.py [açı…]` → `uploads/reports/cfd_validation_ahmed.json`.

**Referans:** Ahmed, Ramm & Faltin (1984) deneyi (60 m/s, bacaklı): φ 25° → Cd 0.285.

| φ | Hücre | Katman kapsaması | Cd (ort.) | std | deney | fark | Süre |
|---|---|---|---|---|---|---|---|
| 25° | 216 959 | %87 (2.71 / 3) | 0.367 | 0.004 | 0.285 | +%29 | mesh 70 s, çözüm 714 s |

**Veri notları:** ağ bu gövde için kaba (literatürdeki çalışmalar 5–20 milyon
hücre); 1500 iterasyonda residual hedefine inmedi (iterasyon sınırı); bacaklar ve
hız farkı (40 / 60 m/s) modellenmedi; 25° eğim RANS modelleri için bilinen zor
durum (ayrılma / yeniden bağlanma eşiğine yakın). Ağ yakınsaması ve diğer açılar
(0°, 12.5°, 35°) yapılmadı — betik açıları argüman olarak alıyor. Cl sütunu yanal
(y) kuvvettir; düşey kaldırma için lift_dir (0, 0, 1) verilmeli.

## Sırada

- V-C5: Basic Finner (roket; sıkıştırılabilir rejim — R4 ile).
