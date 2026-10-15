# Crash eğitim testleri (T1–T18) — Malzeme + Sınır koşulları

> Arayüzde: Belgeler → son sayfa "Eğitim testleri" (frontend/src/docs/crashTraining.ts — bu dosya ondan üretildi).

Modele göre sıralı: her model grubun başında bir kez kurulur; ardından gelen her test bir öncekinden yalnız **tek şeyi** değiştirir.

Her testte not al: koşu # · değiştirdiğin · IE_final · KE_final · RWALL Fmax · impuls · HG/IE · silinen eleman · gözlem. Karşılaştırma: alttaki Crash geçmişi → koşuları işaretle → Karşılaştır.

---

## Model 1 — Crash box (3 mm) + 100 kg kızak, rijit duvara 10 m/s

**Modeli kur (bir kez):**
1. Crash sekmesi → 1 · Geometry → şablon “Crash box — kabuk (orta yüzey)” → parametreler (varsayılan): Box Length L 300 · Box Height h 50 · Box Width b 40 · Wall t 3 (mm) → Model üret → (pencerede) Modeli üret
2. 2 · Mesh → 5 mm · 2D shell · quad → Mesh üret
3. 3 · Material → 1 Kütüphane: S235 → 2 Parçalara ata: “S235 ata”
4. 4 · Crash → Çarpma: Rijit duvara · Hız 10 · Süre 20 · yön +X · konum -1, 25, 20 → Parçalar: #0 Hareketli
5. 4 · Crash → Ek tanımlar → + Kütle / kızak → bölge kutu_arka · kütle 100 kg · hareket Serbest → “OpenRadioss çalıştır” ✓

> Neden kızak + 20 ms: kutu tek başına ~1.2 kg (10 m/s'de ~59 J) — ~1 mm ezilip durur, katlanma görünmez. 100 kg arka kütle ~5 kJ getirir; 20 ms'de kutu katlanarak ezilir (1.25e).

### T1 · LAW1 elastik vs LAW2 plastik _(Malzeme)_
- **Öğreneceğin:** Malzeme modeli enerjinin yutulup yutulmadığını belirler.
- **Değişen:** 3 Davranış: önce LAW1, sonra LAW2
- **Adımlar:** LAW1 → çöz → LAW2 → çöz → İki koşuyu karşılaştır
- **Bak:** IE_final, KE_final, impuls, animasyon
- **Beklenen:** LAW1 → IE çok küçük, KE ≈ başlangıç, impuls ≈ 2·m·v (seker). LAW2 → IE büyür, ön uç katlanır.
- **Ölçülen:** #361 LAW1: IE 102 J, KE_son 5038 J (başlangıç ≈ 5060 J), impuls 2017 N·s ≈ 2·m·v, Fmax 1756 kN (HG/IE %33). #362 LAW2: IE 4320 J, KE_son 386 J, impuls 755 N·s, Fmax 119.6 kN, HG/IE %8.2.
- **Biri sorarsa:** "Elastik malzeme çarpıp geri seker, enerji yutmaz; ezilen metal için LAW2 gerekir."

### T2 · Akma ve pekleşme (a, b, n) _(Malzeme)_
- **Öğreneceğin:** σ = a + b·εₚⁿ — akma ve sertleşme kuvveti nasıl değiştirir.
- **Değişen:** LAW2'de yalnız Akma ve pekleşme alanları
- **Adımlar:** b = 0, n = 1 → çöz → b = 500 MPa, n = 0.5 → çöz → a = 400e6 Pa → çöz
- **Bak:** RWALL Fmax, ortalama kuvvet (grafik), IE
- **Beklenen:** b ve a büyüdükçe kuvvet artar, aynı sürede daha az ezilir.
- **Ölçülen:** b = 0, n = 1 varsayılan → T1b ile aynı koşu (#363 = #362: Fmax 119.6 kN, IE 4320 J, KE_son 386 J). #364 b = 500, n = 0.5: Fmax 155.5 kN, IE 4722 J, KE_son 32 J (kızak durdu). #365 a = 400 MPa: Fmax 201.7 kN, IE 4634 J, KE_son 28 J.

### T3 · Hız etkisi (Johnson–Cook c, ε̇₀) _(Malzeme)_
- **Öğreneceğin:** Metal hızlı yüklemede sertleşir.
- **Değişen:** a, b, n'yi varsayılana döndür; Hız 15 m/s; Hız etkisi alanları
- **Adımlar:** c = 0 → çöz → c = 0.05, ε̇₀ = 1 → çöz
- **Beklenen:** c > 0 → tepe ve ortalama kuvvet yükselir.
- **Ölçülen:** 15 m/s ≈ 11.4 kJ; 20 ms içinde kızak durmuyor. #366 c = 0: Fmax 121.3 kN, IE 6685 J, KE_son 4073 J. #367 c = 0.05: Fmax 152.6 kN, IE 7845 J, KE_son 2928 J.

### T4 · Sıcaklık etkisi _(Malzeme)_
- **Öğreneceğin:** Plastik iş ısıya döner, malzeme yumuşar.
- **Değişen:** T3'ün c = 0.05 koşusuna Sıcaklık alanlarını ekle
- **Adımlar:** m = 1, T_melt = 1800 K, T_r = 293 K, ρCp = 3.8e6 → çöz
- **Beklenen:** Kuvvet T3'e göre biraz düşer (etkisi küçük olabilir — veri).
- **Ölçülen:** #368: Fmax 152.5 kN, IE 7942 J, KE_son 2824 J — T3b (#367) ile fark < %1.5; bu koşuda sıcaklık etkisi görünmüyor.

### T5 · LAW36 tablo _(Malzeme)_
- **Öğreneceğin:** Ölçülmüş σ–ε eğrisiyle malzeme.
- **Değişen:** Hız 10'a dön; LAW2 yerine LAW36
- **Adımlar:** Eğri 1: 0 235 / 0.1 320 / 0.3 380 → çöz → T2'nin b = 0 koşusuyla karşılaştır
- **Beklenen:** Eğri sertleştikçe kuvvet artar; benzer eğride LAW2 ile benzer sonuç.
- **Ölçülen:** #369 LAW36: Fmax 126.5 kN, IE 4573 J, KE_son 154 J, impuls 851 N·s — T2a (#363, b = 0): Fmax 119.6 kN, IE 4320 J, KE_son 386 J.

### T6 · Duvar yönü, konum, açı, Modelden seç _(Sınır koşulu)_
- **Öğreneceğin:** /RWALL tanımı ve viewport işaretleri.
- **Değişen:** LAW2'ye dön; yalnız 1 Çarpma alanları
- **Adımlar:** Konumu “⌖ Modelden seç” ile ön uca tıklayarak ver → çöz → Açı 15° → çöz → Açı 0, bilerek yanlış yön (−X) → çöz
- **Beklenen:** 15°: eğik çarpma, kuvvet düşer. Yanlış yön: parça duvardan uzaklaşır → kuvvet ≈ 0 (kurulum hatası böyle görünür).

### T7 · Çıktı ayarları (preprocess) + CFC (post-process) _(Çıktı)_
- **Öğreneceğin:** Neyin kaydedildiği ile nasıl süzüldüğü farklı şeyler.
- **Değişen:** Yön +X'e dön; Çıktı ayarları ve sonuçta CFC
- **Adımlar:** 4 · Crash → Çıktı ayarları: TH aralığı 0.1 ms → çöz; boş → çöz → 5 · Sonuçlar → CFC 60 → Uygula; sonra CFC 600
- **Beklenen:** Kaba TH (0.1 ms) tepeyi kaçırır; CFC tepeyi düşürür, ham eğri korunur.

---

## Model 2 — Crash box (2 mm) + raylı kızak, uzun ezilme

**Modeli kur (bir kez):**
1. 1 · Geometry → şablon “Crash box — kabuk (orta yüzey)” → parametreler: Box Length L 300 · Box Height h 50 · Box Width b 40 · Wall t 2 (yalnız t değişti; mm) → Model üret → Modeli üret
2. 2 · Mesh → 5 mm · 2D shell · quad → Mesh üret; 3 · Material → S235 ata, LAW2
3. 4 · Crash → Çarpma: Rijit duvara · Hız 12 · Süre 30 · yön +X · konum -1, 25, 20; #0 Hareketli
4. 4 Ek tanımlar → Hazır kurulum “Kızak testi” → Ek kütle 50 kg (hareket: Rayda)

### T8 · Öz temas: yok / TYPE7 / TYPE24 _(Sınır koşulu)_
- **Öğreneceğin:** Katlanan kabuğun katları birbirine girmesin.
- **Değişen:** Yalnız 3 Temaslar
- **Adımlar:** Temas yok → çöz → TYPE7 #0↔#0 → çöz → TYPE24 #0↔#0 → çöz
- **Bak:** Animasyon (katlar), ortalama kuvvet
- **Beklenen:** Temas yok → katlar iç içe geçer, kuvvet düşük; öz temasla gerçekçi katlanma.

### T9 · Kızak: rayda vs serbest _(Sınır koşulu)_
- **Öğreneceğin:** Rijit gövde + kütle; ray (DOF) neden gerekli.
- **Değişen:** TYPE7 öz temas kalsın; yalnız kızak kartında Hareket
- **Adımlar:** Hareket: Rayda → çöz → Hareket: Serbest → çöz
- **Beklenen:** Serbest: ~120 mm sonra kutu yana yatar, kuvvet çöker (DOE pilotunda yaşandı). Rayda: katlanarak ezilir, kızak durur.

### T10 · Hourglass (Uzman ayarları) _(Uzman)_
- **Öğreneceğin:** HG/IE ne demek, nasıl düşer.
- **Değişen:** Rayda'ya dön; yalnız Uzman ayarları
- **Adımlar:** Rayda koşusunda HG/IE'ye bak (≈ %7) → Uzman → Ishell 24 → çöz
- **Beklenen:** HG/IE düşer; kuvvet biraz değişebilir.

---

## Model 3 — İki parça: kutu + çarpma plakası (3D solid)

**Modeli kur (bir kez):**
1. 1 · Geometry → şablon “Crash box + çarpma plakası (iki parça)” → parametreler (varsayılan): Box Length L 200 · Box Height h 50 · Box Width b 40 · Wall t 2 · Plate Thickness tp 10 · Plate Margin m 20 · Gap g 1 (mm) → Model üret → Modeli üret
2. 2 · Mesh → 10 mm · 3D solid → Mesh üret; 3 · Material → Tüm parçalara S235 ata, LAW2
3. 4 · Crash → Çarpma: Duvarsız · yalnız ilk hız · Hız 10 · yön −X · Süre 3

### T11 · Duvarsız mod, roller ve temas _(Sınır koşulu)_
- **Öğreneceğin:** Hareketli / Sabit / Serbest; duvarsız çarpışma ancak temasla olur.
- **Değişen:** Parçalar rolleri ve 3 Temaslar
- **Adımlar:** Kutu Hareketli, plaka Sabit, temas YOK → çöz → Temas ekle TYPE7 kutu → plaka → çöz → Plaka Serbest → çöz
- **Beklenen:** Temas yokken kutu plakanın içinden geçer; temasla çarpışır; serbest plaka itilip uzaklaşır.
- **Biri sorarsa:** "Duvarsız modda iki parça ancak temas tanımlıysa çarpışır."

### T12 · Parçaya ayrı ilk hız _(Sınır koşulu)_
- **Öğreneceğin:** Farklı hızlarla gelen parçalar.
- **Değişen:** Temas kalsın, iki parça Serbest; Ek tanımlar → Parçaya ayrı ilk hız
- **Adımlar:** Kutu 10 m/s (yön −1, 0, 0), plaka 5 m/s (yön 1, 0, 0) → çöz
- **Beklenen:** Kafa kafaya çarpışma; 1 · Çarpma hızı artık uygulanmaz.

---

## Model 4 — Plaka delinme (hazır senaryo)

**Modeli kur (bir kez):**
1. + Yeni crash vakası → “Plaka delinme / darbe (rijit küre)” → Senaryoyu koş (geometri, mesh, kurulum otomatik)

### T13 · Kopma: basit (EPS_p_max) ve /FAIL _(Malzeme)_
- **Öğreneceğin:** Kopma kapalıyken hiçbir şey yırtılmaz.
- **Değişen:** Yalnız 3 Davranış ve kopma
- **Adımlar:** İlk koşu: kopma kapalı (senaryonun kendisi) → Kopma / hasar → Çekme gerinimi: ε_t1 = 0.2, ε_f1 = 0.3 → 4 · Crash → çöz → Çekme gerinimini kapat; LAW2 → EPS_p_max = 0.3 → çöz
- **Bak:** Silinen eleman, animasyonda delik
- **Beklenen:** Kopma açıkken eleman silinir, küre plakayı delebilir.

### T14 · Parça başına malzeme modeli _(Malzeme)_
- **Öğreneceğin:** Çok parçalı modelde her parçaya ayrı kart.
- **Değişen:** Kopma kapalı; parça #1 (küre) için ayrı kart
- **Adımlar:** #1 “ayrı” → LAW1; #0 (plaka) LAW2 → çöz
- **Beklenen:** Küre deforme olmaz, plaka çöker.

---

## Model 5+ — Diğer hazır senaryolar (her test kendi modeliyle)

**Modeli kur (bir kez):**
1. Her test: + Yeni crash vakası → ilgili senaryo → Senaryoyu koş

### T15 · Bölgeyi kilitle (patlama yüklü plaka) _(Sınır koşulu)_
- **Öğreneceğin:** Parçanın tamamı değil bir bölgesi kilitlenir.
- **Değişen:** Senaryo: Patlama yüklü plaka; sonra kenar kilidini kaldır
- **Adımlar:** Olduğu gibi → çöz → Ek tanımlar'daki kenar kilidi kartını sil → çöz
- **Beklenen:** Kilit yokken plaka tümüyle uçar — kilit yükün tepkisini taşır.

### T16 · Sabit hızla it (kapı intrüzyonu) _(Sınır koşulu)_
- **Öğreneceğin:** İlk hız ≠ sabit hız; parça yavaşlamaz.
- **Değişen:** Senaryo: Kapı intrüzyonu
- **Adımlar:** Senaryoyu koş
- **Bak:** Temas kuvveti–zaman, kirişin eğilmesi
- **Beklenen:** Silindir hızı sabit kalır, kiriş giderek eğilir; ilk hız verilseydi silindir yavaşlardı.

### T17 · Yerçekimi (düşme testi) _(Sınır koşulu)_
- **Öğreneceğin:** Sabit ivme; düşme testleri.
- **Değişen:** Senaryo: Düşme testi; sonra yerçekimini kapat
- **Adımlar:** Yerçekimi açık → çöz → Kapalı → çöz
- **Beklenen:** Kısa sürede fark küçük — veri.

### T18 · Kesit kuvveti (S-kiriş) _(Çıktı)_
- **Öğreneceğin:** Modelin içinden geçen düzlemde iç kuvvet.
- **Değişen:** Senaryo: S-kiriş; Çıktı ayarları → + Kesit ekle
- **Adımlar:** Kirişin ortasından geçen M, M1, M2 ver → çöz → Sonuçta kesit kuvveti eğrisine bak
- **Beklenen:** Kesit kuvveti duvar kuvvetinden farklıdır — iç yükü gösterir.
