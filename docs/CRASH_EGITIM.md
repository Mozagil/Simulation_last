# Crash eğitim testleri — Malzeme + Sınır koşulları

> Arayüzde: Belgeler → son sayfa "Eğitim testleri (T1–T17)" (frontend/src/docs/crashTraining.ts). Biri değişince diğeri de güncellenir.

Amaç: 3 · Material ve 4 · Crash'teki **her** özelliği küçük, karşılaştırmalı
deneylerle anlamak; "bu ne işe yarar?" sorusuna kendi sonucunla cevap
verebilmek. Her test tek bir şeyi değiştirir, gerisi aynı kalır.

Ortak taban (aksi yazılmadıkça) — **Crash box tabanı**:
- Crash sekmesi → 1 · Geometry → Şablon "Crash box — kabuk (orta yüzey)" →
  Model üret → (pencerede) Modeli üret
- 2 · Mesh → 5 mm · 2D shell · quad → Mesh üret
- 3 · Material → 1 Kütüphane: S235 → 2 Parçalara ata: "S235 ata"
- 4 · Crash → 1 Çarpma: Rijit duvara · Hız 10 · Süre 3 · yön **+X** ·
  konum **-1, 25, 20** → 2 Parçalar: #0 Hareketli → "OpenRadioss çalıştır" ✓
  → .rad üret / çöz
- Sonuçları karşılaştırmak için: alttaki **Crash geçmişi** → koşuları işaretle
  → Karşılaştır.

Kayıt tablosu (her testte doldur): koşu # · değiştirdiğin · IE_final ·
KE_final · RWALL Fmax · impuls · HG/IE · silinen eleman · gözlem.

---

## Bölüm A — Malzeme (3 · Material)

### T1 · LAW1 elastik vs LAW2 plastik
- **Öğreneceğin:** malzeme modeli enerjinin yutulup yutulmadığını belirler.
- **Adım:** taban; 3 Davranış: LAW1 → koş. Sonra LAW2 → koş.
- **Bak:** IE_final, KE_final, impuls, animasyon.
- **Beklenen:** LAW1 → IE çok küçük, KE ≈ başlangıç, impuls ≈ 2·m·v (seker,
  ezilmez). LAW2 → IE büyür, kutu ön ucu katlanır.
- **Biri sorarsa:** "Elastik malzeme çarpıp geri seker, enerji yutmaz; crash'te
  ezilen metal için LAW2 (elasto-plastik) gerekir."

### T2 · Akma ve pekleşme (a, b, n)
- **Öğreneceğin:** σ = a + b·εₚⁿ — akma ve sertleşme kuvveti nasıl değiştirir.
- **Adım:** LAW2; (i) b = 0, n = 1 · (ii) b = 500 MPa, n = 0.5 · (iii) a = 400e6 Pa.
- **Bak:** RWALL Fmax, ortalama kuvvet (grafik), IE.
- **Beklenen:** b ve a büyüdükçe kuvvet artar, aynı sürede daha az ezilir.

### T3 · Hız etkisi (Johnson–Cook c, ε̇₀)
- **Öğreneceğin:** metal hızlı yüklemede sertleşir.
- **Adım:** LAW2, Hız 15 m/s; (i) c = 0 · (ii) c = 0.05, ε̇₀ = 1.
- **Beklenen:** c > 0 → tepe ve ortalama kuvvet yükselir.

### T4 · Sıcaklık etkisi
- **Öğreneceğin:** plastik iş ısıya döner, malzeme yumuşar.
- **Adım:** T3 (ii) + m = 1, T_melt = 1800 K, T_r = 293 K, ρCp = 3.8e6.
- **Beklenen:** kuvvet T3 (ii)'ye göre biraz düşer (etkisi küçük olabilir — veri).

### T5 · Kopma: basit (EPS_p_max) ve /FAIL
- **Öğreneceğin:** kopma kapalıyken hiçbir şey yırtılmaz.
- **Taban:** + Yeni crash vakası → **Plaka delinme (rijit küre)** → Senaryoyu koş
  (kopma kapalı). Sonra 3 · Material → Kopma / hasar → **Çekme gerinimi**:
  ε_t1 = 0.2, ε_f1 = 0.3 → 4 · Crash → çöz.
- **Bak:** "Silinen eleman", animasyonda delik.
- **Beklenen:** kopma açıkken eleman silinir, küre plakayı delebilir.
- **Ek:** aynı şeyi LAW2 → EPS_p_max = 0.3 ile dene (basit sınır).

### T6 · LAW36 tablo
- **Öğreneceğin:** ölçülmüş σ–ε eğrisiyle malzeme.
- **Adım:** taban; LAW36 → Eğri 1: `0 235` / `0.1 320` / `0.3 380` → çöz;
  T2 (i) ile karşılaştır.

### T7 · Parça başına malzeme modeli
- **Öğreneceğin:** çok parçalı modelde her parçaya ayrı kart.
- **Taban:** Plaka delinme senaryosu; 3 Davranış'ta parça #1 (küre) "ayrı" → LAW1;
  #0 (plaka) LAW2.
- **Beklenen:** küre deforme olmaz, plaka çöker.

---

## Bölüm B — Sınır koşulları (4 · Crash)

### T8 · Duvar yönü, konum, açı, Modelden seç
- **Öğreneceğin:** /RWALL tanımı ve viewport işaretleri.
- **Adım:** taban (LAW2); (i) yön +X, konum "⌖ Modelden seç" ile ön uca tıkla ·
  (ii) Açı 15° · (iii) bilerek yanlış yön (−X) → ne olur?
- **Beklenen:** (ii) eğik çarpma, kuvvet düşer, yanal deformasyon. (iii) parça
  duvardan uzaklaşır → kuvvet ≈ 0 (kurulum hatası nasıl görünür).

### T9 · Duvarsız mod ve parça rolleri
- **Öğreneceğin:** Hareketli / Sabit / Serbest; duvarsız çarpışma temasla olur.
- **Taban:** şablon "Crash box + çarpma plakası (iki parça)" (3D solid,
  10 mm mesh) → malzeme ata → Duvarsız · yön −X · kutu Hareketli, plaka Sabit.
- **Adım:** (i) temas YOK → çöz · (ii) Temas ekle TYPE7 kutu → plaka → çöz ·
  (iii) plaka Serbest yap → çöz.
- **Beklenen:** (i) kutu plakanın içinden geçer (temas yoksa çarpışma yok!) ·
  (ii) çarpışır · (iii) plaka itilip uzaklaşır.

### T10 · Öz temas ve TYPE7 / TYPE24
- **Öğreneceğin:** katlanan kabuğun katları birbirine girmesin.
- **Taban:** crash box + Kızak testi (40 kg, rayda), Süre 25 ms.
- **Adım:** (i) temas yok · (ii) TYPE7 #0↔#0 · (iii) TYPE24 #0↔#0.
- **Bak:** animasyon (katlar), ortalama kuvvet.
- **Beklenen:** (i) katlar iç içe geçer, kuvvet düşük · (ii)/(iii) gerçekçi katlanma.

### T11 · Kızak: rayda vs serbest (Ek tanımlar → Kütle / kızak)
- **Öğreneceğin:** rijit gövde + kütle; ray (DOF) neden gerekli.
- **Adım:** Kızak testi 50 kg, t (wall) 2 mm şablonla, 12 m/s, 30 ms: (i) Rayda ·
  (ii) Serbest.
- **Beklenen:** (ii) kutu ~120 mm sonra yana yatar, kuvvet çöker (DOE pilotunda
  yaşadığımız); (i) katlanarak ezilir, kızak durur.

### T12 · Bölgeyi kilitle (BCS) — tam ve kısmi
- **Öğreneceğin:** parçanın tamamı değil bir bölgesi; DOF seçimi.
- **Taban:** + Yeni vaka → **Patlama yüklü plaka** (kenarlar ankastre).
- **Adım:** (i) olduğu gibi · (ii) kenar kilidini kaldır (kart sil) → ne olur?
- **Beklenen:** (ii) plaka tümüyle uçar — kilit, yükün tepkisini taşır.

### T13 · Sabit hızla it (IMPVEL)
- **Öğreneceğin:** ilk hız ≠ sabit hız; parça yavaşlamaz.
- **Taban:** + Yeni vaka → **Kapı intrüzyonu** (silindir sabit hızla itilir).
- **Bak:** kuvvet–zaman (temas), kirişin eğilmesi.
- **Karşılaştır:** aynı silindire IMPVEL yerine ilk hız verilseydi silindir yavaşlardı.

### T14 · Parçaya ayrı ilk hız
- **Öğreneceğin:** farklı hızlarla gelen parçalar.
- **Taban:** T9 (ii) kurulumu; Ek tanımlar → Parçaya ayrı ilk hız: kutu 10 m/s
  (−X), plaka 5 m/s (+X); iki parça Serbest.
- **Beklenen:** kafa kafaya çarpışma; 1 · Çarpma hızı artık uygulanmaz.

### T15 · Yerçekimi
- **Taban:** + Yeni vaka → **Düşme testi** (H ile v = √(2gH)).
- **Adım:** yerçekimi açık / kapalı karşılaştır (kısa sürede fark küçük — veri).

---

## Bölüm C — Uzman ve çıktı

### T16 · Hourglass (Uzman ayarları)
- **Öğreneceğin:** HG/IE ne demek, nasıl düşer.
- **Adım:** T11 (i) koşusu; HG/IE'ye bak (≈ %7). Uzman → Ishell 24 → tekrar.
- **Beklenen:** HG/IE düşer; kuvvet biraz değişebilir.

### T17 · Çıktı ayarları (preprocess) + CFC (post-process)
- **Adım:** (i) TH aralığı 0.1 ms vs boş → tepe değişir mi? · (ii) S-kiriş
  senaryosunda kesit ekle → kesit kuvveti · (iii) sonuçta CFC 60 / 600 uygula.
- **Beklenen:** kaba TH tepeyi kaçırır; CFC tepeyi düşürür (ham korunur).

---

Bitince: ML tezgahı (ML Stüdyo → Crash) — DOE kurulumunda hangi alanı taradığını
bu testlerden bileceksin.
