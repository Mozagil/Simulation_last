# Crash Sınır Koşulları — Başvuru

> Panel'deki her ayarın ne yaptığı, OpenRadioss kart karşılığı ve hangi
> analizde kullanıldığı.
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

| rol | ne yapar | OpenRadioss |
|---|---|---|
| `moving` | Parçanın tüm düğümlerine **ilk hız** verilir | `/INIVEL` |
| `fixed` | Tüm düğümler **tamamen kilitlenir** | `/BCS` (111111) |
| `free` | Ne ilk hız ne kilit — sadece temasla hareket eder | — |

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

OpenRadioss: `/RWALL`

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

| | OpenRadioss |
|---|---|
| genel temas | `/INTER/TYPE7` |
| kenar dahil | `/INTER/TYPE24` |

**TYPE7 vs TYPE24:** TYPE7 düğüm–yüzey, çoğu durumda yeterli ve hızlı.
TYPE24 kenar–kenar teması da yakalar; ince kabuklar katlanırken (crash
box akordeon ezilmesi) kenarlar birbirine girebiliyor, orada TYPE24
daha güvenli.

**`inacti` neden önemli:** Mesh'te parçalar başlangıçta hafifçe iç içe
olabilir. 0 bırakırsan çözücü ilk adımda büyük bir itme kuvveti üretir
ve model patlar. Penetrasyon şüphesi varsa bu bayrağı değiştirmek
gerekir.

---

## 4. Sınır koşulları — `boundary_conditions[]` (`/BCS`)

Belirli bir bölgenin ya da parçanın serbestliklerini kilitler.

| alan | anlamı |
|---|---|
| `dofs` | 6 haneli: `Tx Ty Tz Rx Ry Rz`. `111000` = öteleme kilitli, dönme serbest |
| `region` / `part_id` / `rigid_body` | Nereye uygulanacak |

OpenRadioss: `/BCS`

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

OpenRadioss: `/IMPVEL`

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

OpenRadioss: `/RBODY`

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

OpenRadioss: `/ADMAS`

**Ne zaman:** Modellenmeyen bileşenlerin kütlesini temsil etmek (motor,
batarya, yolcu). Kütle doğru değilse momentum yanlış olur, tüm sonuç
kayar.

---

## 8. Yerçekimi — `gravity` (`/GRAV`)

| alan | anlamı |
|---|---|
| `accel_m_s2` | İşaretli ivme, ör. −9.81 |
| `direction` | `X \| Y \| Z` |

OpenRadioss: `/GRAV`

**Ne zaman:** Düşme testleri. Yatay çarpışmalarda 10 ms'lik sürede
yerçekiminin etkisi ihmal edilebilir — gereksiz yere açma.

---

## 9. Basınç yükü — `pressure_loads[]` (`/PLOAD`)

Zamana bağlı basınç. Friedlander dalgası (patlama) için.

OpenRadioss: `/PLOAD`

## 10. Patlama — `blast_loads[]` (`/LOAD/PBLAST`)

Ampirik patlama modeli (mayın senaryosu). Patlayıcı kütlesi ve mesafeden
basınç dalgası üretir.

OpenRadioss: `/LOAD/PBLAST`

## 11. SPH mermi — `sph_projectiles[]`

Kuş çarpması gibi senaryolar. Mermi sonlu eleman yerine parçacıklarla
modellenir (çok büyük deformasyon, mesh bozulmaz).

OpenRadioss: `/SPHCEL` + `/PROP/SPH` + `/MAT/HYDRO`

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

| | OpenRadioss |
|---|---|
| elastik | LAW1 |
| plastik | LAW2 |
| Johnson-Cook | LAW2 + hız terimleri |
| tablolu | LAW36 |

**Crash'te `elastic` neredeyse hiç doğru değil.** Enerji yutulması
plastik deformasyonla olur; elastik malzeme çarpıp geri seker, ezilme
mesafesi ve yutulan enerji anlamsız çıkar.

### Kabuk kartı — `CrashShellParams`

| alan | anlamı |
|---|---|
| `ishell` | Kabuk formülasyonu |
| `nip` | Kalınlık boyunca integrasyon noktası |
| `hm`, `hf`, `hr` | Hourglass katsayıları (membran / eğilme / dönme) |

OpenRadioss: `/PROP/TYPE1` (Ishell, N) — hourglass katsayıları aynı kartta

**Hourglass nedir:** Tek integrasyon noktalı elemanlar sıfır enerjili
sahte deformasyon modlarına girebilir — eleman "saat camı" gibi burkulur
ama enerji harcamaz. Sonuç fiziksel değildir. Hourglass katsayısı bunu
bastırır. Çıktıdaki hourglass enerjisi toplam enerjinin %5'ini geçerse
model şüphelidir.

---

## 13. Çıktı ve zaman adımı — `engine`, `th`, `sections`, `filters`

| | ne | OpenRadioss |
|---|---|---|
| `t_end_ms` | Simülasyon bitiş zamanı | `/RUN` veri satırı |
| `engine.anim_dt_ms` | Animasyon kare aralığı | `/ANIM/DT` |
| `engine.th_dt_ms` | Zaman geçmişi aralığı | `/TFILE` |
| `th` | Hangi büyüklükler kaydedilsin | `/TH` grupları |
| `sections` | Kesit kuvveti ölçümü | `/SECT/PARAL` |
| `filters` | SAE J211 CFC filtre sınıfı | — (post-process) |

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
3. **Temaslar** — isteğe bağlı TYPE7 / TYPE24 satırları.

Seyrek ayarlar (ilk hız / sabitle / dayatılmış hız / rijit gövde kartları,
yerçekimi, kabuk/solid kartı, hourglass, çıktı) grupların altında ayrı
kartlarda. Malzeme kanunu ve /FAIL 3 · Malzeme adımında. Koşu sonucu
5 · Sonuçlar'da, koşu geçmişi alttaki dock'ta.
