# Yarım Kalan İşler

> Claude Code için devir dokümanı. Her madde: **ne**, **neden**, **nasıl
> doğrulanır**. Ölçülmemiş şeyler açıkça işaretli — onları "çalışıyor"
> varsayıp üstüne inşa etme.
>
> Branch: `feature/surrogate-accuracy` · `main`'e merge edilmedi
> Son durum (2026-09-19): 594 backend testi geçiyor (1 atlandı, ccx ile
> ilgisiz) — gerçek ccx fizik testleri dahil; 88 frontend testi geçiyor

---

## 0. ~~ACİL — ölçülmemiş değişiklik~~ — KAPANDI (2026-09-19)

### 0.1 Yüzey yükü düzeltmesinin doğrulanması — ✅ doğrulandı

**Hipotez doğru çıktı**, ama ölçüm önce bir hata yakaladı: `92bb1f1`
tutarlı-ağırlık bloğunu eklemiş, eski eşit-bölme yüz döngüsünü yerinde
bırakmıştı. Yüzey yükü **iki kez** yazılıyordu (iki `*CLOAD` bloğu, toplam
60 kN) — u ve σ tam iki katına çıkıyordu (σ 187 → 384). Mevcut "toplam
kuvvet korunur" testi `.inp` çıktısına bakmadığı için yakalamamıştı.
Düzeltme + `.inp` seviyesinde test: `c0f421c`.

**Kontrollü A/B** (aynı ortam, aynı 5 mesh, tek fark yük dağıtımı;
delikli plaka H200 W100 t5 d20, S235, 30 kN):

| es | eşit bölme | tutarlı ağırlık |
|---|---|---|
| 12 | 0.060882 | 0.059850 |
| 7 | 0.060795 | 0.059905 |
| 5 | 0.060623 | 0.059914 |
| 3.6 | 0.065623 | 0.059905 |
| 2.4 | 0.084794 | 0.059853 |
| **yayılma** | **%39.9** | **%0.11** |

Kontrol kolu eski ölçümü 4 haneye kadar yeniden üretti (0.084795 →
0.084794): anomali gerçek, tek değişken yük dağıtımı. σ iki kolda aynı
(ince meshlerde 187–192 MPa; Peterson Kt=2.51 × 75 MPa = 188 MPa).
Kabul ölçütü (<%1) karşılandı.

**Kiriş verisi etkisi — ölçüldü, önceki "%1 mertebesinde" tahmini
yanlıştı:** study 3'ten 8 tasarım bugünkü çözücüyle yeniden çözüldü; en
büyük fark u'da %0.001, σ'da %0.002. Sebep: yükleme yüzeyindeki yerel
bozulma yüzey gerilmesiyle ölçeklenir — plakada 60 MPa, kirişte ~0.33 MPa
(~180× küçük). **Kiriş verisi ve eğitilmiş modeller geçerli, yeniden
koşmaya gerek yok.**

### 0.2 Bu doğrulamanın yan ürünleri (kapandı)

- `31d09a6` — **CLOAD toplam kuvvet sözleşmesi.** Eskiden her yüze/kenara
  ayrı ayrı tam F yazılıyordu (2 yüz → 2F), tutarlı yol ise toplam F
  veriyordu: aynı BC mesh tipine göre F ya da n·F. Artık seçimin tamamına
  toplam F. 11 şablonun varsayılan yük bölgesi tam 1 yüz (gmsh ile
  sayıldı) — DOE verisi etkilenmedi; fark yalnız Tezgâh'ta elle çoklu
  seçimde.
- `6585824` — **Gerçek-çözüm testleri sessizce atlanıyordu.** `requires_ccx`
  yalnız PATH'e bakıyordu, uygulama CCX_PATH kullanıyor. Kiriş referans ve
  şablon uçtan-uca testleri hiç koşmuyordu; "tüm testler yeşil" fiziği
  kapsamıyordu. Artık `_ccx_executable()` ile karar veriliyor.
- Kürasyon: çift yüklü (622–626), A/B kontrol kolu (633–637) ve mükerrer
  (664–676) run'lar `exclude-bulk` ile gerekçeli dışlandı. Geçerli plaka
  yakınsama run'ları: 628–632.

---

## 1. GNN alan modeli — prototip, çalışmıyor

Arayüzde **"GNN eğit"** butonu var ve bir dosya üretiyor, ama yaptığı iş
eğitim sayılmaz. Kullanıcıya çalışıyormuş izlenimi veriyor.

### 1.1 Mesh bağlantısı yazılmıyor
`calculix.py` → `write_inputs(path, X, None)`. Connectivity **daima
None**; diskteki tüm `.train.npz` dosyalarında `connectivity.shape=(0,0)`.
Graf koordinatlardan **k-NN (k=6)** ile kuruluyor — yani "MeshGraphNet"
dediğimiz şey mesh grafı değil, nokta bulutu komşuluğu.

Eleman bağlantısı `.inp` dosyasında zaten var, sadece geçirilmiyor.

### 1.2 Normalizasyon yok
Ham kanallar aynı katmana giriyor:

| kanal | aralık |
|---|---|
| x, y, z | 0 … 700 |
| fixed_ux/uy/uz | 0 / 1 |
| youngs_modulus_mpa | 210000 |
| density_tonne_mm3 | 7.85e−9 |

E ve koordinatlar gizli katmanı dolduruyor; BC bayrakları ve yoğunluk
sayısal olarak yok hükmünde. Çıktı tarafı da normalize değil.

### 1.3 Gerçek eğitim yok
`train_gnn`: son katmana en küçük kareler + process ağırlıklarına **6
adım** kaba gradyan (`lr=1e-4`). **Encoder hiç güncellenmiyor** — sabit
rastgele projeksiyon olarak kalıyor.

**Ölçülen:** `node_rmse.u_y = 12.35 mm`, `scalar_rmse.max_displacement
= 21.26 mm`. Gerçek deplasmanlar 22–93 mm arası → hata sinyalin
mertebesinde, "hep sıfır de" tahmininden ayırt edilemez.

**Sıra:** (1) connectivity yaz → (2) normalizasyon → (3) gerçek eğitim
(PyTorch Geometric ya da NumPy'de düzgün backprop).

**Ara çözüm:** Düzeltilene kadar butona "prototip — sonuçlar geçersiz"
etiketi konmalı, ya da devre dışı bırakılmalı.

---

## 2. Veri ayıklama ve arşiv

### 2.1 Korpusa göre arşiv (EKSİK)
**Tümünü indir** korpusa göre süzmüyor; yalnız "çözülmüş run'lar"
filtresi var. Temiz eğitim setini (dondurulmuş korpustaki run'lar)
indirmek mümkün değil.

**Yapılacak:** Arşiv ucuna korpus adı parametresi + panelde "yalnız
eğitim seti" seçeneği. Korpus manifesti `run_ids` listesini zaten
tutuyor (`uploads/models/`), süzgeç oradan kurulabilir.

### 2.2 Mevcut olanlar (çalışıyor, sadece kullanılması gerek)
- Geçmişte her satırda **Dışla** butonu (silmez, eğitimden çıkarır)
- `PATCH /geometry/runs/exclude-bulk` — toplu işaretleme
- Klasör görünümü: şablon → eğitim durumu / DOE seti
- Korpus `manually_excluded` ile dışlananları almıyor

**Temiz arşiv için doğru sıra:** elle dışla → **Seti dondur** → arşivle.

---

## 3. Solver yakınsaması (Faz 0.6) — ✅ kapandı (2026-09-19)

**Ölçüm önceki varsayımı düzeltti.** "Yakınsamamış çözüm `solved`
sayılıyor" iddiası ölçülen vakalarda **doğru değildi**: ccx yakınsamadığında
sıfır olmayan kod döndürüyor (201) ve kod bunu zaten `failed` sayıyordu.
Gerçek ccx deneyi (NLGEOM kiriş, 6061-T6 L500 T8 W40):

| vaka | exit | .frd | son adım zamanı |
|---|---|---|---|
| normal | 0 | 20 artım | 1.0 |
| artım limiti (INC=3) | 201 | 3 artım (**kısmi ama var**) | 0.15 |
| yük ×200 | 0 | 29 artım, 2 cutback | 1.0 |
| ıraksama | 201 | 1 blok | 0.0 |

Yapılanlar:
- [x] `.sta` okuyucu (`parse_ccx_sta`): artım, cutback (`ATT` sütunundaki
      `U`), iterasyon, son adım zamanı. `.cvg` ayrıca okunmadı — gereken
      özet `.sta`'da var.
- [x] `scalars`'a özet: `_solver_converged`, `_n_increments`,
      `_n_cutbacks`, `_n_iterations`, `_final_step_time`
- [x] Savunma: exit=0 ama statik adım 1.0'a ulaşmadıysa `SolverError`
      (modal/`*FREQUENCY` hariç). Ölçülen vakalarda tetiklenmedi — ccx
      zaten 201 veriyor — ama sessiz başarısızlığın bedeli yüksek.
- [x] Hata mesajına özet: "Adım zamanı 0.15/1.0, 3 artım, 0 cutback."
- [x] Korpus kapısı `not_converged` (kaydı olmayan eski lineer run'lar
      düşmez)
- [x] Regresyon: gerçek ccx ile bilerek yakınsamayan tek-eleman vaka
      `SolverError` veriyor; `.sta` fikstürleri gerçek çıktılar
      (`tests/fixtures/ccx_sta/`)

## 4. NLGEOM (büyük deformasyon)

### 4.0 NLGEOM sonuçları yanlış okunuyordu — ✅ kapandı (2026-09-19)

Yakınsama deneyi sırasında bulundu, tek kök neden: çözüm tipi girdi
destesinden değil `.frd`'deki blok sayısından tahmin ediliyordu ("birden
çok DISP bloğu = modal"). NLGEOM statik çözüm artım başına blok yazar →
- deplasman İLK artımdan okunuyordu (`modes[0]`): **2.669 mm**
- gerilme artımlar boyunca ORTALANIYORDU: **103.5 MPa** (~0.525 × tam yük)
- eğitim örneği **modal şemayla** yazılıyor, görüntüleyici artımları "mod"
  diye gösterip ilk artımı açıyordu

Düzeltme: tip `*FREQUENCY` kartından okunur; statikte son artım; gerilme
artım başına ayrı tutulur. Lineer çıktı birebir aynı (tek artım).

| 6061-T6 kiriş L500 T8 W40, F=150 N | eski | **yeni** | lineer FEA (aynı mesh) |
|---|---|---|---|
| u_max | 2.669 | **52.893** | 53.388 mm |
| σ_max | 103.5 | **196.5** | 197.7 MPa |

Regresyon (gerçek ccx): aynı deste lineer ve küçük yüklü NLGEOM — ikisi
%2 içinde olmalı. Eski kodda NLGEOM u = lineerin tam %10'u (10 artımın
ilki) çıkıyordu; test eski kodda kalıyor, yenisinde geçiyor.

**Aşağıdaki doğrulama planı için ölçüm:** bu vakada NLGEOM lineerden
yalnız **%0.93** küçük (σ %0.61) — "%5–15" beklentisi u/L ≈ 0.1 için
yanlıştı. Yön doğru (sertleşme), büyüklük küçük; uç yüklü konsolun
klasik büyük sehim çözümüyle tutarlı (etki ~%9'a ancak lineer u/L ≈ 0.33'te
çıkar). **"Fark yoksa kart uygulanmamış" ölçütü %1'lik farkla güvenilir
değil** — doğrulama vakası daha narin seçilmeli (lineer u/L ≈ 0.3).
Akmadan buna ulaşmak için malzeme/geometri yeniden hesaplanmalı.


Backend **hazır**: `*STEP, NLGEOM` kartı, artımlı yükleme, `nlgeom` ve
`n_increments` parametreleri, korpusta lineer/nonlineer ayrımı
(`CorpusSpec.nlgeom`, `scalars["_nlgeom"]`).

Eksikler:
- [ ] **Arayüzde açma/kapama yok** — yalnız API'den erişilebiliyor
- [ ] Hiç koşulmadı, tek bir doğrulama bile yapılmadı
- [ ] NLGEOM veri seti yok (u/L 0.10–0.30 bandı için ayrı DOE + ayrı model)

**Doğrulama vakası** (hesaplandı): çelikte akmadan büyük deformasyona
ulaşmak için L/T ≈ 168 gerekiyor — çok narin. Alüminyum pratik:
**6061-T6, L=500, T=8, W=40, F=150 N** → u/L = 0.106, σ = 176 MPa
(akma 276, güvenli).

Aynı vaka lineer ve NLGEOM koşulup karşılaştırılmalı. Beklenen: NLGEOM
**daha küçük** deplasman (büyük deformasyonda yapı sertleşir).
~~Fark %5–15~~ — **ölçüldü: bu vakada %0.93** (bkz. 4.0). Bu büyüklükte
fark kartın uygulandığını güvenilir biçimde göstermez; vaka daha narin
seçilmeli (lineer u/L ≈ 0.3).

---

## 5. Delikli plaka eğitimi — veri ✅, ürün kararı bekliyor (2026-09-19)

**Veri:** kalite seti study 5 — 200 örnek (S235 96 + S355 104), 198 çözüldü,
2 başarısız (ikisi de `nonpositive jacobian` — bkz. 8.4). Kalite taraması
198/198 ok, analitik uyarı 0. Korpus `plaka-v1`: 198/198 tutuldu.
En büyük örnek 333 bin düğüm, 365 s, ccx bellek tepesi ~10 GB. Toplam
~2 saat 10 dk (ilk tahmin 60 dk — orta boy örnekler kalibrasyondan yavaş).

**Bulunan ve düzeltilen hata:** korpus `mesh_ratio`'yu her zaman `es/T` ile
hesaplıyordu; DOE mesh'i `oran × karakteristik uzunluk` (plakada **d**) ile
kurar. Kirişte ikisi tesadüfen aynı. Plakada ara ölçümde 114 geçerli
örneğin **45'i** `mesh_outlier` diye atılıyordu. Artık şablonun
karakteristik uzunluğu kullanılıyor; kiriş korpusu birebir aynı (192).

**Model kıyası** (şablona uygun özellikler, ürün kodu DEĞİŞMEDİ — deney;
198 örnek, 148/50, tohum 2026):

| model | u MAPE | u en kötü | σ MAPE | σ en kötü |
|---|---|---|---|---|
| RF ham | %19.3 | %100 | %15.3 | %51 |
| log-log | %1.53 | %4.6 | %2.22 | %7.7 |
| **log-log + RF artık** | **%0.60** | **%2.7** | %1.32 | %7.2 |
| fizik özellikli (log(W−d), d/W) | %1.14 | %4.8 | **%1.29** | **%5.7** |
| fizik + RF artık | %0.62 | %3.3 | %1.24 | %6.7 |

- Tahmin ("log-log %5–10, +RF artık %2–3") **karamsar çıktı**: log-log
  zaten %1.5–2.2; hibrit u'da %0.60.
- **Hibrit tasarım doğrulandı** (u: %1.53 → %0.60). σ'da her şey ~%1.3'te
  toplanıyor — mesh gürültü tabanının (±%1, bkz. yakınsama) üstünde çok az
  yer var; şablona özel özellik mühendisliği yalnız en kötü durumu
  iyileştiriyor (%7.7 → %5.7).
- En kötü σ hataları mesh bandının KABA ucunda (es/d 0.22–0.25;
  |hata|–es/d r=+0.33, d/W ile r=+0.18) → model biçimi değil
  ayrıklaştırma gürültüsü.
- log-log üsleri σ: W −1.16, T −1.01, F 0.996, d +0.21 — beklendiği gibi
  teorik saf kuvvet yasası değil (Kt(d/W), log(W−d)).

**Ürüne almak için gereken kararlar (açık):**
- [ ] **Özellik vektörü şablona özgü olmalı.** `FEATURE_KEYS` kirişe göre
      (length/thickness/width): plakada `length=0`, **`diameter` ve
      `height` hiç özellik değil**. Bugünkü ürünle plaka eğitilirse model
      delik çapını görmez. Öneri: şablonun `params_schema` sayısal alanları
      + mesh + malzeme + yük; bundle zaten `feature_keys` saklıyor.
- [ ] **Model dosyaları şablon başına saklanmalı.** `scalar_rf.joblib` /
      `scalar_loglinear.joblib` TEK ve global: plaka eğitimi kiriş
      modelinin ÜZERİNE YAZAR.
- [ ] Hibrit tür (`log-log + RF artık`) ürüne eklensin mi.

## 6. Hot-spot ekstrapolasyonu (Faz 0.6)

Ham `max_von_mises` tekil noktalardan okunuyor. Kısmi çözüm olarak
`max_von_mises_away` eklendi (kısıttan 1×T uzakta): gürültü %5.57 →
%1.20, teoriden +%10 → −%0.8, `thickness` üsteli −1.919 → −2.011
(teori −2).

Roadmap'te planlanan daha doğru yöntem henüz yapılmadı:
- [ ] Yüzeyde 0.4t ve 1.0t mesafelerinden okuyup yüzeye ekstrapolasyon
- [ ] `scalars`'a hem tepe hem hot-spot değeri
- [ ] Şablonlara fillet parametresi (ankastre kökü, omuz geçişleri) —
      gerçek yapılarda keskin köşe yok, tekilliğin asıl kaynağı bu

---

## 7. Şablon kütüphanesi (Faz 0.4)

12 şablon var, 4'ü eksik:
- [ ] T-braket (kaburgalı ve kaburgasız)
- [ ] L-braket, delikli bağlantı
- [ ] Flanş (cıvata delikli)
- [ ] Kademeli mil (çap geçişinde gerilme yığılması, fillet parametre)

---

## 8. Küçük ama gerçek sorunlar

### 8.1 `/solve` `region` alanını sessizce yok sayıyor
Bölge adıyla BC verilirse (`{"type":"cload","region":"yuk_cekme",...}`)
`/solve` onu görmezden geliyor ve model **yüksüz** çözülüyor. Hata
vermiyor. Bölge→yüzey bağlamayı `bind_scenario_bcs` yapıyor ve yalnız
DOE/convergence yolunda çağrılıyor.

**Yapılacak:** ya `region` desteklensin ya da açık hata verilsin.

### 8.2 Test malzemesi çöpü
DB'de 16 adet `TestCustomSteel_*` malzemesi birikmiş (id 34–49) —
testlerin bıraktığı kayıtlar. 21 malzemenin 16'sı çöp. Testler rollback
yapmalı ya da ayrı test DB'si kullanmalı.

Aynı kök neden run'larda da var: her tam pytest koşusu `cae_dev`'e ~13
şablonsuz run bırakıyor ("Test Case 1", "PDF testi" …; örn. id 640–663).
Eğitimi etkilemiyor (korpus `no_template` ile atıyor) ama geçmişi ve
veri seti sayılarını kirletiyor. `tests/db_guard.py` bunu önlemek için
yazılmış olabilir — bağlı mı kontrol edilmeli.

### 8.3 `doe_study_id` geriye dönük boş
Migration eski run'ları doldurmadı; mevcut ~900 run "DOE dışı" görünüyor.
`DoeCase` tablosundan eşleyen bir betik 5 dakikalık iş — mevcut setler
(#5, #6, #8, #9) de klasörlenebilir hale gelir.

---

### 8.4 gmsh ters kuadratik eleman (`nonpositive jacobian`)
Plaka DOE'sinde 200 örnekten 2'si (#62 d=24 W=77.5 es=3.82; #129 es=3.03)
ccx'te `*ERROR in e_c3d: nonpositive jacobian` ile düştü — muhtemelen delik
yüzeyindeki eğri kenar-orta düğümleri. Sistem doğru davrandı (`failed`,
sessiz `solved` değil). gmsh yüksek-mertebe optimizasyonu
(`Mesh.HighOrderOptimize`) bir mesh ayarı kararı — kullanıcıya ait.
Ayrıca hata mesajı yalnız log yolunu gösteriyor; ccx'in `*ERROR` satırı
mesaja taşınmalı.

## Öncelik sırası (öneri)

1. ~~**0.1** — yüzey yükü doğrulaması~~ ✅ kapandı
2. ~~**3** — solver yakınsaması~~ ✅ kapandı
   ~~**4.0** — NLGEOM sonuç okuma hatası~~ ✅ kapandı
3. ~~**5** — delikli plaka verisi + kıyas~~ ✅ — **ürün kararı bekliyor** (özellik vektörü, model saklama)
4. **2.1** — korpusa göre arşiv (temiz veri indirilemiyor)
5. **1** — GNN (en büyük iş, kontur tahmini için zorunlu)
6. **4** — NLGEOM arayüz + veri seti
7. **6, 7, 8** — iyileştirmeler

**Crash'e (Faz 1) geçmeden önce en az 0.1 (✅) ve 3 (✅) kapanmalı** — crash de çok artımlı `.frd` üretecek; 4.0 aynı sınıftan — ikisi de
solver altyapısını ilgilendiriyor, crash aynı altyapıyı kullanacak.
