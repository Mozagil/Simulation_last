# Crash (OpenRadioss) — toplu tablo

Faz 1'in (1.10–1.26) bugünkü durumunu tek sayfada toplar. Yeni bilgi yoktur:
kaynaklar `backend/app/api/crash_catalog.py`, şablon şemaları
(`backend/app/templates/`), `backend/app/solvers/crash_params.py`,
`docs/ROADMAP.md` (1.17f, 1.18e, K1–K13) ve `docs/CRASH_EGITIM.md`.
Ayrıntı ve tarihçe ROADMAP'te kalır. Oranlar veri olarak verilir; geçti/kaldı
hükmü yoktur.

Birimler: kg–mm–ms (GPa, kN, J). Hız m/s, uzunluk mm.

## 1. Şablonlar (katalog 16/16 hazır: K0–K13 + 1.18 plaka–küre + 1.24d can crush)

| Katalog | Şablon | Mesh | Geometri parametreleri (varsayılan) | Doğrulama | Eğitim testi |
|---|---|---|---|---|---|
| Crash box eksenel ezilme | `crash_box_shell` | kabuk | box_length 300, box_height 50, box_width 40, wall 3 | V1–V3 | T1–T10, T19–T22, T24, T30 (Model 1–2) |
| — (eğitim Model 3) | `crash_box_plate` | solid | box_length 200, box_height 50, box_width 40, wall 2, plate_thickness 10, plate_margin 20, gap 1 | — | T11, T12 |
| Plaka delinme | `plate_ball_shell` | kabuk | plate_size 300, plate_thickness 5, ball_diameter 50, gap 1 | V4, V5 | T13, T14 |
| Kafa impaktörü (HIC) | `plate_ball_shell` | kabuk | 600 / 0.8 / Ø165, kafa 4.5 kg, 11.1 m/s | V10 | — |
| FOPS | `plate_ball_shell` | kabuk | 1200 / 6 / Ø250, 227 kg, H 5210 | V11 | — |
| Taylor çubuğu | `taylor_bar` | solid | length 50, diameter 10 | V6 | — |
| Düşme testi | `drop_box_shell` | kabuk | size 200×150×50, wall 2, rot_x / rot_y 0, gap 1 | V7 | T17 |
| Direk yan çarpması | `pole_beam_shell` | kabuk | length 800, depth 60, width 40, wall 2, direk Ø254 | V8 | T28 |
| ROPS | `rops_frame_shell` | kabuk | span 1000, height 1200, kesit 80×60, wall 4, bend_radius 150 | V9 | — |
| Kepçe / taş | `bucket_rock_shell` | kabuk | radius 500, angle 90, width 600, thickness 10, taş Ø200 | V16 | — |
| S-kiriş | `s_rail_shell` | kabuk | front 100, rear 200, bend R150 / 45°, kesit 60×40, wall 2 | V12 | T18 |
| Kapı intrüzyonu | `door_beam_shell` | kabuk | length 800, kesit 40×30, wall 1.5, impaktör Ø305 | V13 | T16 |
| Hopkinson çubuğu | `hopkinson_bar` | solid | Ø20, striker 100, bar 500, gap 0.5 | V14 | — |
| Patlama yüklü plaka | `blast_plate_shell` | kabuk | plate_size 400, plate_thickness 3 | V15 | T15 |
| Kuş çarpması (SPH) | `blast_plate_shell` | kabuk | 600 / 6, kuş 1.82 kg, 150 m/s | V17 | T27 |
| Mayın / araç altı | `blast_plate_shell` | kabuk | 1000 / 10, TNT 6 kg, mesafe 500 | V18 | — |
| Can crush | `can_crush_shell` | kabuk | can Ø66×115, wall 0.5, C-kesit çarpıcı 120×40×20, 15° | — (veri) | T23 |

Şablondan bağımsız eğitim testleri: T25 karşılaştırma + enerji dengesi,
T26 mini DOE + vekil, T29 `.k` içe aktarma.

## 2. Parametre haritası

Koşu isteği (`CrashSolveRequest`) 30 alan taşır; çoğu boş bırakılabilen
listelerdir. Kategori başına:

| Kategori | Alanlar (özet) | Radioss kartı | Arayüz yeri |
|---|---|---|---|
| Çarpma / duvar | hız, açı, yön, duvar türü (düzlem / silindir), nokta, normal, Ø | `/RWALL/PLANE`, `/RWALL/CYL`, `/INIVEL` | 4 · Crash → Çarpma |
| Parça rolleri | part_id, rol (hareketli / sabit / serbest), kabuk kalınlığı | `/PART`, `/BCS`, `/INIVEL` | 4 · Crash → Parçalar |
| Malzeme | LAW1 elastik; LAW2 Johnson–Cook (σy, b, n, εp,max, σmax, c, ε̇₀, sıcaklık); LAW36 tablo eğrileri | `/MAT/LAW1`, `/MAT/LAW2`, `/MAT/LAW36`, `/FUNCT` | 3 · Malzeme |
| Kopma | Johnson D1–D5, ε̇₀; çekme şekil değiştirmesi ε_t1/t2, ε_f1/f2 | `/FAIL/JOHNSON`, `/FAIL/TENSSTRAIN` | 3 · Malzeme |
| Eleman / kesit | kabuk: Ishell, Ish3n, Ismstr, NIP, hourglass Hm/Hf/Hr; solid: Isolid, Ismstr, h | `/PROP/TYPE1`, `/PROP/TYPE14` | 4 · Crash → Uzman ayarları |
| Temas | TYPE7 / TYPE24, ana / ikincil parça, tüm model, sürtünme, gapmin, stfac, Istf, Inacti, Iedge | `/INTER/TYPE7`, `/INTER/TYPE24` | 4 · Crash → Temaslar |
| Kütle / rijit gövde | ek kütle (bölge / parça); rijit gövde kütlesi, ivme çıktısı | `/ADMAS`, `/RBODY` | 4 · Crash → Ek tanımlar |
| Sınır koşulu / hız | kilitli serbestlikler (ray dahil); sabit hız + başlangıç/bitiş; parçaya ilk hız | `/BCS`, `/IMPVEL`, `/INIVEL` | 4 · Crash → Ek tanımlar |
| Yük | yerçekimi; Friedlander basınç; PBLAST (TNT, nokta, patlama anı) | `/GRAV`, `/PLOAD`, `/LOAD/PBLAST` | 4 · Crash → Çarpma / Ek tanımlar |
| SPH mermi | çap, boy, aralık, yoğunluk, bulk, Pmin, hız, hedef | `/SPHCEL`, `/PROP/SPH`, `/MAT/HYDRO` | 4 · Crash → Ek tanımlar |
| Yay | iki uç (rijit gövde / nokta / sabit), K, C, kütle | `/SPRING`, `/PROP/TYPE4` | 4 · Crash → Ek tanımlar |
| Sönüm | α, β, parçalar, başlangıç/bitiş | `/DAMP` | 4 · Crash → Ek tanımlar |
| Çözüm kontrolü | bitiş süresi, TH / animasyon aralığı, Δt türü / ölçeği / min | `/RUN`, `/TFILE`, `/ANIM/DT`, `/DT` | 4 · Crash → Çözüm kontrolü |
| Çıktı | TH grupları (duvar, temas, parça, kesit, düğüm), kesit düzlemleri, ezilme referansı | `/TH/*`, `/SECT/PARAL` | 4 · Crash → Çıktı ayarları, Ezilme referansı |
| Süzme (post) | kuvvet CFC, ivme CFC | — (post-process) | 5 · Sonuçlar |
| Ham kart | serbest metin, `/END`'den önce eklenir | herhangi | 4 · Crash → Ek tanımlar |

## 3. Doğrulama (V1–V18)

Oran = model / referans. Koşu ve formül ayrıntısı:
`docs/validation/crash_validation.md`, ROADMAP 1.17f, 1.18e, K1–K13.

| No | Vaka | Referans | Oran (model / referans) |
|---|---|---|---|
| V1 | Crash box elastik | plato ρ·c₀·v·A; temas 2L/c₀ | 0.9995; 1.019; impuls/2Mv₀ 0.966 |
| V2 | Crash box elasto-plastik | plato σy·A | 1.004; impuls 0.974 |
| V3 | Crash box + 50 kg kızak | W&A 1983 / A&J 1984 Pm | 1.15–1.22 / 0.84–0.89; mesh 3 → 2.5 mm %0.7 |
| V4 | Plaka–küre elastik | ankastre plaka k = D/(0.0056·a²) | CFC60 tepe 0.977, ilerleme 1.006, süre 1.009 |
| V5 | Plaka delinme | Recht–Ipson uydurması | v_bl 28.75 m/s, R² 0.9998 |
| V6 | Taylor çubuğu | Wilkins & Guinan L1/L0 | 1.025 (100 m/s), 1.071 (150 m/s) |
| V7 | Düşme testi | KE₀ / mgH; temas anı | 1.001; 1.000; zemin impulsu 0.9997 |
| V8 | Direk yan çarpması | Pm / (4·Mp/L) | 0.805 (10 mm), 0.755 (7.5 mm) — mesh'le değişiyor |
| V9 | ROPS | plato / 4·Mp/(H − R) | 0.996 (15 mm), 0.980 (10 mm); ∫F dδ / IE 1.005 |
| V10 | Kafa impaktörü | ∫\|a\|dt / (I/m) | 0.9995; HIC15 4782 (veri) |
| V11 | FOPS | KE₀ / mgH | 1.0003; ilerleme 97 mm (veri) |
| V12 | S-kiriş | impuls; ortalama kuvvet / düz tüp W&A | 1.001; 0.234 (veri) |
| V13 | Kapı intrüzyonu | plato / 8·Mp/L | 1.054; ∫F dδ / IE 0.998 |
| V14 | Hopkinson çubuğu | ρcvA/2; 2Ls/c | 0.983; 0.972 |
| V15 | Patlama yüklü plaka | serbest plaka momentumu / impuls | 1.0003 (ankastre 0.65, veri) |
| V16 | Kepçe / taş | ∫\|a\|dt / (I/m) | 1.013 |
| V17 | Kuş (SPH), rijit hedef | ρAv²; L/v; impuls | 0.945; 0.924; 1.047 |
| V18 | Mayın (PBLAST) | Hopkinson–Cranz ölçekleme | impuls 8.000 / varış 2.000 (W × 8) |

## 4. Açık kalanlar (crash)

- Bekleyen dallar: `fix/crash-spring-deck` (yay deck hatası; main'de T22c
  starter hatası), `fix/crash-import-unassigned-mat`, `feature/crash-training-runs`,
  `feature/radioss-card-headers`.
- Mühendis kararı: kabul kriterleri (eğitim raporunda veri eşiği olarak
  enerji dengesi ≤ %5, HG/IE ≤ %10, eklenen kütle ≤ %2 kullanılıyor, 2026-10-19);
  dikdörtgen kesitte C = (b+d)/2.
- Küçük açıklar (ROADMAP Faz 1 `[ ]`): crash sekmesinden UI koşu doğrulaması,
  midsurface kenar ikizlenmesi, midsurface "Parça #0" eşleşmesi, kesit yerel ekseni.
- Operasyonel: 200 koşuluk crash DOE (Codespace).
- Ayrı faz: tam ALE, kompozit crash (`/PROP/STACK` + LAW25).
