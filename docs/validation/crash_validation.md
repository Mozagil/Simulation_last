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
