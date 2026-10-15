# Crash eğitim testleri (T1–T30) — Malzeme + Sınır koşulları

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

### T21 · Geri sekme (springback): süre ve /DAMP _(Çıktı)_
- **Öğreneceğin:** Tepe |u| ile son |u| farkı elastik geri dönüştür; sönüm olmadan salınım son değeri bozar.
- **Değişen:** Süre 20 → 40 ms; sonra Çözüm kontrolü → Sönüm
- **Adımlar:** Süre 40 ms → çöz; 5 · Sonuçlar → “Geri sekme” kartı: tepe |u| (t), son |u|, fark, oran → Çözüm kontrolü → + Sönüm ekle → α 0, β 1e-5, parçalar: #0, başlangıç = tepe zamanı → çöz → |u|max–zaman eğrisini iki koşuda karşılaştır
- **Bak:** Tepe sonrası eğri sönüyor mu, salınıyor mu
- **Beklenen:** 20 ms'de kutu daha salınırken koşu biter, son |u| güvenilmez. 40 ms + sönümde eğri yatar; geri sekme = tepe − son, plastik kısım kalıcıdır.

### T24 · Kütüphane Johnson–Cook seti: 6061-T6 / DP600 vs elle _(Malzeme)_
- **Öğreneceğin:** crash_jc kütüphane seti kartı doldurur; σ–ε grafiği girilenle aynı şeyi gösterir.
- **Değişen:** 3 · Material → kütüphaneden JC'li malzeme; LAW2 kartında “Kütüphane Johnson–Cook seti”
- **Adımlar:** 3 · Material → kütüphane: 6061-T6 ata → 4 · Crash → Malzeme (LAW2) kartı → “Kütüphane Johnson–Cook seti” → Uygula → σ–ε grafiğine bak → çöz → a, b, n'i elle aynı değerlerle gir → çöz (aynı sonuç) → DP600 (çelik) ata → set uygula → çöz; Fmax'ı 6061 ile karşılaştır
- **Bak:** σ–ε grafiğinde akma ve pekleşme eğimi
- **Beklenen:** Set uygula ile elle giriş aynı deck'i üretir (Fmax birebir). DP600'de σy·A çok daha yüksek: tepe kuvvet ve IE artar, ezilme azalır. Kaynak satırı docs/CRASH_MATERIALS.md'de.

### T30 · Eleman formülasyonu (Ishell) ve hourglass _(Uzman)_
- **Öğreneceğin:** Kabuk formülasyonu tepe kuvvet ve HG enerjisini nasıl değiştirir.
- **Değişen:** Uzman ayarları → Ishell
- **Adımlar:** Uzman ayarları → Ishell 0 (varsayılan) → çöz → Ishell 24 (QEPH) → çöz → Ishell 12 (tam entegre) → çöz
- **Bak:** HG son / IE son ve koşu süresi
- **Beklenen:** QEPH ile HG enerjisi düşer, tepe kuvvet biraz değişir; tam entegre HG'yi sıfıra yaklaştırır ama koşu yavaşlar.

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

### T19 · Genel temas: TYPE24 çift vs Tüm model _(Sınır koşulu)_
- **Öğreneceğin:** Tek genel temas (≈ LS-DYNA AUTOMATIC_SINGLE_SURFACE) ne zaman yeter; kabuk + solid karışıkta üç arayüz.
- **Değişen:** T8'deki TYPE24 öz temas → kapsam Tüm model
- **Adımlar:** 3 · Temaslar → Temas 1 kapsam “Parça çifti”, TYPE24, #0 ↔ #0 (T8 kurulumu) → çöz → Aynı kartta kapsam “Tüm model” → parça seçicileri kaybolur → çöz → Deck'i görüntüle: /SURF/PART/7901 ve /INTER/TYPE24/1 (surf_ID2 = 0) kartlarını bul
- **Bak:** Katlanma bölgesinde kabuk kendi içinden geçiyor mu (animasyon ×5)
- **Beklenen:** Tek parçada ikisi aynı sonucu verir (kuvvet eğrisi üst üste). Çok parçalı modelde Tüm model her çifti elle tanımlamayı kaldırır; kabuk + solid karışıksa deck'te üç TYPE24 görünür.

### T20 · Ezilme mesafesi δ, F–δ ve ortalama ezilme kuvveti (C8b) _(Çıktı)_
- **Öğreneceğin:** Ezilme mesafesi hangi düğümden ölçülür; ∫F dδ / δ ile IE / δ neden farklı çıkar.
- **Değişen:** Çıktı ayarları → Ezilme referansı: kızak kartı
- **Adımlar:** 4 · Crash → Çıktı ayarları → Ezilme referansı: Kütle / kızak #1 → çöz → 5 · Sonuçlar → F–δ eğrisi ve “Ortalama ezilme kuvveti” kartı; δ_maks'ı not al → Referansı kaldır → çöz: ezilme kartı boş gelir (referanssız ölçüm yok)
- **Bak:** F–δ eğrisinin ilk tepesi ve plato seviyesi
- **Beklenen:** Ortalama ezilme kuvveti tepe kuvvetin çok altında kalır (katlanma platosu). ∫F dδ / δ duvar işi, IE / δ gövdenin yuttuğu enerji; ikisi KE kaybı ve sürtünme kadar ayrışır.

### T22 · Yay: kızak ↔ zemin, K ve C etkisi _(Sınır koşulu)_
- **Öğreneceğin:** /SPRING + /PROP/TYPE4 doğrusal yay; K kuvveti, C sönümü nasıl değiştirir; /TH/SPRING okuma.
- **Değişen:** Ek tanımlar → + Yay
- **Adımlar:** Ek tanımlar → + Yay → A ucu: Kütle / kızak #1 · B ucu: Nokta (−50, 25, 20) Sabit ✓ · K 500 N/mm · C 0 → çöz → K 5000 → çöz → K 500, C 20 → çöz → Deck'te /PROP/TYPE4 (K kN/mm = 0.5), /SPRING, /BCS/41 kartlarını bul; eğrilerde th_spring_1_FX
- **Bak:** Kızak hızı ve duvar kuvveti eğrisi
- **Beklenen:** Yay kızağı geri çeker: K büyüdükçe duvar kuvveti ve ezilme azalır, yay kuvveti artar. C salınımı söndürür. Yay ucu esnek parçaya değil rijit gövdeye bağlanır.

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

## Model 6 — Alüminyum kutu (can) ezme: açılı C-kesit çarpıcı + sabit blok

**Modeli kur (bir kez):**
1. + Yeni crash vakası → senaryo “Alüminyum kutu (can) ezme — açılı C-kesit çarpıcı” (şablon can_crush_shell, varsayılan parametreler)
2. 3 · Material → kütüphane 6061-T6 (kutu), çarpıcı ve blok çelik; 4 · Crash → Parçalar: çarpıcı Hareketli + Rijit gövde ✓, blok Sabit, kutu Serbest; Temaslar: Tüm model

### T23 · Can crush: açılı C-kesit çarpıcı + sabit blok _(Sınır koşulu)_
- **Öğreneceğin:** Rijit çarpıcı + ilk hız, genel temas, kabuk silindirin katlanması (Ansys Explicit örneği).
- **Değişen:** Senaryo: Alüminyum kutu (can) ezme
- **Adımlar:** + Yeni crash vakası → senaryo “Alüminyum kutu (can) ezme” → Senaryoyu koş → Parçalar: çarpıcı Rijit gövde ✓ (hareketli), blok Sabit, kutu Serbest; Temaslar: Tüm model → çöz → Çarpıcı açısını değiştir (şablon parametresi) → çöz
- **Bak:** Von Mises ve plastik gerinim konturu, katlanma yeri
- **Beklenen:** Kutu önce çarpıcının altında çöker, sonra yana yatarak katlanır; açı büyüdükçe asimetri artar. Genel temas olmadan cidar kendi içinden geçer.

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

### T25 · Karşılaştırma + enerji dengesi okuma _(Çıktı)_
- **Öğreneceğin:** IE / KE / HG / toplam enerji eğrilerini birlikte okumak; enerji dengesi ne zaman kötü.
- **Değişen:** Üç koşuyu Karşılaştır; eğri grubu Enerji
- **Adımlar:** Crash geçmişi → T1b, T2 (a 400), T10 (hourglass) koşularını işaretle → Karşılaştır → Eğri: Enerji → Toplam enerji, İç enerji, Kinetik enerji, Hourglass sırayla → Skaler tabloda “Enerji dengesi” ve “HG son / IE son” satırları
- **Bak:** Toplam enerji düz mü, HG/IE yüzde kaç
- **Beklenen:** Toplam enerji yatay kalmalı; düşüyorsa temas/sönüm kaybı, yükseliyorsa hourglass. HG/IE > %10 koşuyu şüpheli yapar (T10'daki ayarla düşer).

### T26 · Mini DOE + vekil tahmin _(Çıktı)_
- **Öğreneceğin:** 20 koşuluk DOE'nin vekil modele yetmediğini görmek; aralık dışı (OOD) uyarısı.
- **Değişen:** ML tezgahı → crash → DOE
- **Adımlar:** ML tezgahı → Crash → DOE: şablon crash_box, parametreler Wall t 2–4 mm, Hız 8–15 m/s, 20 nokta (LHS) → DOE başlat (Codespaces'te bekle) → Eğit · 5-fold CV → hedef başına R² / MAE'ye bak → Tahmin et: t 3, v 10 (aralık içi) ve t 6 (aralık dışı)
- **Bak:** R² değerleri ve OOD uyarısı
- **Beklenen:** 20 noktayla R² düşük ve kararsızdır (ezber). Aralık dışı girdi uyarı alır; tahmin güvenilmez. 200 nokta bu yüzden gerekli.

### T27 · Kuş / yumuşak cisim çarpması (SPH) _(Sınır koşulu)_
- **Öğreneceğin:** SPH parçacık projesi; parçacık aralığı ve kütle tutarlılığı.
- **Değişen:** Senaryo: Kuş / yumuşak cisim çarpması
- **Adımlar:** Senaryoyu koş → SPH kartında parçacık aralığını yarıya indir → çöz → Deck'te /SPHCEL ve /INTER/TYPE7 (SPH ↔ plaka) kartlarına bak
- **Bak:** Plaka tepe kuvveti ve SPH toplam kütle (deck özeti)
- **Beklenen:** Parçacık aralığı küçüldükçe kuvvet eğrisi yumuşar, koşu süresi büyür; toplam kütle ve ilk KE aynı kalmalı.

### T28 · Direk (pole) yan çarpması _(Sınır koşulu)_
- **Öğreneceğin:** Uç kütleli kirişin direğe çarpması; temas tipi ve uç kütle etkisi.
- **Değişen:** Senaryo: Direk yan çarpması; uç kütleleri
- **Adımlar:** Senaryoyu koş → Ek tanımlar → uç kütle kartlarından birini sil → çöz → Direk yarıçapını şablonda değiştir → çöz
- **Bak:** Kirişin orta sehimi ve temas kuvveti
- **Beklenen:** Uç kütle kalkınca kiriş daha az eğilir, kuvvet daha erken düşer. İnce direk daha derin intrüzyon, daha düşük tepe.

### T29 · LS-DYNA .k içe aktarma _(Çıktı)_
- **Öğreneceğin:** Hangi kartlar çevrilir, hangileri atlanır; içe aktarılan kurulum neden elle kontrol edilmeli.
- **Değişen:** Crash geçmişi → LS-DYNA içe aktar
- **Adımlar:** Basit bir .k (tek parça, *MAT_PLASTIC_KINEMATIC, *RIGIDWALL_PLANAR, *INITIAL_VELOCITY) hazırla → LS-DYNA içe aktar → Çevrilen kartlar / atlananlar listesini oku; 4 · Crash'te malzeme ve duvar kartlarını kontrol et → çöz → Aynı modeli elle kurup Fmax'ı karşılaştır
- **Bak:** Atlanan kart listesi
- **Beklenen:** Çevrilen kartlar bire bir eşleşir (Fmax aynı); *CONTACT_AUTOMATIC_SINGLE_SURFACE → Tüm model, desteklenmeyen kartlar listede uyarıyla kalır.
