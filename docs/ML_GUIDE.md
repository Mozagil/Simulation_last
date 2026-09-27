# ML / Surrogate Rehberi

> Simülasyon mühendisi için, ML'e yeni başlayan biri varsayılarak yazıldı.
> Her iddia kodda doğrulanmış; ölçülen sayılar gerçek koşulardan.
>
> Son güncelleme: Faz 0.6 · ankastre kiriş doğrulaması tamamlandı.

---

## 1. Neden surrogate?

Bir FEA çözümü dakikalar sürer. Tasarım optimizasyonunda aynı kirişi 500
farklı boyutla denemek istersen günler eder.

Surrogate şu fikir: **bir kez 200 çözüm yap, sonuçlara bir fonksiyon uydur,
yeni sorulara o fonksiyonla milisaniyede cevap ver.**

Kritik nokta — surrogate FEA'nın yerine geçmez:

- **İnterpolasyondur.** Eğitim verisinin kapsadığı uzayın *içinde*
  güvenilir, dışında değil. Model bunu bilir ve uyarır (`out_of_domain`).
- **Kesinlik sınırlıdır.** Eğitim verisinin kendi gürültüsünün altına
  inemez. Bizde bu taban %1 (deplasman) ve %1.2 (maskeli gerilme).
- **Tasarım tarama aracıdır, onay aracı değil.** "Bu 500 tasarımdan hangi
  20'sini ccx ile çözmeye değer" sorusuna cevap verir. Nihai doğrulama
  yine FEA'dır.

---

## 2. Zincir — beş aşama

```
1. DOE      → hangi 200 vakayı çözeceğiz?      (parametre uzayını tara)
2. Çözüm    → ccx her birini çözer, .frd üretir
3. KORPUS   → çözümlerin hangileri eğitime UYGUN?  (süzgeç)
4. Eğitim   → uygun olanlardan fonksiyon çıkar
5. Tahmin   → yeni L/T/W/F ver, cevabı al
```

Her aşamada bir şeyin bozuk olması sonrakini **sessizce** zehirler.
Bulduğumuz sorunların çoğu tam olarak buydu: hata vermiyor, sadece yanlış
sonuç veriyordu.

---

## 3. KORPUS nedir

**Korpus = eğitime uygun bulunmuş çözümlerin dondurulmuş listesi.**

Neden gerekli: DB'de her türlü run var — şablonsuz, farklı analiz tipi,
büyük deformasyona girmiş, aşırı kaba mesh'le çözülmüş. Hepsini eğitime
sokarsan model çöp öğrenir. Korpus bir **süzgeç ve anlık görüntü**.

Kod: `backend/app/ml/corpus.py`

### Süzgeç kriterleri (`CorpusSpec`)

| kriter | varsayılan | neden |
|---|---|---|
| `template_id` | — | Tek şablon. Kiriş ve delikli plaka aynı modele girmez. |
| `analysis_type` | `static` | Modal ve statik farklı fizik. |
| `max_u_over_L` | 0.10 | u/L bunun üstündeyse **büyük deformasyon**: lineer çözücü sessizce yanlış cevap vermiştir. |
| `mesh_ratio_band` | 0.5 | Medyan mesh oranından çok sapan run'lar atılır. |
| `require_analytic_ok` | True | FEA analitikten çok saparsa o run şüphelidir. |

Ayrıca **tek malzeme**: `(E, ν)` çiftine göre çoğunluk tutulur, gerisi
`other_material` olarak elenir. S235 ve S355 ikisi de (210 GPa, 0.3)
olduğu için *aynı* sayılır ve ikisi de kalır; 6061-T6 (68.9 GPa) elenir.

### Bizim korpusumuz

```
taranan            : 468
tutulan            : 225   ← eğitim seti
  no_template      :  40   (elle yüklenmiş geometriler)
  analytic_warn    :  12   (FEA teoriden çok sapmış)
  other_material   : 165   (alüminyum)
  large_displacement: 23   (u/L > 0.10)
  mesh_outlier     :   3
```

Başlangıç noktamız **8 örnekti**. 225'e çıkardık.

### "Canlı süzgeç" vs "dondurulmuş"

- **Canlı süzgeç**: her eğitimde DB yeniden taranır. Veri ekledikçe korpus
  büyür. Geliştirme sırasında pratik.
- **Dondurulmuş** (`freeze`): run id listesi dosyaya yazılır. Aynı korpusla
  tekrar eğitince **aynı sonucu alırsın**. Yayına çıkarken şart —
  "bu model şu 225 çözümden eğitildi" denebilmesi için.

---

## 4. SKALER model (çalışıyor, doğrulandı)

**Ne verir:** Tek sayılar — `max_displacement`, `max_von_mises`,
`max_von_mises_away`. Yani "bu kiriş en fazla kaç mm sehim yapar".

**Ne vermez:** Kontur. Gerilmenin *nerede* olduğunu bilmez, sadece en
büyüğünü.

Kod: `backend/app/ml/scalar_rf.py`

### Girdiler (11 özellik)

```
length, thickness, width          ← geometri
element_size                      ← mesh çözünürlüğü
youngs_modulus, poisson_ratio     ← malzeme
load_fx, load_fy, load_fz         ← yük
pressure_mpa, dimension
```

### Model: log-log doğrusal + artık üzerinde RF

Başta saf Random Forest vardı ve **çalışmadı**. Sebebi öğretici:

Kirişin fiziği bir **kuvvet yasası**:
```
u = 4FL³/(E·W·T³)
log u = log(4F) + 3·logL − logE − logW − 3·logT
```

Log uzayında bu **düz bir düzlem**. Random Forest ise veriyi dik
basamaklarla böler — düzlemi basamaklarla taklit etmeye çalışır ve 225
örnekle beceremez.

Ölçüm (225 örnek, gerçek kutu, ölçülen gürültüyle):

| model | MAPE (deplasman) |
|---|---|
| RF, ham girdi + ham hedef | **%42.9** |
| RF, ham girdi + log hedef | %27.0 |
| **log-log doğrusal** | **%0.8** |
| log-log doğrusal + RF artık | %0.8 |

Neden ikisi birden: saf kuvvet yasasında RF zarar vermiyor (%0.80→%0.84),
sapma varsa kazandırıyor. Sentetik gerilme yığılması eklendiğinde: yalnız
doğrusal %1.13 → +RF %0.93. Delikli plaka gibi saf olmayan şablonlar için
bu güvence gerekli.

### Neden bu model daha iyi: üsteller okunabilir

Log-log doğrusal modelde katsayılar **doğrudan fiziksel üsteldir**. Gerçek
verideki sonuç:

| özellik | model | teori | | model | teori |
|---|---|---|---|---|---|
| | **deplasman** | | | **gerilme** | |
| length | +2.989 | +3 | | +1.025 | +1 |
| thickness | −2.980 | −3 | | −1.919 | −2 |
| width | −1.009 | −1 | | −0.982 | −1 |
| load_fy | +1.000 | +1 | | +0.998 | +1 |
| element_size | +0.004 | — | | −0.072 | — |

Model, 225 gerçek CalculiX çözümünden **kiriş teorisini yeniden
keşfetti**. Formülü hiç görmedi.

Bu R²'den çok daha güçlü bir doğrulama: ezberleyen bir model bu üstelleri
veremez. `element_size ≈ 0` de ayrıca değerli — mesh boyutunun fizikle
ilgisi olmadığını model kendi buldu, convergence taramasının bağımsız
teyidi.

### Hedefler: ham vs maskeli gerilme

`max_von_mises` ankastre köşeden okunuyor. Orası idealize problemde **tekil
bir nokta** — σ mesh inceldikçe sınırsız büyür, yakınsamış değeri yoktur.
Ölçtük:

| | ham max σ | 1×T uzakta |
|---|---|---|
| gürültü tabanı | %5.57 | **%1.20** |
| teoriden sapma | +%10 | **−%0.8** |

Bu yüzden `max_von_mises_away` eklendi: kısıttan **sabit fiziksel mesafe**
(1×kalınlık) uzaktaki düğümler üzerinden maksimum.

"Bir sonraki eleman" demek yetmezdi — o mesh'e bağlı bir mesafedir
(es=15'te 15 mm, es=3'te 3 mm), gürültü kaybolmaz şekil değiştirir.

Kod: `backend/app/postprocess/stress_probe.py`

---

## 5. GNN ALAN modeli (prototip — çalışmıyor)

**Ne vermesi gerekiyor:** Her düğümde deplasman ve gerilme. Yani
**kontur çizebilecek** çıktı. Skaler model "en fazla 23.8 mm" der; alan
modeli "şu düğümde şu kadar" der.

**Neden GNN:** Mesh doğal olarak bir **graftır** — düğümler ve onları
bağlayan elemanlar. Görüntü değil (piksel ızgarası yok), tablo değil
(komşuluk önemli). Graph Neural Network tam bu yapı için.

Mantığı: her düğüm komşularından bilgi toplar, birkaç turda bilgi mesh
boyunca yayılır. Fiziğe benziyor — gerilme de komşuluk üzerinden yayılır.

Kod: `backend/app/ml/gnn.py`

### Şu anki durum: üç yapısal sorun

**1. Mesh bağlantısı hiç yazılmıyor.**
`calculix.py` `write_inputs(path, X, None)` çağırıyor — connectivity daima
`None`. Diskteki tüm `.train.npz` dosyalarında `connectivity.shape = (0,0)`.

Sonuç: graf, koordinatlardan **k-NN (k=6)** ile kuruluyor. Yani
"MeshGraphNet" dediğimiz şey şu an mesh grafı değil, bir **nokta bulutu
komşuluğu**. Eleman bağlantısı `.inp` dosyasında zaten var, sadece
geçirilmiyor.

**2. Normalizasyon yok.** Ham kanallar aynı katmana giriyor:

| kanal | aralık |
|---|---|
| x, y, z | 0 … 700 |
| fixed_ux/uy/uz | 0 / 1 |
| youngs_modulus_mpa | 210000 |
| density_tonne_mm3 | 7.85e−9 |

E ve koordinatlar gizli katmanı tek başına dolduruyor; BC bayrakları ve
yoğunluk sayısal olarak **yok hükmünde**. Çıktı tarafı da normalize değil
(u ~ mm, σ ~ 150 MPa aynı lineer katmandan).

**3. Gerçek eğitim yok.** `train_gnn`: son katmana en küçük kareler +
process ağırlıklarına 6 adım kaba gradyan (`lr=1e-4`). **Encoder hiç
güncellenmiyor** — sabit rastgele projeksiyon olarak kalıyor. Dosyanın
kendi docstring'i de bunu kabul ediyor.

### Ölçülen sonuç

```
node_rmse.u_y              = 12.35 mm
scalar_rmse.max_displacement = 21.26 mm
```
Aynı setteki gerçek deplasmanlar 22–93 mm arası. **Hata sinyalin
mertebesinde** — "hep sıfır de" tahmininden ayırt edilemez.

### Neden böyle: bilinçli bir erteleme

PyTorch eklenmedi çünkü Codespace imajında disk doluyordu. NumPy ile
yazılmış bu iskelet, şemanın (düğüm girdi/çıktı + kenar) yerinde
olduğunu gösteriyor ama **model değil, prototip**.

Düzeltmek için gerekenler, sırayla:
1. `connectivity`'yi yaz (eleman bağlantısı zaten `.inp`'de)
2. Girdi/çıktı normalizasyonu
3. Gerçek eğitim — PyTorch Geometric ya da NumPy'de düzgün backprop

---

## 6. ML terimleri, FEA diliyle

**Feature / target.** Girdi (L, T, W, F, E) ve hedef (u_max, σ_max).

**Eğitim / test ayrımı (holdout).** Modeli 168 örnekle eğitip aynı 168'de
sınamak, öğrenciye çalıştığı soruları sormaktır. 57 örnek kenara ayrılır,
model onları hiç görmez, başarı orada ölçülür.

> *Bu projede bozuktu:* 12'den az örnekte `X_test = X_train` atanıyordu,
> yani "test R²" aslında eğitim R²'siydi. Gördüğün "R² 0.739, n_test 8"
> tam olarak buydu. Düzeltildi.

**Overfitting (ezberleme).** Model veriyi ezberler, genelleme yapamaz.
Belirtisi: eğitimde mükemmel, testte kötü.

**R².** Varyansın ne kadarı açıklanıyor. **Yanıltıcı olabilir** — bizde
R² 0.92 iken bağıl hata %74'tü. Sebep: u değerleri 0.07–41 mm arası
(~600×). R² büyük değerlerin hakimiyetinde; model 30 mm'yi %5, 0.1 mm'yi
%200 hatayla bilse bile R² yüksek çıkar.

**MAPE.** Ortalama bağıl hata. **Mühendis için asıl metrik.** "%2 hata"
doğrudan anlaşılır.

**OOD (out of domain).** Eğitim uzayının dışı. Model orada da bir sayı
üretir ama güvenilmez — bu yüzden uyarı verir.

**Gürültü tabanı.** Hedefin kendi belirsizliği. Mesh inceltmekle altına
inilemeyen sınır. Modelin doğruluk tavanını **baştan belirler**: hedef
±%5 oynuyorsa model ondan iyi olamaz.

---

## 7. Komutlar

| komut | ne yapar | ne zaman |
|---|---|---|
| `POST /doe/quality-set` | 200 örneklik tarama, ccx'i sırayla koşturur | Yeni veri gerektiğinde |
| `GET /doe/studies` | Çalışmaları listeler | id bulmak için |
| `GET /doe/studies/{id}` | Kaçı bitti, hata var mı | Koşarken izlemek |
| `POST /convergence` | Tek geometri, mesh'i kabadan inceye tarar | Yeni şablonda bir kez |
| `GET /convergence/{id}` | Yakınsama tablosu + gürültü tabanı | Tarama bitince |
| `GET /convergence/{id}/stress-probe` | Maskeli gerilmeyi dener | Standoff oranı seçerken |
| `POST /convergence/backfill-stress-probe` | Eski run'lara maskeli skaleri ekler | Bir kez, DOE'den önce |
| `POST /surrogate/corpus/freeze` | Eğitim setini dondurur | Yayına çıkarken |
| `GET /surrogate/corpus/{name}` | Korpus manifesti | Neyin elendiğini görmek |
| `POST /surrogate/scalar/train` | Skaler modeli eğitir | Veri değiştiğinde |
| `POST /surrogate/predict/params` | L/T/W/F → tahmin | Kullanım anı |
| `GET /surrogate/status` | Hangi modeller eğitilmiş | Durum kontrolü |

**Arayüzde:** ML Stüdyo → Hızlı tahmin paneli. "RF eğit" ve "Parametreyle
tahmin" butonları bu uçları çağırır; üstel tablosu ve kiriş teorisi
karşılaştırması orada görünür.

---

## 8. Durum ve eksikler

| aşama | durum |
|---|---|
| DOE + analitik ön eleme | ✅ |
| Mesh convergence | ✅ ölçüldü, bant belirlendi |
| Korpus | ✅ 225 örnek (başlangıç 8) |
| Skaler model | ✅ doğrulandı, MAPE %0.19 |
| Tahmin arayüzü | ✅ teoriyle karşılaştırmalı |
| **GNN alan modeli** | ❌ prototip, çalışmıyor |
| **Diğer 11 şablon** | ❌ yalnız kiriş doğrulandı |
| **Büyük deformasyon** | ❌ NLGEOM yok, u/L>0.10 eleniyor |
| **Çok malzemeli** | ❌ korpus tek E kabul ediyor |

### Bilinen nüans — bağımsızlık

Korpus kapısı `require_analytic_ok=True`, yani FEA'nın analitikten çok
saptığı 12 run elendi. Veri, teoriyle uyumlulara doğru **hafifçe
filtrelenmiş**.

Bu "model teoriyi öğrendi" iddiasını çürütmez (kapı geniş bir eşik,
üsteller ondan çıkmaz) ama tam bağımsız da değil. Kesinleştirmek için:
kapıyı kapatıp yeniden eğit, üsteller değişmiyorsa sonuç sağlamdır.

---

## 9. Sıradaki adımlar

**a. GNN'i çalışır hale getir** — kontur tahmini istiyorsan zorunlu.
En büyük iş.

**b. İkinci şablonu doğrula** (delikli plaka) — altyapı hazır, her biri
1-2 saat. Gerilme yığılması olduğu için log-log doğrusal tek başına
yetmeyecek; RF artık katmanının gerçekten işe yarayıp yaramadığını
görmek açısından iyi bir sınav.

**c. Bağımsızlık testi** — en ucuzu, bir eğitim koşusu.

**d. NLGEOM** — büyük deformasyon ayrı bir model ailesi.
