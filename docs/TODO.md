# Yarım Kalan İşler

> Claude Code için devir dokümanı. Her madde: **ne**, **neden**, **nasıl
> doğrulanır**. Ölçülmemiş şeyler açıkça işaretli — onları "çalışıyor"
> varsayıp üstüne inşa etme.
>
> Branch: `feature/surrogate-accuracy` · `main`'e merge edilmedi
> Son durum (2026-09-24): 765 backend testi geçiyor (1 atlandı, ccx ile
> ilgisiz) — gerçek ccx fizik testleri dahil; 95 frontend testi geçiyor

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

### ~~1.1 Mesh bağlantısı yazılmıyor~~ — KAPANDI (2026-09-22)
`calculix.py` → `write_inputs(path, X, None)` yüzünden connectivity **daima
None**'dı; diskteki tüm `.train.npz` dosyalarında `shape=(0,0)`. Graf
koordinatlardan k-NN (k=6) ile kuruluyordu — "MeshGraphNet" dediğimiz şey
mesh grafı değil, nokta bulutu komşuluğuydu.

**Yazım (9658f13).** `_read_inp_elements` `.inp`'ten bağlantı + eleman tipi
okur; `pad_connectivity` karışık tipleri tek diziye koyar (−1 dolgu); tipler
`.inputs.npz` → `.train.npz` zincirinde taşınır. `ELEMENT_EDGES` tablosu
(C3D4/C3D10/C3D8/S3/S4) ile **klik değil gerçek eleman kenarları**: C3D10'da
klik 45 kenar üretip mesh'te komşu OLMAYAN karşılıklı kenar-ortası düğümleri
bağlıyordu; doğrusu 12 kenar (köşe–orta–köşe). `GraphSample.edge_source` =
`"mesh"` | `"knn"`, eski dosyalar dürüstçe ayrışır.

Ölçüm (99_d3.msh, 8386 düğüm, 4007 C3D10):

| graf | kenar |
|---|---|
| gerçek mesh | 13 848 |
| klik (tipsiz) | 89 613 |
| eski k-NN (k=6) | 27 917 |

Eski grafın kenarlarının yalnız **%33.6'sı** mesh'te gerçekten vardı;
gerçek kenarların **%67.8'i** grafta vardı. Model yapının gerçek
bağlantısını hiç görmemiş.

**Geriye doldurma (206015f).** Düzeltme yalnız yeni koşuları kapsıyordu.
`app/dataset/connectivity_backfill.py` bağlantıyı mesh'ten yeniden
ÇIKARMAZ, üretim yolunu (`rebuild_input_for_run` → `build_input`) çağırır.
Güvenlik kilidi: mesh dosyaları `{stem}_d3.msh` adıyla ÜZERİNE yazıldığı
için düğüm koordinatları birebir karşılaştırılır (tol 1e-3 mm), uymazsa
dosyaya dokunulmaz.

Dev veri sonucu: **1473 dosya yazıldı** (957 run), 34 run `mesh_uyusmuyor`,
10 zaten doluydu. Eğitim dosyaları: **518 mesh grafı / 34 k-NN** (%94).
Uyuşmayan 34'ün hepsi yakınsama taramaları (aynı geometri 7 kez yeniden
mesh'lenmiş, diskte yalnız sonuncusu var) — kilit olmasaydı bu dosyalara
YANLIŞ graf yazılacaktı ve hiçbir metrikte görünmezdi.

Bütünlük: 552 eğitim dosyasında `node_outputs`'tan hesaplanan u_max, DB
skaleriyle birebir tuttu (**uyuşmayan 0**). Testler: `test_mesh_graph.py`
(20) + `test_connectivity_backfill.py` (11). 684 backend testi geçiyor.

Yan düzeltme: `.env`'i yalnız `app.main` yüklüyordu; CLI/alembic gibi API
dışı girişler sessizce varsayılan DB adresine düşüyordu (`app/db/session.py`).

### ~~1.2 Normalizasyon yok~~ — KAPANDI (2026-09-23)
Ham kanallar aynı katmana giriyordu (x,y,z: 0…700 · bayraklar: 0/1 · E:
210000 · yoğunluk: 7.85e−9). `app/ml/normalization.py` → `ChannelScaler`:
ölçek EĞİTİM setinden çıkarılır, model dosyasında saklanır, tahminde ters
çevrilir. Dışarıya her zaman fiziksel birim (mm, MPa) döner — metrikler
eski ölçümlerle karşılaştırılabilir kalsın diye.

**Yazarken çıkan iki gerçek sorun (ikisi de ölçüldü):**

1. `poisson_ratio` fiziksel olarak sabit (0.3) ama float32 saklamadan
   std = 9.1e−8 geliyor. Saf z-skoru buna BÖLÜYOR ve yuvarlama gürültüsünü
   ±1 mertebesinde bir girdiye çeviriyordu. Bağıl eşik (`CONSTANT_REL`)
   eklendi.
2. Kanal başına bağımsız ölçek fiziği bozuyor. x/y/z ölçekleri 169 / 5.3 /
   18.9 çıkıyordu: narin kiriş küpe dönüşüyor, **eğilmeyi belirleyen en-boy
   oranı siliniyor**. Aynı şey çıktıda: `u_z` bu yük durumunda fiziksel
   olarak sıfır (std 7e−4 mm), kendi std'siyle bölününce sayısal gürültü
   `u_y` kadar önemli görünüyor. Çözüm: aynı birimi paylaşan bileşenler
   (`NODE_INPUT_GROUPS`, `NODE_OUTPUT_GROUPS`) ORTAK ölçek alıyor.

**A/B ölçümü** — study 3'ten 88 graf (64 eğitim / 24 holdout), aynı tohum,
tek değişken ölçekleme. Taban = "eğitim ortalamasını söyle":

| holdout metriği | taban | eski (ham) | yeni (normalize) |
|---|---|---|---|
| u_y RMSE (mm) | 1.840 | 1.241 | **1.211** |
| von Mises RMSE (MPa) | 17.90 | 15.84 | 15.87 |
| skaler u_max (mm) | 3.72 | **2.45** | 2.76 |
| skaler vm_max (MPa) | 44.32 | 33.02 | **28.32** |

**Dürüst sonuç: normalizasyon tek başına neredeyse fark etmiyor** (iki
metrik iyileşti, biri kötüleşti, biri aynı). Beklenen de buydu: encoder
hâlâ DONUK rastgele projeksiyon, çıkış katmanı en küçük kareler — darboğaz
ölçek değil, 1.3'teki eğitimin olmayışı. Normalizasyon 1.3'ün ÖN KOŞULU
(1e−9…1e5 arası kanallarla gradyan eğitimi yürümez), tek başına çözüm
değil. Bu satır "yapıldı, iyileşti" diye okunmamalı.

Model her iki hâlde de tabandan iyi (u_y'de %34, vm'de %11) — yani "hep
ortalamayı söyle"den ayırt edilebiliyor, ama mühendislik için kullanılabilir
değil.

Testler: `test_normalization.py` (16) + `test_gnn_normalization.py` (7) —
sabit kanal, float32 gürültüsü, narinlik korunumu, npz gidiş-dönüşü,
ölçeksiz eski model, ölçek uygulanmazsa sonucun değişmesi.
707 backend testi geçiyor.

### 1.3 Gerçek eğitim yok
`train_gnn`: son katmana en küçük kareler + process ağırlıklarına **6
adım** kaba gradyan (`lr=1e-4`). **Encoder hiç güncellenmiyor** — sabit
rastgele projeksiyon olarak kalıyor.

**Ölçülen:** `node_rmse.u_y = 12.35 mm`, `scalar_rmse.max_displacement
= 21.26 mm`. Gerçek deplasmanlar 22–93 mm arası → hata sinyalin
mertebesinde, "hep sıfır de" tahmininden ayırt edilemez.

**Sıra:** (1) ~~connectivity yaz~~ ✅ → (2) ~~normalizasyon~~ ✅ →
(3) gerçek eğitim.

#### ~~1.3a Komşu ortalaması vektörleştirildi~~ — KAPANDI (2026-09-23)
Mesaj geçişinin çekirdeği (`_mean_neighbors`) kenarlar üzerinde Python
döngüsüydü. Eğitim ve her A/B ölçümü bunu yüzlerce kez çağırıyor; ölçüm
turu dakikalar sürdüğü için 1.3b'yi ayarlamak pratikte imkânsızdı.

Tek çağrı (gizli=24): 500 düğüm 4.44 → 0.43 ms · 9k düğüm 81.0 → 5.4 ms ·
28k düğüm 246.9 → 17.3 ms. **Gerçek eğitim işi (24 graf, 7218 düğüm ort):
56.4 sn → 6.1 sn, 9.2×** ve `u_y` RMSE altı hanede aynı (1.064074).

Düzleştirilmiş `bincount` kullanılıyor; geçici indeks dizisi
2·kenar·gizli_boyut büyüdüğü için sınır aşılınca sütun sütun toplamaya
düşüyor (gizli katman 1.3b'de genişleyecek). Eski döngülü uygulama
`tests/test_mean_neighbors.py` içinde referans olarak duruyor — sonuç
değişirse test düşer. 723 backend testi geçiyor.

#### 1.3b Gerçek geri yayılım — KOD YAPILDI (2026-09-24), BAŞARI ÖLÇÜTÜ TUTMADI
**Çerçeve kararı uygulandı (`9935b8a`):** eğitim PyTorch (`app/ml/gnn_torch.py`,
`requirements-ml.txt`, isteğe bağlı), çıkarım NumPy `forward`'da kaldı.
Ağırlıklar aynı `.npz` şemasında; iki uygulamanın eşitliği testle kilitli
(bağıl 1e-12). torch venv'i 563 MB → 1.2 GB yapıyor — sunucu/CI kurmuyor.
Adam, graf başına mini-batch, erken durdurma, en iyi turun ağırlıkları.
`metrics["engine"]` hangi motorun koştuğunu söyler ("numpy" eğitim değildir).
Testler: `tests/test_gnn_torch.py` (16).

**Ölçülen** (study 3, 88 graf, 70 eğitim / 18 holdout — holdout):

| | taban | numpy | torch |
|---|---|---|---|
| u_y RMSE (mm) | 1.331 | 0.965 | 0.862 |
| von Mises RMSE (MPa) | 16.84 | 15.08 | 14.77 |
| u_max RMSE (mm) | 1.919 | 3.022 | 1.791 |
| vm_max RMSE (MPa) | 41.89 | 28.26 | 32.18 |

Kayıp 0.769 → 0.476, encoder artık güncelleniyor, erken durdurma 9. turda.

**Başarı ölçütü:** holdout'ta skaler u_max hatası < %5 ve alan RMSE'si
u_max'ın %5'inin altında. **TUTMADI:** u_max RMSE 1.79 mm, eşik 0.121 mm —
~15 kat uzak, taban çizgisinin (1.92) ancak biraz altında.

**Şüphe (ölçülmedi):** 2 mesaj geçişi adımı ~7000 düğümlü kirişte ankastre
ucun bilgisini serbest uca taşıyamıyor; deplasman global bir büyüklük.
`hidden`/`n_proc` taraması başlamadı. → **Mimari kararı gerekiyor (1.3c).**

**Ara çözüm — YAPILDI (2026-09-24):** panelde buton "GNN eğit (prototip)",
altında "GNN alan modeli prototip — sonuçlar geçersiz" notu ve son eğitimin
holdout u_max RMSE'si (`metrics.holdout`) gösteriliyor. Buton devre dışı
BIRAKILMADI — ölçüm turları için eğitim hâlâ gerekli.

**Kapsam — KAPANDI (2026-09-24):** `/gnn/train` sonucu artık
`uploads/models/<şablon>/field_gnn.npz`'ye yazıyor (`model_store.gnn_path`);
plaka eğitimi kiriş modelini ezmiyor. Korpus tek şablonlu olmalı (karışık
→ 422, şablonsuz → 422); şablonsuz run'lar atılıp `dropped.no_template`
olarak raporlanıyor. `.json` meta'ya `template_id` + `corpus` yazılıyor.
`/status?template_id=` o şablonun GNN'ini, `/predict` run'ın KENDİ
şablonunun GNN'ini kullanıyor. Eski global dosya yalnız meta'sındaki şablon
eşleşirse okunuyor. **Bugünkü diskteki eski dosya (8 graf) şablon kaydı
taşımadığı için hiçbir şablona verilmiyor.** Açık run tahmini, şablon
başına GNN eğitilene kadar skaler modele düşüyor. Dosya silinmedi.
Testler: `test_gnn_template_store.py` (7).

#### 1.3c GNN mimarisi — (a) TARAMA YAPILDI (2026-09-25), ÖLÇÜT YİNE TUTMADI
Kiriş kiris-v2 (192 mesh grafı, torch, aynı tohum, holdout ~%20):

| hidden | n_proc | u_y RMSE (mm) | vm RMSE (MPa) | u_max RMSE (mm) | vm_max RMSE (MPa) | süre |
|---|---|---|---|---|---|---|
| 24 | 2 | 1.120 | 11.28 | 2.564 | 25.0 | 5 dk |
| 24 | 4 | 1.081 | 11.04 | 2.578 | 24.9 | 7 dk |
| 24 | 8 | 1.026 | 10.84 | 2.464 | 24.8 | 50 dk* |
| 24 | 16 | 1.097 | 16.18 | 2.276 | 36.8 | 25 dk |
| 48 | 2 | 1.143 | 11.09 | 2.897 | 27.7 | 13 dk |
| 48 | 8 | **1.016** | **10.70** | **2.145** | 26.9 | 40 dk |

(*CPU çekişmesi.) **Sonuç:** mesaj geçişi derinliği yardım ediyor (2→8:
−%16 u_max), genişlik tek başına zarar veriyor, 16 adım aşırı uyuyor
(vm bozuluyor). En iyisi (48/8) bile ölçütün (0.12 mm) **18 katı**. Yani
şüphe kısmen doğru (bilgi yayılımı sınırlı) ama çare değil: sorun
mimarinin ölçeğinde değil, temsilinde — deplasman GLOBAL bir büyüklük,
yerel mesaj geçişi 7000 düğümde ankastre→uç ilişkisini öğrenemiyor.
**Karar:** (b)/(c)/(d) bu turda yapılmadı; GNN "prototip — sonuçlar
geçersiz" etiketiyle kalır. `/gnn/train` artık `hidden`/`n_proc` alır.
Şablon başına kiriş GNN'i (48/8) yeniden çözülen dosyalarla eğitildi
(`uploads/models/cantilever_beam/field_gnn.npz`) — sonuç aşağıda.

---

## 2. Veri ayıklama ve arşiv

### 2.1 Korpusa göre arşiv — ✅ kapandı (2026-09-20)

`GET /dataset/export?corpus_name=<ad>`: donmuş setin run'ları. `run_ids`
ile birlikte verilirse KESİŞİM alınır; bilinmeyen set 404. Setin TANIMI
da arşive konur (`corpus/corpus_<ad>.json`), içe aktarmada geri yazılır —
ama aynı adlı set varsa ÜZERİNE YAZILMAZ (yereldeki set kullanıcının
kendi kürasyonunu taşıyor olabilir); geri yazılanlar `restored_corpora`
ile döner. Panelde "Eğitim seti" seçici + "Eğitim setini indir" düğmesi;
donmuş set yoksa ikisi de çıkmaz.

Doğrulandı (çalışan sunucu): `plaka-v1` arşivi tam 198 run içeriyor —
korpusun tamamı, fazlası değil.

**Bilinen sınır:** arşiv, süzgeçten bağımsız olarak TÜM geometrileri alır
(run'lar geometrilere yabancı anahtarla bağlı; eksik geometri içe
aktarmada yetim run bırakır). Şu an 2369 geometri var → metaveri kısmı
~148 KB. Sete göre süzmek istenirse içe aktarmada yetim kontrolü gerekir.

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
- [x] **Arayüzde açma/kapama** — YAPILDI (2026-09-25, `b23e487`): statik
      çözüm panelinde "NLGEOM (büyük deformasyon)" + artım sayısı (1–500).
      Kapalıyken istek eskisiyle aynı. Test: `api/materials.nlgeom.test.ts` (3).
- [x] **Ön kontrol + soru — YAPILDI (2026-09-25).** `POST
      /geometry/{id}/solve/screen` lineer analitikle beklenen u/L döner
      (karar vermez). Arayüz: NLGEOM seçili değilse ve u/L > 0.10 ise
      "büyük deformasyon ile çözülsün mü?" sorar (Tamam → NLGEOM, İptal →
      lineer). Analitiği olmayan şablon/şablonsuz geometride sorulmaz.
      Test: `test_solve_screen.py` (2) + `materials.nlgeom.test.ts` (+1).
- [x] **Doğrulama — YAPILDI (2026-09-25), kesin çözümle tutuyor.** Vaka
      α = FL²/(EI) = 1 (6061-T6, L1000 T6.4 W40, F = 60.2 N, σ ≈ 220 MPa <
      akma 276). Referans: Bisshopp & Drucker büyük sehim çözümü.

      | | lineer teori | kesin (B–D) | FEA lineer | FEA NLGEOM es=3.2 (80k) | FEA NLGEOM es=6.4 (18k) |
      |---|---|---|---|---|---|
      | uç δ/L | 0.3333 | **0.3017** | 0.3325 | **0.3011** | **0.3017** |
      | uç Δx/L | 0 | **−0.0564** | 0.0000 | **−0.0562** | **−0.0564** |

      NLGEOM lineerden %9.4 küçük (önceki vakadaki %0.93'ün aksine kartın
      uygulandığı açıkça görülüyor), kesin çözümden %0.2 içinde; yatay
      kısalma da yakalanıyor (lineer çözüm bunu hiç göremez). 20 artım,
      yakınsadı, cutback yok. Regresyon: `test_nlgeom.py::
      test_nlgeom_buyuk_sehim_kesin_cozumle_tutar` (gerçek ccx, ~85 s).
- [x] **NLGEOM DOE tanımı — HAZIR (2026-09-25), henüz KOŞULMADI.**
      `docs/doe/nlgeom_kiris_v1.json`: kiriş, 6061-T6 (id 4), 150 örnek,
      L 900–1200 · T 4–6.5 · W 25–50 · Fy −100…−2 N, es/T 0.7–1.0,
      NLGEOM 20 artım. Ön eleme lineer u/L 0.10–0.34 ⇔ α = FL²/EI 0.3–1.0,
      akma %80. Kuru örnekleme: **150/150** geçti, α 0.30–1.02 düzgün
      dağılmış (7 kovada 15–30), σ 44–219 MPa, es/T ≤ 1.0.
      Kod: `DoeSpec.nlgeom` / `n_increments` / `screen_min_u_over_l`
      (varsayılan 0 → lineer DOE'ler değişmez), runner çözücüye iletir.
      Test: `test_doe_nlgeom.py` (5).
      Koşu (Codespace önerilir — yerelde ccx büyük mesh'te ~18 GB'a çıktı;
      örnek başı ~1–2 dk, toplam ~4–5 sa):
      `POST /doe/studies` gövde = JSON dosyası → `POST /doe/studies/{id}/run`.
- [x] **Korpus NLGEOM kapıları — YAPILDI (2026-09-25).** `CorpusSpec(nlgeom=True)`
      artık varsayılan u/L kapısını 0.5'e çeker (`NLGEOM_MAX_U_OVER_L`) ve
      lineer analitik kapısını kapatır; açıkça verilen değer korunur.
      Manifest `spec.nlgeom` taşır; `/scalar/train`, `/corpus/freeze`
      `nlgeom` sorgu parametresi alır. Lineer korpus değişmedi.
      Test: `test_ml_corpus.py` (+3).
- [ ] NLGEOM ayrı model: eğitim + kıyas (korpus düzeltmesinden sonra)

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

## 5. Delikli plaka eğitimi — ✅ kapandı (veri + kıyas + ürüne alma)

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

**Ürüne alındı (2026-09-20, A/B/C adımları):**
- [x] **Özellik vektörü şablona özgü.** Şablonun sayısal şema alanları +
      kategorik göstergeler (`notch_kind=u/v`) + ortak kuyruk. Kiriş için
      eski vektörle BİREBİR aynı: kaydedilmiş kiriş modeli yeni kodla da
      aynı tahmini verdi (u 6.543).
- [x] **Model dosyaları şablon başına** (`uploads/models/<şablon>/`).
      Eski global dosyalar silinmedi; korpusu hangi şablonsa yalnız ona
      salt okunur yedek.
- [x] **Hibrit tür eklendi.** Artık katmanına geometri ikili oranları
      otomatik giriyor (şablona özgü elle özellik yok): plakada ham
      özelliklerle u %0.64 / σ %1.86, oranlarla %0.29 / %1.30.
- [x] Panel: şablon seçici, şemadan üretilen form, üç model türü, seçili
      tür o şablonda yoksa mevcut türe görünür geçiş.

**Korpus dışı doğrulama** (yakınsama run 631, FEA u=0.059905 σ=188.49):
rf u +0.84% σ −14.33% · loglinear +1.72% / +1.63% · **hybrid −0.09% / +0.17%**

**Eğitilmiş modeller:** kiriş ve plaka için üçer tür kayıtlı.

**Sıradaki:** kalan 10 şablon için aynı yol (DOE → korpus → eğitim).

## 6. Hot-spot ekstrapolasyonu (Faz 0.6)

Ham `max_von_mises` tekil noktalardan okunuyor. Kısmi çözüm olarak
`max_von_mises_away` eklendi (kısıttan 1×T uzakta): gürültü %5.57 →
%1.20, teoriden +%10 → −%0.8, `thickness` üsteli −1.919 → −2.011
(teori −2).

### Ekstrapolasyon YAPILDI ve ÖLÇÜMLE ELENDİ (2026-09-24)

`app/postprocess/stress_probe.py` → `hot_spot_stress`: [0.4t, 1.0t]
penceresi bitişik dilimlere bölünür, her dilimde yüzey zarfı için maksimum
alınır, noktalara en küçük karelerle doğru geçirilip d=0'a uzatılır.
Mesafe varsayılan olarak TEPE düğümden ölçülür (`origin="peak"`).

Yazarken çıkan üç düzeltme:
1. Klasik iki noktalı IIW formülü (σ_hs = 1.67σ₁ − 0.67σ₂) tek nokta
   gürültüsünü ~1.8 katına çıkarıyor → pencere çok dilimden örneklenip
   regresyonla geçiliyor.
2. İlk tasarımda sabit yarı genişlikli bantlar ÖRTÜŞÜYORDU; aynı düğüm
   birkaç okuma noktası olarak sayılıyordu → bitişik dilimler.
3. Mesafeyi kısıttan ölçmek yanlış: **delikli plakada yığılma delikte,
   kısıt uzakta**. IIW'de de mesafeler hot-spot'un kendisinden ölçülür.

**Ölçüm — aynı geometrinin farklı mesh'leri, yayılma % (düşük = iyi):**

| yöntem | tüm mesh'ler | yakınsamış mesh'ler |
|---|---|---|
| ham tepe (`max_von_mises`) | %10.5 | %3.9 |
| **kaçınma (`max_von_mises_away`)** | **%7.8** | **%1.9** |
| hot-spot ekstrapolasyon | %65.1 | %38.0 |
| nokta yöntemi (tepeden 0.5t) | %13.7 | %7.8 |
| çizgi yöntemi (tepeden 0–1t ort.) | %13.8 | %10.6 |
| %99.5 yüzdelik | %20.8 | %10.2 |

**Ekstrapolasyon açık ara en kötüsü.** Sebep ölçüldü, tahmin değil:
`fit_r2` 0.00–0.68 arasında — pencerede gerilme mesafeye göre doğrusal
DEĞİL. Fizik basit: 500 mm'lik kirişte kökten 4–10 mm uzaklıkta gerilme
yalnız ~%1 değişiyor, mesh gürültüsü ise ±%5. Eğim gürültüden ibaret
olunca d=0'a uzatmak onu büyütüyor. Yöntem kaynak dikişi/çentik gibi
pencerede DİK ve düzenli gradyan olan vakalar için tasarlanmış; bizim
tekilliğimiz ankastre köşe artefaktı.

İkinci sebep: mesafe 3B Öklid, yani bir dilim tepe noktanın çevresindeki
KÜRESEL kabuk — IIW'deki gibi yüzey boyunca tek bir yol izlenmiyor.

**İki gerçek bulgu:**
- `max_von_mises_away` PLAKADA HİÇ İŞE YARAMIYOR: yayılması ham tepeyle
  birebir aynı (%11.4/%11.4), çünkü maske kısıta göre kurulu ama yığılma
  delikte. Kiriş dışındaki şablonlarda bu hedef bir şey düzeltmiyor.
- Yakınsamış mesh'lerde ham tepe zaten yalnız %3.9 oynuyor. Asıl kaldıraç
  farklı bir gerilme ölçütü değil, **mesh inceliği** (yakınsama paneli
  madde 3'te kapandı).

Kod duruyor (19 test, `fit_r2` ve `increasing_away` teşhisleriyle) ama
`scalars`'a EKLENMEDİ ve eğitim hedefi yapılmadı: %38 gürültülü bir sayıyı
hedef listesine koymak yanıltıcı olurdu.

### Seçilen yol: (c) + (b) — YAPILDI (2026-09-24)

**(c) Yakınsama kapısı** — `CorpusSpec.max_mesh_ratio` (varsayılan 1.0).
Mevcut `mesh_ratio_band` bir TUTARLILIK bandıydı (medyandan sapma):
korpusun tamamı kabaysa hepsini geçiriyordu. Yeni kapı mutlak incelik
eşiği. Eşik ölçümle seçildi (yukarıdaki diz tablosu), maliyeti diskteki
538 eğitim dosyasının 33'ü (**%6.1**). Kapı serttir — az örnek kalsa bile
kaba koşu geri alınmaz; `max_mesh_ratio=None` ile kapatılabilir.

**(b) Tepe merkezli ölçüt** — `stress_near_peak`: mesafe kısıta değil,
gerilmenin en yüksek olduğu düğüme göre ölçülür; hangi şablon olursa olsun
tekilliği bulur. `scalars`'a `max_von_mises_near_peak` +
`peak_probe_offset_mm` olarak yazılıyor (`/solve` sonrası, `.train.npz`
üzerinden — eski koşulara da geriye dönük uygulanabilir).

Okuma yanlılığı belgelendi: kabuk içindeki maksimum alındığı ve gerilme
uzaklaştıkça azaldığı için değer kabuğun İÇ kenarından gelir, yani
gerçekte `(offset − band) × L` mesafesinden okunur.

Hedef listesine (`TARGET_KEYS`) HENÜZ eklenmedi: yeni ölçüt yalnız bundan
sonraki koşularda yazılıyor, mevcut 538 dosyada yok. Eğitim hedefi yapmadan
önce geriye dönük doldurma gerekir (1.1c'deki gibi, `.train.npz`'den
yeniden hesapla) — ayrı mikro-adım.

### Kalan
- [x] `max_von_mises_near_peak`'i mevcut koşulara geriye doldur — YAPILDI
      (2026-09-24). `/backfill-stress-probe` `_away` dolu run'ı TÜMDEN
      atlıyordu, tepe ölçütü eski koşulara hiç yazılamıyordu; artık iki
      ölçüt ayrı doldurulur, mevcut değerin üzerine yazılmaz. Dev DB:
      584 çözülmüş run → 500 şablonlu run'ın **500'üne** yazıldı
      (kiriş 281/281, plaka 219/219), 84 şablonsuz atlandı, 0 hata. Aynı
      geçişte 263 run'a eksik `_away` de yazıldı. Test:
      `test_backfill_near_peak.py` (2).
- [x] `max_von_mises_near_peak` hedef listesinde (`TARGET_KEYS`, 4. hedef) —
      YAPILDI (2026-09-24). Eksikse NaN, run düşmez; eski 3 hedefli model
      dosyaları bundle'ın kendi `target_keys`'iyle okunmaya devam eder.
      Test: `test_target_near_peak.py` (3).

  **Kıyas (holdout, bellekte eğitildi — diskteki modeller değişmedi):**

  | korpus | model | vm (ham) MAPE | vm_away MAPE | vm_near_peak MAPE |
  |---|---|---|---|---|
  | set kiris-v2 (200) | loglinear | 2.0% | **0.7%** | 2.4% |
  | | hybrid | 1.9% | **0.6%** | 2.3% |
  | set plaka-v1 (198) | loglinear | 2.2% | 2.2% | 7.6% |
  | | hybrid | **1.3%** | **1.3%** | 7.8% |
  | canlı kiriş (222) | hybrid | 2.1% | **0.6%** | 2.5% |
  | canlı plaka (201) | hybrid | **1.8%** | **1.8%** | 7.8% |

  RF her hedefte %11–17 (ayırt etmiyor). **Sonuç: `near_peak` hiçbir
  korpusta en iyi değil.** Kirişte `_away`'in ~4 katı hata; plakada ham
  değerin ~4–6 katı. Plakada delik kenarı TEKİLLİK DEĞİL (sonlu Kt) —
  yakınsamış mesh'te ham tepe fiziksel olarak doğru ve düzgün tahmin
  ediliyor; `near_peak` ise farklı bir büyüklüğü (tepeden 0.5×L uzakta)
  ve tepe düğümün mesh'e bağlı konumu yüzünden daha gürültülü okuyor
  (yukarıdaki yayılım ölçümü: %7.8 — tahmin hatasıyla aynı mertebe).
  Hedef olarak duruyor (zararsız, NaN toleranslı) ama akma kontrolü
  hâlâ `_away` → ham sırasını kullanıyor; değiştirilmedi.
- [x] **Kiriş kök filleti — YAPILDI (2026-09-25), tekillik YAKINSAMADI.**
      Düz kutuda kökte geometrik köşe yok (tekillik BC kenarından), fillet
      ancak destek modellenince konabiliyor. Yeni alanlar: `root_fillet` (r,
      0 → duvar yok, geometri eskisiyle birebir), `wall_thickness` (20),
      `wall_margin` (20). r > 0: x<0'da duvar bloğu + birleşim kenarlarına
      fillet, ankastre duvarın ARKA yüzüne taşınır.
      Yan düzeltmeler: eski run'da olmayan şablon alanı özellik vektörüne 0
      değil şablon VARSAYILANIYLA girer (`_schema_defaults`); anahtarsız eski
      bundle `FEATURE_KEYS`'e düşer. Testler: `test_cantilever_root_fillet.py`
      (4) + 3 şema testi güncellendi.

      **Gerçek ccx, 500×10×50, 500 N, düz tet (C3D10), global eleman boyu:**

      | es | r=0 düğüm | r=0 u / vm | r=5 düğüm | r=5 u / vm |
      |---|---|---|---|---|
      | 8.0 | 7 255 | 23.92 / 330.6 | 9 496 | 23.59 / 308.9 |
      | 5.0 | 21 185 | 23.96 / 337.0 | 27 724 | 23.67 / 329.5 |
      | 3.5 | 52 327 | 23.74 / 330.0 | 71 305 | 23.70 / 354.9 |
      | 2.5 | 126 150 | 23.69 / 322.7 | 167 817 | 23.71 / 367.7 |
      | 1.8 | — | — | 424 240 | — / 395.0 |

      Deplasman iki durumda da teoriye (23.81) yakın. **r=5'te vm monoton
      ARTIYOR** (309 → 395, son adımda +%7). Tepe yeri ölçüldü: duvar arka
      yüzü ~14 MPa (BC tekilliği gerçekten gitti), tepe FİLLET BÖLGESİNDE,
      kesit köşesinde (5,0,0) / (4.2,0,50) — iki kök filletinin kirişin
      KESKİN boyuna kenarıyla buluştuğu nokta. Kiriş bölgesi (x>5) de yavaş
      artıyor (308 → 322). Olası iki sebep, ayrılmadı: (1) fillet global
      eleman boyuyla çözünmüyor (r/es = 2.8'de bile), yerel inceltme gerek;
      (2) köşe birleşim noktası kendisi tekil (boyuna kenarlar keskin).
      İkisi de mühendislik kararı (yerel mesh inceltme / boyuna kenar
      radyusu) — agent karar vermedi.

      **Yerel inceltme ölçümü (2026-09-25, yalnız ölçüm betiği, ürün kodu
      değişmedi):** global es=5, kök çevresine (x −3…12) gmsh Box alanı ile
      yerel boy h. Eğri fillet yüzeyinde ters jacobian'lı C3D10 çıktı (8.4
      ile aynı) → betikte `optimize("HighOrder")` açıldı.

      | h (mm) | düğüm | köşe vm (MPa) | fillet ortası vm (MPa) |
      |---|---|---|---|
      | 2.0 | 35 167 | 384.7 | 348.4 |
      | 1.2 | 62 658 | 410.3 (+6.7%) | 354.8 (+1.8%) |
      | 0.8 | 140 361 | 417.4 (+1.7%) | 362.0 (+2.0%) |
      | 0.55 | — | ccx 600 s zaman aşımı (~18 GB bellek) | — |

      **Köşe değeri yakınsıyor:** artışlar küçülüyor (+25.6 → +7.1 MPa),
      geometrik seri limiti ≈ 420 MPa. Yani sebep büyük olasılıkla
      (1) çözünürlük — köşe birleşimi tekil DEĞİL; boyuna kenar radyusu
      (c) bu ölçüme göre gerekmiyor. Fillet ortası adım başına ~%2 artmaya
      devam ediyor — tam yakınsamadı, 3 nokta az. Güven: orta; h=0.55
      bitseydi kesinleşirdi.
      **Ürün için sonuç:** filletli kirişte gerilme hedefi global eleman
      boyuyla mesh'e bağlı (es=2.5'te bile ~%12 düşük). Kullanılabilir
      olması için ürüne yerel mesh inceltmesi (+ yüksek mertebe
      optimizasyonu, 8.4) gerekiyor — ikisi de mesh ayarı, karar sende.
      O zamana kadar `root_fillet > 0` DOE'de gerilme hedefi için
      kullanılmamalı.
- [ ] Omuz geçişi filleti — kademeli mil (madde 7) ile birlikte

---

## 7. Şablon kütüphanesi (Faz 0.4)

16 şablon — Grup 3 YAPILDI (2026-09-25), hepsi gerçek OCC geometrisi,
hacimle doğrulandı (`test_templates_grup3.py`, 11 test), şemaları var:
- [x] `t_bracket` — sırt plakası + konsol raf, `rib_kind` none/gusset
      (üçgen prizma, gövdeye kaynaşık). Analitik yalnız kaburgasız raf;
      kaburgalı DOE'de `require_analytic_ok=False` gerekir.
- [x] `l_bracket_bolted` — dik bacakta 2 cıvata deliği, ankastre DELİK
      yüzeylerinde (gerçek delik yığılması); analitik yatay bacak konsolu.
- [x] `flange` — halka plaka, n cıvata deliği ankastre, boru deliğinden
      eksenel çekme. `analytic=None` (DOE ön elemesi atlanır).
- [x] `stepped_shaft` — omuz filleti GEOMETRİDE; Kt Peterson/Norton
      üstel tablosu (D/d ara değer, r/d 0.01–0.3), sehim Castigliano;
      `characteristic_length = r` (fillet çözülsün diye).
Hiçbiri ccx ile koşulmadı — DOE/yakınsama ayrı iş. Şablon başına
mesh yakınsaması ölçülmeden eğitime alınmamalı (kök filleti dersi).

---

## 8. Küçük ama gerçek sorunlar

### 8.1 `/solve` `region` alanını sessizce yok sayıyor — ✅ kapandı (2026-09-20)

Kök neden: `region` SolveBC modelinde YOKTU, pydantic sessizce atıyordu.
Eski kodda canlı olarak yeniden üretildi: bölge adıyla fixed + cload →
HTTP 200, `.inp`'te `*CLOAD` bloğu yok, toplam Fy = 0 (yüksüz "başarılı"
model).

Düzeltme: `SolveBC.region` + `/solve` de bölgeleri çözüyor (DOE ile aynı
`bind_scenario_bcs`); bilinmeyen bölge 422 + mevcut bölgelerin listesi.
Ayrıca `_require_targets`: hiçbir yüzey/kenar/düğüme bağlanmayan
fixed/cload/pressure/displacement/sliding/bearing 422 — hedefsiz yük
ccx'te hata vermez, sıfır deplasmanlı "başarılı" sonuç üretir. `gravity`
(hacim yükü) ve `rigid_body` (referans düğüm) muaf.

Doğrulandı: bölge adıyla toplam Fy = −150.00 N (beklenen −150).

### 8.2 Test malzemesi çöpü — ✅ kapandı (2026-09-25), AMA VERİ KAYBIYLA

**Kök çözüm:** `tests/conftest.py` testleri `cae_test` veritabanına
yönlendirir (`app` import edilmeden önce `DATABASE_URL`; yoksa yaratılır;
şema `alembic upgrade head`; kimlik sayaçları 10M'dan başlar ki test
dosyaları dev'in `uploads/` dosyalarıyla çakışmasın). Kapatmak:
`CAE_TESTS_USE_DEV_DB=1`. Dev DB'den 44 `TestCustomSteel_*` malzemesi ve
453 `box.step` test run'ı (+2592 test geometrisi) silindi.

**OLAY — 2026-09-25, geri dönüşsüz:** `cae_test`'e geçiş, eski
fixture'lardaki `safe_cleanup`'ı "izinli" saydı ve `rmtree(uploads/…)`
GERÇEK dosyaları sildi: `uploads/runs/` (~716 klasör: 538 `.train.npz`,
`.frd.gz`, `.inp`), `uploads/models/` (skaler modeller, `field_gnn.npz`,
korpus manifestleri), `uploads/meshes/`. DB (`cae_dev`) ve `uploads/*.step`
sağlam. Düzeltme: `db_guard` dosya silmeyi yalnız açık
`CAE_ALLOW_UPLOAD_WIPE=1` ile yapar; `RESTART IDENTITY` kaldırıldı.

**Kurtarma:** manifestler `study_id` ile yeniden donduruldu — kiris-v2
200 → **192** (bugünkü yakınsama kapısı 8 run daha atıyor), plaka-v1 198
→ 198; skaler modeller yeniden eğitildi (hibrit holdout u_max MAPE kiriş
%0.20, plaka %0.29 — eskisiyle aynı mertebe). Koşu dosyaları ccx ile
yeniden üretiliyor (`resolve_runs`: 430 run, DB'ye yazmaz; ilk 93'te
u sapması %0.00–0.01, yani deterministik). Eski `field_gnn.npz` (8 graf,
şablonsuz, zaten geçersiz) geri gelmeyecek.

Eski metin:
DB'de 16 adet `TestCustomSteel_*` malzemesi birikmiş (id 34–49) —
testlerin bıraktığı kayıtlar. 21 malzemenin 16'sı çöp. Testler rollback
yapmalı ya da ayrı test DB'si kullanmalı.

Aynı kök neden run'larda da var: her tam pytest koşusu `cae_dev`'e ~13
şablonsuz run bırakıyor ("Test Case 1", "PDF testi" …; örn. id 640–663).
Eğitimi etkilemiyor (korpus `no_template` ile atıyor) ama geçmişi ve
veri seti sayılarını kirletiyor. `tests/db_guard.py` bunu önlemek için
yazılmış olabilir — bağlı mı kontrol edilmeli.

### ~~8.3 `doe_study_id` geriye dönük boş~~ — KAPANDI (2026-09-20)
Sütunu ekleyen `b9c0d1e2f3a4` mevcut satırları doldurmamıştı. Bağ zaten
veride (`doe_cases.run_id`), yalnız run tarafından geriye bakılamıyordu.

`app/doe/backfill.py` + veri migration'ı `c0d1e2f3a4b5`: boş olanı
doldurur, **dolu değeri asla ezmez**, bir run iki çalışmaya bağlıysa
dokunmaz (belirsiz), tekrar çalıştırılabilir. Elle de koşulabilir:
`python -m app.doe.backfill [--dry-run]`.

Dev DB'de ölçüm (TODO'daki "#5, #6, #8, #9" numaraları tutmuyordu):

| çalışma | ad | dolduruldu |
|---|---|---|
| 1 | kalite-200 cantilever | 200 |
| 2 | cantilever_beam LHS | 20 |
| 3 | kiris-egitim-v2 | 200 |
| 4 | kiris-dogrulama | 12 |
| 5 | kalite-200 plate_with_hole | (zaten doluydu) 200 |

Toplam 432 run dolduruldu, **çelişki 0**. Kalan 377 boş run gerçekten
DOE dışı (elle açılmış + 8.2'deki test artıkları) — uydurma çalışma
atanmadı. `GET /geometry/runs?doe_study_id=N` beşi de süzüyor (canlı
doğrulandı: 200/20/200/12/200 kayıt).

Testler: `tests/test_doe_backfill.py` (8) — ezmeme, belirsiz run,
idempotenlik, DOE dışı run boş kalır, `--dry-run` yazmaz.

---

### 8.4 gmsh ters kuadratik eleman (`nonpositive jacobian`)
Plaka DOE'sinde 200 örnekten 2'si (#62 d=24 W=77.5 es=3.82; #129 es=3.03)
ccx'te `*ERROR in e_c3d: nonpositive jacobian` ile düştü — muhtemelen delik
yüzeyindeki eğri kenar-orta düğümleri. Sistem doğru davrandı (`failed`,
sessiz `solved` değil).

**Hata mesajı kısmı KAPANDI (2026-09-23).** `_ccx_error_lines` ccx log'undaki
`*ERROR` bloklarını koşu mesajına taşıyor. Gerçek koşularda ölçüldü:

| | mesaj |
|---|---|
| eski | `CalculiX hata (exit=201). Log: uploads\runs\809\run809.ccx.log` |
| yeni | `… *ERROR in e_c3d: nonpositive jacobian determinant in element 38 …` |

Sabit sütun boşlukları sıkıştırılıyor; log stdout+stderr birleşimi olduğu
ve ccx aynı satırı ikisine de yazdığı için yinelenen blok eleniyor (run
809 ve 876'da görüldü). `*WARNING` mesaja girmez, en fazla 2 blok / 240
karakter. Testler: `test_ccx_error_message.py` (7). 714 backend testi
geçiyor.

**AÇIK KALAN — mühendislik kararı sende:** ters jacobian'ın kendisi.
`Mesh.HighOrderOptimize` bir mesh ayarı; `CLAUDE.md` kuralı 4 gereği agent
kendiliğinden açmaz. Seçenekler: (a) olduğu gibi bırak, DOE'de binde 10
örnek düşer ve sebebi artık mesajda görünür; (b) şablon/mesh ayarlarına
açık bir "yüksek mertebe optimizasyonu" anahtarı eklensin (varsayılan
kapalı, kararı sen verirsin); (c) o koşularda eleman boyutu değişsin.

## Ara maddeler — ana maddeler (6, 4) bitince yapılacak (2026-09-24)

- [x] **Panel eğitim isteğine şablon gönderiyor — YAPILDI (2026-09-25).**
      `trainScalarRf`/`trainFieldGnn` seçili şablonu yollar; canlı süzgeçle
      eğitim artık 422 vermez. Aynı adımda panele "NLGEOM (büyük deformasyon)
      modeli" anahtarı: durum, eğitim ve parametre tahmini o modele gider.
      Test: `SurrogatePanel.test.tsx` (+1).
- [ ] **1.3c GNN mimarisi.** Önce (a) `n_proc`/`hidden` taraması (yalnız
      ölçüm), sonra sonuca göre (b)/(c)/(d). Şablon başına GNN yeniden
      eğitilmeli — diskteki eski `field_gnn.npz` şablon kaydı taşımadığı
      için artık hiçbir şablona verilmiyor.

## Öncelik sırası (öneri)

1. ~~**0.1** — yüzey yükü doğrulaması~~ ✅ kapandı
2. ~~**3** — solver yakınsaması~~ ✅ kapandı
   ~~**4.0** — NLGEOM sonuç okuma hatası~~ ✅ kapandı
3. ~~**5** — delikli plaka verisi + kıyas + ürüne alma~~ ✅ kapandı
4. ~~**2.1** — korpusa göre arşiv~~ ✅ kapandı
5. ~~**8.1** — /solve region~~ ✅ kapandı
6. ~~**8.3** — `doe_study_id` geriye dönük~~ ✅ kapandı
7. **1** — GNN (en büyük iş, kontur tahmini için zorunlu) — 1.1, 1.2, 1.3a, 1.3b kodu ✅; ölçüt tutmadı → 1.3c mimari kararı
8. **4** — NLGEOM arayüz + veri seti
9. **6, 7, 8.2** — iyileştirmeler
10. **5 (devam)** — kalan 10 şablon için DOE + eğitim

**Crash'e (Faz 1) geçmeden önce en az 0.1 (✅) ve 3 (✅) kapanmalı** — crash de çok artımlı `.frd` üretecek; 4.0 aynı sınıftan — ikisi de
solver altyapısını ilgilendiriyor, crash aynı altyapıyı kullanacak.
