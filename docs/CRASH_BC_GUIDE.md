# Crash Sınır Koşulları — Başvuru

> Panel'deki her ayarın ne yaptığı, OpenRadioss kart karşılığı, LS-DYNA
> keyword eşleniği (≈, yalnız bilgi amaçlı ad — LS-DYNA kullanılmaz) ve
> hangi analizde kullanıldığı.
>
> Kaynak: `backend/app/solvers/crash_params.py`, `app/api/crash.py`,
> `app/solvers/openradioss.py`. Genel bilgi değil, bu projedeki kod.

---

## 0. Önce kavram: implicit ile explicit farkı

Durability (CalculiX) **implicit statik** çözüyor: denge denklemi bir kez
kurulup çözülüyor, zaman yok. Crash (OpenRadioss) **explicit dinamik**:
zaman mikro-saniyelik adımlarla ilerliyor, her adımda kuvvet dengesi
yeniden hesaplanıyor.

Bunun pratik sonucu: crash'te her şey **zamana bağlı**. "Yük" diye bir
şey yok; onun yerine ilk hız, dayatılmış hız, temas kuvveti var. Çözüm
süresi (`t_end_ms`) modelin bir parçası.

---

## 1. Parça rolleri — `parts[].role`

Panelde her parçaya bir rol veriyorsun. Üç seçenek:

| rol | ne yapar | OpenRadioss | LS-DYNA |
|---|---|---|---|
| `moving` | Parçanın tüm düğümlerine **ilk hız** verilir | `/INIVEL` | `*INITIAL_VELOCITY_GENERATION` |
| `fixed` | Tüm düğümler **tamamen kilitlenir** | `/BCS` (111111) | `*BOUNDARY_SPC_SET` |
| `free` | Ne ilk hız ne kilit — sadece temasla hareket eder | — | — |

**Ne zaman hangisi:** Crash box eksenel ezilmede kutu `moving`, çarpma
plakası `fixed`. Kuş çarpması gibi senaryolarda hedef `fixed`, mermi
ayrı mekanizmayla (SPH) geliyor.

`free` daha ince bir durum: parça başka bir parçanın itmesiyle hareket
edecekse (zincirleme çarpışma) ne ilk hız vermek ne kilitlemek doğru.

---

## 2. Bariyer ve rijit duvar — `barrier`

| alan | anlamı | birim |
|---|---|---|
| `speed_m_s` | Çarpışma hızı büyüklüğü | m/s |
| `angle_deg` | 0 = duvara dik. Pozitif değer eğik çarpma | derece |
| `wall.kind` | `plane` (düzlem) \| `cyl` (silindir — direk çarpması) | — |
| `wall.point`, `wall.normal` | Duvarın konumu ve yönü | mm |
| `wall.diameter_mm` | Silindirik duvarda çap | mm |

OpenRadioss: `/RWALL` · LS-DYNA: `*RIGIDWALL_PLANAR` / `_GEOMETRIC_CYLINDER`

**Birim notu:** Çözücü kg–mm–ms biriminde çalışıyor, orada 1 m/s = 1 mm/ms.
Panel m/s alıyor, dönüşümü deck yazarken yapıyor.

`use_rigid_wall: false` dersen `/RWALL` hiç yazılmaz — parça–parça
çarpışmayı temasla (`/INTER`) çözersin. İki parçalı senaryolarda doğrusu
bu.

---

## 3. Temas — `contacts[]`

Crash'in kalbi. Temas tanımlanmazsa parçalar birbirinin içinden geçer.

| alan | anlamı | tipik |
|---|---|---|
| `type` | 7 veya 24 | 7 |
| `master_part` / `slave_part` | Hangi parçalar temas edecek | — |
| `fric` | Coulomb sürtünme katsayısı | 0.1–0.3 |
| `gapmin` | En küçük temas boşluğu | kabuk kalınlığının yarısı |
| `stfac` | Temas rijitliği ölçeği | 1.0 |
| `istf` | Rijitlik nasıl hesaplanır | 0 (varsayılan) |
| `inacti` | İlk penetrasyon nasıl ele alınır | 0 |

| | OpenRadioss | LS-DYNA |
|---|---|---|
| genel temas | `/INTER/TYPE7` | `*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE` |
| kenar dahil | `/INTER/TYPE24` | `*CONTACT_AUTOMATIC_SINGLE_SURFACE` |

**TYPE7 vs TYPE24:** TYPE7 düğüm–yüzey, çoğu durumda yeterli ve hızlı.
TYPE24 kenar–kenar teması da yakalar; ince kabuklar katlanırken (crash
box akordeon ezilmesi) kenarlar birbirine girebiliyor, orada TYPE24
daha güvenli.

| `all_parts` | Genel temas (yalnız TYPE24): tüm parçalar, öz temas dahil; `master_part` / `slave_part` verilmez | — |
| `iedge` | TYPE24 kenar–kenar teması | 0 |

**Genel temas (`all_parts: true`, 1.24a):** tüm kabuk parçalar tek yüzey
(`/SURF/PART`), tüm katı parçaların dış yüzü ayrı yüzey; kabuk + katı varsa
üç TYPE24 arayüzü (kabuk öz, katı öz, kabuk ↔ katı). Çift temaslarla birlikte
kullanılabilir. LS-DYNA karşılığı `*CONTACT_AUTOMATIC_SINGLE_SURFACE`.

**`inacti` neden önemli:** Mesh'te parçalar başlangıçta hafifçe iç içe
olabilir. TYPE24'te `inacti = 0` iken Radioss bu başlangıç penetrasyonlarını
**yok sayar** — starter listing'i "INACTI = 0 ⇒ THESE PENETRATIONS (NOT THE
TINY ONES) WILL BE IGNORED" yazar ve o çiftler temas dışında kalır (ölçüldü,
kutu ezme #376: 847 penetrasyon yok sayıldı, kutu tabana 2.5 mm girdi).
Kabuklar arası temas boşluğu ≈ (t₁ + t₂)/2; başlangıç aralığını bundan büyük
tutmak (kutu ezmede taban boşluğu 1.0 mm) penetrasyonu baştan önler.

**`iedge` (kenar–kenar):** katlanan ince kabukta kenarlar birbirini kesebilir;
kenar teması kapalıyken (#376) çarpıcı kenarı ince kapağın içinden geçti, `iedge = 1`
ile (#377) başlangıç penetrasyonu ve bu geçiş görülmedi (kutu kaydıktan sonrası ölçülmedi).

---

## 4. Sınır koşulları — `boundary_conditions[]` (`/BCS`)

Belirli bir bölgenin ya da parçanın serbestliklerini kilitler.

| alan | anlamı |
|---|---|
| `dofs` | 6 haneli: `Tx Ty Tz Rx Ry Rz`. `111000` = öteleme kilitli, dönme serbest |
| `region` / `part_id` / `rigid_body` | Nereye uygulanacak |

OpenRadioss: `/BCS` · LS-DYNA: `*BOUNDARY_SPC_SET`

**`parts[].role = fixed` ile farkı:** Rol tüm parçayı 111111 kilitler.
`boundary_conditions` ise **seçili serbestlikleri** ve **bölge bazında**
kilitler. Simetri düzlemi tanımlamak için bu gerekir — ör. modelin
yarısını alıp simetri yüzeyinde normal ötelemeyi kilitlemek.

---

## 5. Dayatılmış hız — `imposed_velocities[]` (`/IMPVEL`)

İlk hızdan farkı: **çözüm boyunca sabit tutar.**

| alan | anlamı |
|---|---|
| `direction` | `X Y Z` (öteleme) \| `XX YY ZZ` (dönme) |
| `velocity_m_s` | İşaretli. Dönmede rad/ms |
| `t_start_ms` / `t_stop_ms` | Hangi aralıkta etkin |

OpenRadioss: `/IMPVEL` · LS-DYNA: `*BOUNDARY_PRESCRIBED_MOTION_SET`

**Ne zaman:** Sled testi benzetimi, ya da çarpma kütlesinin yavaşlamasını
engellemek istediğinde. `moving` rolü ilk hız verir ve parça yavaşlar;
`/IMPVEL` ise hızı zorla sabit tutar — ikisi farklı fizik.

---

## 6. Rijit gövde — `rigid_bodies[]` (`/RBODY`)

Bir bölgeyi/parçayı deforme olmayan tek cisim yapar, kütlesini bir ana
düğümde toplar.

| alan | anlamı |
|---|---|
| `mass_kg` | Ana düğüme eklenen kütle |
| `ikrem` | 0: bağımlı düğümler rijit duvardan çıkarılır, 1: çıkarılmaz |
| `icog` | Ağırlık merkezi işlemi (0 = Radioss varsayılanı) |
| `th_accel` | Ana düğüm ivmesini TH'ye yaz — **HIC kanalı** |

OpenRadioss: `/RBODY` · LS-DYNA: `*CONSTRAINED_NODAL_RIGID_BODY` +
`*ELEMENT_MASS`

**Ne zaman:** Çarpma kütlesini (impactor) modellemek. Deforme olması
gerekmiyorsa rijit yapmak hem doğru hem çok daha hızlı — rijit cisim
zaman adımını sınırlamaz.

`th_accel` özellikle önemli: yolcu yaralanma ölçütü (HIC) ivme
geçmişinden hesaplanıyor, o kanal buradan açılıyor.

---

## 7. Ek kütle — `added_masses[]` (`/ADMAS`)

| alan | anlamı |
|---|---|
| `mass_kg` | Eklenecek kütle |
| `distribution` | `total` (type 1, toplam dağıtılır) \| `per_node` (type 0, her düğüme ayrı) |

OpenRadioss: `/ADMAS` · LS-DYNA: `*ELEMENT_MASS` / `*ELEMENT_MASS_PART`

**Ne zaman:** Modellenmeyen bileşenlerin kütlesini temsil etmek (motor,
batarya, yolcu). Kütle doğru değilse momentum yanlış olur, tüm sonuç
kayar.

---

## 8. Yerçekimi — `gravity` (`/GRAV`)

| alan | anlamı |
|---|---|
| `accel_m_s2` | İşaretli ivme, ör. −9.81 |
| `direction` | `X \| Y \| Z` |

OpenRadioss: `/GRAV` · LS-DYNA: `*LOAD_BODY_Z`

**Ne zaman:** Düşme testleri. Yatay çarpışmalarda 10 ms'lik sürede
yerçekiminin etkisi ihmal edilebilir — gereksiz yere açma.

---

## 9. Basınç yükü — `pressure_loads[]` (`/PLOAD`)

Zamana bağlı basınç. Friedlander dalgası (patlama) için.

OpenRadioss: `/PLOAD` · LS-DYNA: `*LOAD_SEGMENT_SET`

## 10. Patlama — `blast_loads[]` (`/LOAD/PBLAST`)

Ampirik patlama modeli (mayın senaryosu). Patlayıcı kütlesi ve mesafeden
basınç dalgası üretir.

LS-DYNA: `*LOAD_BLAST_ENHANCED`

## 11. SPH mermi — `sph_projectiles[]`

Kuş çarpması gibi senaryolar. Mermi sonlu eleman yerine parçacıklarla
modellenir (çok büyük deformasyon, mesh bozulmaz).

LS-DYNA: `*SECTION_SPH` + `*ELEMENT_SPH`

---

## 11a. Yay — `springs[]` (`/SPRING` + `/PROP/TYPE4`, 1.24b)

İki uç arası eksenel doğrusal yay. Uç: Kütle / kızak kartının ana düğümü
(`rigid_body`) ya da uzayda nokta (`point`, mm; `fixed` ise altı serbestlik
kilitli). `k_n_per_mm` (deck'te kN/mm), `c_n_s_per_mm` sönüm, `mass_kg`; `th`
açıksa `/TH/SPRING` (FX FY FZ). LS-DYNA: `*ELEMENT_DISCRETE` + `*SECTION_DISCRETE`.

## 11b. Sönüm — `damping` (`/DAMP`, 1.24c2)

Rayleigh sönümü C = α·M + β·K. `alpha_per_s` (1/s), `beta_s` (s); deck'e model
birimiyle (α/1000 1/ms, β·1000 ms). `part_ids` boş = tüm parçalar;
`t_start_ms` / `t_stop_ms` (0 = koşu sonu). α kütle orantılı (rijit hareketi de
yavaşlatır), β rijitlik orantılı (yüksek frekans; kararlı Δt küçülür). Ölçülen
(seken LAW1 kutu): β 1e-6 s → Δt_min 5.4e-4 → 3.1e-4 ms; β 1e-5 s aynı sonuç
(listing'de uyarı yok — Radioss β'yı sınırlıyor olabilir, doğrulanmadı).
LS-DYNA: `*DAMPING_PART_MASS` (α) + `*DAMPING_PART_STIFFNESS` (β).

## 11c. Ezilme referansı — `crush_ref` (C8b)

`rigid_body` (ad → ana düğüm) ya da `region` (bölge düğümleri, ortalama);
`direction` boşsa ilk hız yönü. Deck'e ayrı `/TH/NODE/8` (DX DY DZ). Sonuç:
`crush_mm` eğrisi, `crush_final_mm`, `crush_max_mm`, `crush_work_j` = ∫|F_duvar| dδ
(δ_maks'a kadar), `mean_crush_force_kn` = iş / δ_maks, `mean_crush_force_ie_kn`
= IE_son / δ_son. Duvarsız senaryoda yalnız IE oranı.

---

## 12. Malzeme ve eleman kartı — `model`

| alan | anlamı | OpenRadioss |
|---|---|---|
| `law` | `elastic` \| `plastic` \| `tabulated` | LAW1 / LAW2 / LAW36 |
| `isolid` | Solid eleman formülasyonu | TYPE14 Isolid |
| `ismstr` | Küçük/büyük şekil değiştirme | TYPE14 Ismstr |
| `nip` | İntegrasyon noktası sayısı | TYPE14 Inpts |
| `sigma_y_pa` | Akma gerilmesi (boşsa malzemeden) | LAW2 `a` |
| `harden_b_mpa`, `harden_n` | Sertleşme | LAW2 `b`, `n` |
| `eps_p_max` | Kopma plastik şekil değiştirmesi | LAW2 |
| `jc_c`, `jc_eps_dot0_per_s` | Johnson-Cook hız terimleri | LAW2 |

| | OpenRadioss | LS-DYNA |
|---|---|---|
| elastik | LAW1 | `*MAT_ELASTIC` (001) |
| plastik | LAW2 | `*MAT_PIECEWISE_LINEAR_PLASTICITY` (024) |
| Johnson-Cook | LAW2 + hız terimleri | `*MAT_JOHNSON_COOK` (015) |
| tablolu | LAW36 | `*MAT_024` eğri ile |

**Crash'te `elastic` neredeyse hiç doğru değil.** Enerji yutulması
plastik deformasyonla olur; elastik malzeme çarpıp geri seker, ezilme
mesafesi ve yutulan enerji anlamsız çıkar.

### Kabuk kartı — `CrashShellParams`

| alan | anlamı |
|---|---|
| `ishell` | Kabuk formülasyonu |
| `nip` | Kalınlık boyunca integrasyon noktası |
| `hm`, `hf`, `hr` | Hourglass katsayıları (membran / eğilme / dönme) |

LS-DYNA: `*SECTION_SHELL` (ELFORM, NIP) + `*HOURGLASS`

**Hourglass nedir:** Tek integrasyon noktalı elemanlar sıfır enerjili
sahte deformasyon modlarına girebilir — eleman "saat camı" gibi burkulur
ama enerji harcamaz. Sonuç fiziksel değildir. Hourglass katsayısı bunu
bastırır. Çıktıdaki hourglass enerjisi toplam enerjinin %5'ini geçerse
model şüphelidir.

---

## 13. Çıktı ve zaman adımı — `engine`, `th`, `sections`, `filters`

| | ne | OpenRadioss | LS-DYNA |
|---|---|---|---|
| `t_end_ms` | Simülasyon bitiş zamanı | `/RUN` veri satırı | `*CONTROL_TERMINATION` |
| `engine.anim_dt_ms` | Animasyon kare aralığı | `/ANIM/DT` | `*DATABASE_BINARY_D3PLOT` |
| `engine.th_dt_ms` | Zaman geçmişi aralığı | `/TFILE` | `*DATABASE_BINARY_D3THDT` |
| `th` | Hangi büyüklükler kaydedilsin | `/TH` grupları | `*DATABASE_HISTORY_*` |
| `sections` | Kesit kuvveti ölçümü | `/SECT/PARAL` | `*DATABASE_CROSS_SECTION_PLANE` |
| `filters` | SAE J211 CFC filtre sınıfı | — (post-process) | `*DATABASE_..._FILTER` |

**CFC filtresi:** Explicit çözüm ham kuvvet sinyali çok gürültülüdür.
SAE J211, crash verisi için standart filtre sınıfları tanımlar
(CFC 60, 180, 600, 1000). Tepe kuvveti okumadan önce filtrelemek
zorunludur — ham sinyalin tepesi sayısal gürültüdür, fizik değil.
Bu projede ham veri korunuyor, filtre ayrı uygulanıyor.

---

## 14. Tipik senaryo kurulumları

### Crash box eksenel ezilme (rijit duvar)
```
parts: kutu=moving, (plaka yoksa duvar /RWALL)
barrier: speed 10–15 m/s, angle 0
use_rigid_wall: true
model: law=plastic
t_end_ms: 10–20
```

### İki parçalı (kutu + çarpma plakası)
```
parts: kutu=moving, plaka=fixed
use_rigid_wall: false        ← duvar yerine temas
contacts: TYPE7, master=plaka, slave=kutu, fric 0.1
```

### Düşme testi
```
parts: hepsi=free
gravity: -9.81 Z
use_rigid_wall: true (zemin)
t_end_ms: düşme yüksekliğine göre
```

---

## 15. Panel düzeni (2026-10-07)

Crash paneli üç akordeon grubunda (Claude Design "Crash BC Sidebar"):

1. **Çarpma** — rijit duvara çarpma / duvarsız ilk hız, hız, açı, süre,
   duvarın baktığı yön (+X…−Z / özel), duvar konumu ("Modelden seç").
2. **Parçalar** — her parçaya tek soru: hareketli / sabit / serbest.
   Viewport'ta parçalar role göre renklenir (hareketli altın, sabit
   kırmızı, serbest mor); "SINIR KOŞ." düğmesi işaretleri ve renkleri
   gizler.
3. **Temaslar** — isteğe bağlı TYPE7 / TYPE24 satırları; kapsam "Parça çifti"
   ya da "Tüm model" (genel temas, TYPE24).
4. **Ek tanımlar** — bölgeyi kilitle, kütle / kızak (rayda seçeneği),
   sabit hızla it, parçaya ayrı ilk hız, ek kütle, yay; hazır kurulumlar
   (Kızak testi, Ankastre kenar).

Gruplardan sonra (2026-10-15 güncel): **Uzman ayarları**, **Çözüm kontrolü**
(süre, zaman adımı kartı, Rayleigh sönümü) ve **Çıktı ayarları** (kayıt aralığı,
/TH kanalları, kesitler, ezilme mesafesi referansı).

"LS-DYNA karşılıklarını göster" anahtarı açıkken kart adlarının yanında
yaklaşık LS-DYNA keyword'ü görünür (`frontend/src/lib/dynaKeywords.ts`).

Eleman formülasyonu ve hourglass "Uzman ayarları"nda (son koşunun HG/IE
değeri orada); yerçekimi 1 · Çarpma'da; çıktı kartları 4 · Crash → Çıktı
ayarları'nda (CFC filtresi koşudan sonra 5 · Sonuçlar'da). Malzeme kanunu,
/FAIL ve kütüphane Johnson–Cook seti 3 · Malzeme adımında. Koşu sonucu
(enerji, geri sekme, ezilme) 5 · Sonuçlar'da, koşu geçmişi ve karşılaştırma
alttaki dock'ta.

---

## 16. LS-DYNA keyword içe aktarma (.k / .dyn, 1.21)

Sol paneldeki "⇪ LS-DYNA içe aktar" düğmesi. Kendi çeviricimiz okur →
OpenRadioss kartları; LS-DYNA kurulmaz / çalıştırılmaz, keyword yazılmaz
(`docs/LICENSING.md`). Birim çarpanları (uzunluk → mm, kütle → kg, zaman → s)
mühendisten. Çeviri raporu önce okunur (uyarılar, atlanan keyword ve satırlar
üstte); onaydan sonra koşu `POST /crash/import/dyna/{id}/solve`. Koşu
geometrisiz kaydedilir (`crash_runs.import_id`), ML korpusuna girmez. Malzemesi
çevrilmeyen part varsa (ör. desteklenmeyen *MAT_003) çözüm 422 ile durur ve part
listesini verir — varsayılan malzemeye düşülmez.
Çevrilen keyword'ler: *NODE, *ELEMENT_SHELL / SOLID, *PART, *SECTION_*,
*MAT_024 / 001 / 020, temaslar (N2S → TYPE7, S2S → TYPE24), *BOUNDARY_SPC,
*INITIAL_VELOCITY, *RIGIDWALL_PLANAR, *LOAD_BODY, *CONTROL_TERMINATION.
