# Plaka–küre hız taraması (1.18d)

Üretildi: 2026-10-04T16:08:39+00:00 · `scripts/plate_ball_sweep.py`. Hüküm yok — delinme eşiği / kabul mühendisin.

Kurulum (TEST değerleri): S235 LAW2, plaka 300 × 300 × 2 mm, /FAIL/TENSSTRAIN ε_t1 0.15 ε_t2 0.25, küre D50 (kabuk 1 mm) + 1 kg, g 1 mm, eleman 5 mm, 2 ms. Plaka kenarı /BCS 111111, küre rijit gövde, TYPE7.

Son hız +z yukarı: impulstan v = −v0 + I/m (negatif = hâlâ −z: geçti ya da temas sürüyor; pozitif = geri sekti), enerjiden |v| (kontrol).

| v0 m/s | koşu | KE₀ J | m kg | F tepe kN | I N·s | silinen | plaka IE J | v son (I) m/s | ‖v son‖ (E) m/s | denge | HG/IE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 25 | #66 | 331.6 | 1.0613 | 21.2 | 28.93 | 0 | 327.6 | +2.26 | 2.27 | 8.39e-04 | 0.001 |
| 50 | #67 | 1326.6 | 1.0613 | 24.5 | 13.28 | 25 | 562.7 | -37.49 | 37.49 | 7.17e-04 | 0.021 |
| 100 | #68 | 5306.4 | 1.0613 | 41.3 | 4.98 | 28 | 452.4 | -95.30 | 95.31 | 2.65e-04 | 0.054 |
| 150 | #69 | 11939.3 | 1.0613 | 128.7 | 3.86 | 56 | 435.9 | -146.36 | 146.37 | 1.03e-03 | 0.134 |
| 200 | #70 | 21225.4 | 1.0613 | 152.5 | 5.19 | 82 | 359.3 | -195.11 | 195.14 | 1.87e-03 | 0.170 |
