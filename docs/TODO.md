# Yarım Kalan İşler

> Claude Code için devir dokümanı. Her madde: **ne**, **neden**, **nasıl
> doğrulanır**. Ölçülmemiş şeyler açıkça işaretli — onları "çalışıyor"
> varsayıp üstüne inşa etme.
>
> Branch: `feature/surrogate-accuracy` · `main`'e merge edilmedi
> Son durum (2026-09-19): 576 backend testi geçiyor (1 atlandı, ccx ile
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

## 3. Solver yakınsaması (Faz 0.6)

CalculiX `.sta` ve `.cvg` dosyaları **zaten üretiliyor**
(`uploads/runs/{id}/run{id}.sta`), ama **okunmuyor**. Sıfırdan üretmek
değil, var olanı parse etmek gerekiyor.

- [ ] `.sta` / `.cvg` parse: artım sayısı, cutback, yakınsama durumu
- [ ] `AnalysisRun.scalars`'a özet (`converged`, `n_increments`,
      `n_cutbacks`)
- [ ] **Yakınsamamış çözüm `solved` sayılmamalı** — şu an sayılıyor,
      yani başarısız bir çözüm eğitim setine girebiliyor
- [ ] Korpus kapısına ekle
- [ ] Regresyon testi: bilerek yakınsamayan bir vaka `solved` olmamalı

---

## 4. NLGEOM (büyük deformasyon)

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
**daha küçük** deplasman (büyük deformasyonda yapı sertleşir), fark
%5–15. Fark yoksa kart uygulanmamış demektir.

---

## 5. Delikli plaka eğitimi

Kutu ve kalite seti girdisi **hazır** (`doe/quality_set.py`), koşulmadı.

**Sıra:** 0.1 doğrulaması → 200 koşu → korpus → eğitim.

```
H 150–300 · W 70–140 · T 4–12 · d 12–40 · yük 0.1–1.2 × 50 kN
malzeme: S235 + S355
```
Simülasyonla ölçüldü: kabul %80.8, Kt = 2.13–2.81, `sample_spec`
200/200 örnek üretiyor.

**Beklenen sonuç kirişten FARKLI:** üsteller teoriye tam oturmayacak,
çünkü σ = Kt(d/W)·F/((W−d)·T) saf kuvvet yasası değil — `log(W−d)` ne
W'nin ne d'nin kuvveti, `Kt` de oranın doğrusal olmayan fonksiyonu.

**Asıl bakılacak:** MAPE ve RF artık katmanının katkısı.
- yalnız log-log doğrusal: ~%5–10 beklenir (Kt'yi kaçırır)
- +RF artık: ~%2–3

Bu fark çıkarsa hibrit tasarım doğrulanır → kalan 10 şablona güvenle
geçilir. Çıkmazsa şablona özel özellik mühendisliği gerekir (ör. `d/W`
oranını doğrudan girdi yapmak).

---

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

## Öncelik sırası (öneri)

1. ~~**0.1** — yüzey yükü doğrulaması~~ ✅ kapandı
2. **3** — solver yakınsaması (yakınsamamış çözümler eğitime giriyor)
3. **5** — delikli plaka (yöntemin genelleşip genelleşmediği)
4. **2.1** — korpusa göre arşiv (temiz veri indirilemiyor)
5. **1** — GNN (en büyük iş, kontur tahmini için zorunlu)
6. **4** — NLGEOM arayüz + veri seti
7. **6, 7, 8** — iyileştirmeler

**Crash'e (Faz 1) geçmeden önce en az 0.1 (✅) ve 3 kapanmalı** — ikisi de
solver altyapısını ilgilendiriyor, crash aynı altyapıyı kullanacak.
