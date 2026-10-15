/**
 * Crash eğitim testleri (T1–T30) — Belgeler'in son sayfası (kullanıcı
 * 2026-10-08). Modele göre sıralı: her model bir kez kurulur, ardından gelen
 * testler bir öncekinden yalnız TEK şeyi değiştirir. Kaynak metin
 * docs/CRASH_EGITIM.md ile aynı; biri değişince diğeri de güncellenir.
 */

export interface TrainingTest {
  id: string;
  title: string;
  /** Ders alanı: Malzeme / Sınır koşulu / Uzman / Çıktı */
  area: string;
  learn: string;
  /** Bir önceki teste göre değişen tek şey. */
  change: string;
  steps: string[];
  observe?: string;
  expect: string;
  /** Gerçek koşu değerleri (koşu no ile); veri, kabul eşiği değil. */
  measured?: string;
  answer?: string;
}

export interface TrainingGroup {
  title: string;
  /** Modeli kurma adımları (grup başında bir kez). */
  setup: string[];
  /** Kurulumun gerekçesi / ölçülen taban değerler (adım değil). */
  note?: string;
  tests: TrainingTest[];
}

export const TRAINING_RECORD =
  "Her testte not al: koşu # · değiştirdiğin · IE_final · KE_final · RWALL Fmax · impuls · HG/IE · silinen eleman · gözlem. Karşılaştırma: alttaki Crash geçmişi → koşuları işaretle → Karşılaştır.";

export const CRASH_TRAINING: TrainingGroup[] = [
  {
    title: "Model 1 — Crash box (3 mm) + 100 kg kızak, rijit duvara 10 m/s",
    setup: [
      "Crash sekmesi → 1 · Geometry → şablon “Crash box — kabuk (orta yüzey)” → parametreler (varsayılan): Box Length L 300 · Box Height h 50 · Box Width b 40 · Wall t 3 (mm) → Model üret → (pencerede) Modeli üret",
      "2 · Mesh → 5 mm · 2D shell · quad → Mesh üret",
      "3 · Material → 1 Kütüphane: S235 → 2 Parçalara ata: “S235 ata”",
      "4 · Crash → Çarpma: Rijit duvara · Hız 10 · Süre 20 · yön +X · konum -1, 25, 20 → Parçalar: #0 Hareketli",
      "4 · Crash → Ek tanımlar → + Kütle / kızak → bölge kutu_arka · kütle 100 kg · hareket Serbest → “OpenRadioss çalıştır” ✓",
    ],
    note: "Neden kızak + 20 ms: kutu tek başına ~1.2 kg (10 m/s'de ~59 J) — ~1 mm ezilip durur, katlanma görünmez. 100 kg arka kütle ~5 kJ getirir; 20 ms'de kutu katlanarak ezilir (1.25e).",
    tests: [
      {
        id: "T1",
        title: "LAW1 elastik vs LAW2 plastik",
        area: "Malzeme",
        learn: "Malzeme modeli enerjinin yutulup yutulmadığını belirler.",
        change: "3 Davranış: önce LAW1, sonra LAW2",
        steps: ["LAW1 → çöz", "LAW2 → çöz", "İki koşuyu karşılaştır"],
        observe: "IE_final, KE_final, impuls, animasyon",
        expect: "LAW1 → IE çok küçük, KE ≈ başlangıç, impuls ≈ 2·m·v (seker). LAW2 → IE büyür, ön uç katlanır.",
        measured: "#361 LAW1: IE 102 J, KE_son 5038 J (başlangıç ≈ 5060 J), impuls 2017 N·s ≈ 2·m·v, Fmax 1756 kN (HG/IE %33). #362 LAW2: IE 4320 J, KE_son 386 J, impuls 755 N·s, Fmax 119.6 kN, HG/IE %8.2.",
        answer: "Elastik malzeme çarpıp geri seker, enerji yutmaz; ezilen metal için LAW2 gerekir.",
      },
      {
        id: "T2",
        title: "Akma ve pekleşme (a, b, n)",
        area: "Malzeme",
        learn: "σ = a + b·εₚⁿ — akma ve sertleşme kuvveti nasıl değiştirir.",
        change: "LAW2'de yalnız Akma ve pekleşme alanları",
        steps: ["b = 0, n = 1 → çöz", "b = 500 MPa, n = 0.5 → çöz", "a = 400e6 Pa → çöz"],
        observe: "RWALL Fmax, ortalama kuvvet (grafik), IE",
        expect: "b ve a büyüdükçe kuvvet artar, aynı sürede daha az ezilir.",
        measured: "b = 0, n = 1 varsayılan → T1b ile aynı koşu (#363 = #362: Fmax 119.6 kN, IE 4320 J, KE_son 386 J). #364 b = 500, n = 0.5: Fmax 155.5 kN, IE 4722 J, KE_son 32 J (kızak durdu). #365 a = 400 MPa: Fmax 201.7 kN, IE 4634 J, KE_son 28 J.",
      },
      {
        id: "T3",
        title: "Hız etkisi (Johnson–Cook c, ε̇₀)",
        area: "Malzeme",
        learn: "Metal hızlı yüklemede sertleşir.",
        change: "a, b, n'yi varsayılana döndür; Hız 15 m/s; Hız etkisi alanları",
        steps: ["c = 0 → çöz", "c = 0.05, ε̇₀ = 1 → çöz"],
        expect: "c > 0 → tepe ve ortalama kuvvet yükselir.",
        measured: "15 m/s ≈ 11.4 kJ; 20 ms içinde kızak durmuyor. #366 c = 0: Fmax 121.3 kN, IE 6685 J, KE_son 4073 J. #367 c = 0.05: Fmax 152.6 kN, IE 7845 J, KE_son 2928 J.",
      },
      {
        id: "T4",
        title: "Sıcaklık etkisi",
        area: "Malzeme",
        learn: "Plastik iş ısıya döner, malzeme yumuşar.",
        change: "T3'ün c = 0.05 koşusuna Sıcaklık alanlarını ekle",
        steps: ["m = 1, T_melt = 1800 K, T_r = 293 K, ρCp = 3.8e6 → çöz"],
        expect: "Kuvvet T3'e göre biraz düşer (etkisi küçük olabilir — veri).",
        measured: "#368: Fmax 152.5 kN, IE 7942 J, KE_son 2824 J — T3b (#367) ile fark < %1.5; bu koşuda sıcaklık etkisi görünmüyor.",
      },
      {
        id: "T5",
        title: "LAW36 tablo",
        area: "Malzeme",
        learn: "Ölçülmüş σ–ε eğrisiyle malzeme.",
        change: "Hız 10'a dön; LAW2 yerine LAW36",
        steps: ["Eğri 1: 0 235 / 0.1 320 / 0.3 380 → çöz", "T2'nin b = 0 koşusuyla karşılaştır"],
        expect: "Eğri sertleştikçe kuvvet artar; benzer eğride LAW2 ile benzer sonuç.",
        measured: "#369 LAW36: Fmax 126.5 kN, IE 4573 J, KE_son 154 J, impuls 851 N·s — T2a (#363, b = 0): Fmax 119.6 kN, IE 4320 J, KE_son 386 J.",
      },
      {
        id: "T6",
        title: "Duvar yönü, konum, açı, Modelden seç",
        area: "Sınır koşulu",
        learn: "/RWALL tanımı ve viewport işaretleri.",
        change: "LAW2'ye dön; yalnız 1 Çarpma alanları",
        steps: ["Konumu “⌖ Modelden seç” ile ön uca tıklayarak ver → çöz", "Açı 15° → çöz", "Açı 0, bilerek yanlış yön (−X) → çöz"],
        expect: "15°: eğik çarpma, kuvvet düşer. Yanlış yön: parça duvardan uzaklaşır → kuvvet ≈ 0 (kurulum hatası böyle görünür).",
      },
      {
        id: "T7",
        title: "Çıktı ayarları (preprocess) + CFC (post-process)",
        area: "Çıktı",
        learn: "Neyin kaydedildiği ile nasıl süzüldüğü farklı şeyler.",
        change: "Yön +X'e dön; Çıktı ayarları ve sonuçta CFC",
        steps: ["4 · Crash → Çıktı ayarları: TH aralığı 0.1 ms → çöz; boş → çöz", "5 · Sonuçlar → CFC 60 → Uygula; sonra CFC 600"],
        expect: "Kaba TH (0.1 ms) tepeyi kaçırır; CFC tepeyi düşürür, ham eğri korunur.",
      },
      {
        id: "T21",
        title: "Geri sekme (springback): süre ve /DAMP",
        area: "Çıktı",
        learn: "Tepe |u| ile son |u| farkı elastik geri dönüştür; sönüm olmadan salınım son değeri bozar.",
        change: "Süre 20 → 40 ms; sonra Çözüm kontrolü → Sönüm",
        steps: ["Süre 40 ms → çöz; 5 · Sonuçlar → “Geri sekme” kartı: tepe |u| (t), son |u|, fark, oran", "Çözüm kontrolü → + Sönüm ekle → α 0, β 1e-5, parçalar: #0, başlangıç = tepe zamanı → çöz", "|u|max–zaman eğrisini iki koşuda karşılaştır"],
        observe: "Tepe sonrası eğri sönüyor mu, salınıyor mu",
        expect: "20 ms'de kutu daha salınırken koşu biter, son |u| güvenilmez. 40 ms + sönümde eğri yatar; geri sekme = tepe − son, plastik kısım kalıcıdır.",
      },
      {
        id: "T24",
        title: "Kütüphane Johnson–Cook seti: 6061-T6 / DP600 vs elle",
        area: "Malzeme",
        learn: "crash_jc kütüphane seti kartı doldurur; σ–ε grafiği girilenle aynı şeyi gösterir.",
        change: "3 · Material → kütüphaneden JC'li malzeme; LAW2 kartında “Kütüphane Johnson–Cook seti”",
        steps: ["3 · Material → kütüphane: 6061-T6 ata → 4 · Crash → Malzeme (LAW2) kartı → “Kütüphane Johnson–Cook seti” → Uygula → σ–ε grafiğine bak → çöz", "a, b, n'i elle aynı değerlerle gir → çöz (aynı sonuç)", "DP600 (çelik) ata → set uygula → çöz; Fmax'ı 6061 ile karşılaştır"],
        observe: "σ–ε grafiğinde akma ve pekleşme eğimi",
        expect: "Set uygula ile elle giriş aynı deck'i üretir (Fmax birebir). DP600'de σy·A çok daha yüksek: tepe kuvvet ve IE artar, ezilme azalır. Kaynak satırı docs/CRASH_MATERIALS.md'de.",
      },
      {
        id: "T30",
        title: "Eleman formülasyonu (Ishell) ve hourglass",
        area: "Uzman",
        learn: "Kabuk formülasyonu tepe kuvvet ve HG enerjisini nasıl değiştirir.",
        change: "Uzman ayarları → Ishell",
        steps: ["Uzman ayarları → Ishell 0 (varsayılan) → çöz", "Ishell 24 (QEPH) → çöz", "Ishell 12 (tam entegre) → çöz"],
        observe: "HG son / IE son ve koşu süresi",
        expect: "QEPH ile HG enerjisi düşer, tepe kuvvet biraz değişir; tam entegre HG'yi sıfıra yaklaştırır ama koşu yavaşlar.",
      },
    ],
  },
  {
    title: "Model 2 — Crash box (2 mm) + raylı kızak, uzun ezilme",
    setup: [
      "1 · Geometry → şablon “Crash box — kabuk (orta yüzey)” → parametreler: Box Length L 300 · Box Height h 50 · Box Width b 40 · Wall t 2 (yalnız t değişti; mm) → Model üret → Modeli üret",
      "2 · Mesh → 5 mm · 2D shell · quad → Mesh üret; 3 · Material → S235 ata, LAW2",
      "4 · Crash → Çarpma: Rijit duvara · Hız 12 · Süre 30 · yön +X · konum -1, 25, 20; #0 Hareketli",
      "4 Ek tanımlar → Hazır kurulum “Kızak testi” → Ek kütle 50 kg (hareket: Rayda)",
    ],
    tests: [
      {
        id: "T8",
        title: "Öz temas: yok / TYPE7 / TYPE24",
        area: "Sınır koşulu",
        learn: "Katlanan kabuğun katları birbirine girmesin.",
        change: "Yalnız 3 Temaslar",
        steps: ["Temas yok → çöz", "TYPE7 #0↔#0 → çöz", "TYPE24 #0↔#0 → çöz"],
        observe: "Animasyon (katlar), ortalama kuvvet",
        expect: "Temas yok → katlar iç içe geçer, kuvvet düşük; öz temasla gerçekçi katlanma.",
      },
      {
        id: "T9",
        title: "Kızak: rayda vs serbest",
        area: "Sınır koşulu",
        learn: "Rijit gövde + kütle; ray (DOF) neden gerekli.",
        change: "TYPE7 öz temas kalsın; yalnız kızak kartında Hareket",
        steps: ["Hareket: Rayda → çöz", "Hareket: Serbest → çöz"],
        expect: "Serbest: ~120 mm sonra kutu yana yatar, kuvvet çöker (DOE pilotunda yaşandı). Rayda: katlanarak ezilir, kızak durur.",
      },
      {
        id: "T10",
        title: "Hourglass (Uzman ayarları)",
        area: "Uzman",
        learn: "HG/IE ne demek, nasıl düşer.",
        change: "Rayda'ya dön; yalnız Uzman ayarları",
        steps: ["Rayda koşusunda HG/IE'ye bak (≈ %7)", "Uzman → Ishell 24 → çöz"],
        expect: "HG/IE düşer; kuvvet biraz değişebilir.",
      },
      {
        id: "T19",
        title: "Genel temas: TYPE24 çift vs Tüm model",
        area: "Sınır koşulu",
        learn: "Tek genel temas (≈ LS-DYNA AUTOMATIC_SINGLE_SURFACE) ne zaman yeter; kabuk + solid karışıkta üç arayüz.",
        change: "T8'deki TYPE24 öz temas → kapsam Tüm model",
        steps: ["3 · Temaslar → Temas 1 kapsam “Parça çifti”, TYPE24, #0 ↔ #0 (T8 kurulumu) → çöz", "Aynı kartta kapsam “Tüm model” → parça seçicileri kaybolur → çöz", "Deck'i görüntüle: /SURF/PART/7901 ve /INTER/TYPE24/1 (surf_ID2 = 0) kartlarını bul"],
        observe: "Katlanma bölgesinde kabuk kendi içinden geçiyor mu (animasyon ×5)",
        expect: "Tek parçada ikisi aynı sonucu verir (kuvvet eğrisi üst üste). Çok parçalı modelde Tüm model her çifti elle tanımlamayı kaldırır; kabuk + solid karışıksa deck'te üç TYPE24 görünür.",
      },
      {
        id: "T20",
        title: "Ezilme mesafesi δ, F–δ ve ortalama ezilme kuvveti (C8b)",
        area: "Çıktı",
        learn: "Ezilme mesafesi hangi düğümden ölçülür; ∫F dδ / δ ile IE / δ neden farklı çıkar.",
        change: "Çıktı ayarları → Ezilme referansı: kızak kartı",
        steps: ["4 · Crash → Çıktı ayarları → Ezilme referansı: Kütle / kızak #1 → çöz", "5 · Sonuçlar → F–δ eğrisi ve “Ortalama ezilme kuvveti” kartı; δ_maks'ı not al", "Referansı kaldır → çöz: ezilme kartı boş gelir (referanssız ölçüm yok)"],
        observe: "F–δ eğrisinin ilk tepesi ve plato seviyesi",
        expect: "Ortalama ezilme kuvveti tepe kuvvetin çok altında kalır (katlanma platosu). ∫F dδ / δ duvar işi, IE / δ gövdenin yuttuğu enerji; ikisi KE kaybı ve sürtünme kadar ayrışır.",
      },
      {
        id: "T22",
        title: "Yay: kızak ↔ zemin, K ve C etkisi",
        area: "Sınır koşulu",
        learn: "/SPRING + /PROP/TYPE4 doğrusal yay; K kuvveti, C sönümü nasıl değiştirir; /TH/SPRING okuma.",
        change: "Ek tanımlar → + Yay",
        steps: ["Ek tanımlar → + Yay → A ucu: Kütle / kızak #1 · B ucu: Nokta (−50, 25, 20) Sabit ✓ · K 500 N/mm · C 0 → çöz", "K 5000 → çöz", "K 500, C 20 → çöz", "Deck'te /PROP/TYPE4 (K kN/mm = 0.5), /SPRING, /BCS/41 kartlarını bul; eğrilerde th_spring_1_FX"],
        observe: "Kızak hızı ve duvar kuvveti eğrisi",
        expect: "Yay kızağı geri çeker: K büyüdükçe duvar kuvveti ve ezilme azalır, yay kuvveti artar. C salınımı söndürür. Yay ucu esnek parçaya değil rijit gövdeye bağlanır.",
      },
    ],
  },
  {
    title: "Model 3 — İki parça: kutu + çarpma plakası (3D solid)",
    setup: [
      "1 · Geometry → şablon “Crash box + çarpma plakası (iki parça)” → parametreler (varsayılan): Box Length L 200 · Box Height h 50 · Box Width b 40 · Wall t 2 · Plate Thickness tp 10 · Plate Margin m 20 · Gap g 1 (mm) → Model üret → Modeli üret",
      "2 · Mesh → 10 mm · 3D solid → Mesh üret; 3 · Material → Tüm parçalara S235 ata, LAW2",
      "4 · Crash → Çarpma: Duvarsız · yalnız ilk hız · Hız 10 · yön −X · Süre 3",
    ],
    tests: [
      {
        id: "T11",
        title: "Duvarsız mod, roller ve temas",
        area: "Sınır koşulu",
        learn: "Hareketli / Sabit / Serbest; duvarsız çarpışma ancak temasla olur.",
        change: "Parçalar rolleri ve 3 Temaslar",
        steps: ["Kutu Hareketli, plaka Sabit, temas YOK → çöz", "Temas ekle TYPE7 kutu → plaka → çöz", "Plaka Serbest → çöz"],
        expect: "Temas yokken kutu plakanın içinden geçer; temasla çarpışır; serbest plaka itilip uzaklaşır.",
        answer: "Duvarsız modda iki parça ancak temas tanımlıysa çarpışır.",
      },
      {
        id: "T12",
        title: "Parçaya ayrı ilk hız",
        area: "Sınır koşulu",
        learn: "Farklı hızlarla gelen parçalar.",
        change: "Temas kalsın, iki parça Serbest; Ek tanımlar → Parçaya ayrı ilk hız",
        steps: ["Kutu 10 m/s (yön −1, 0, 0), plaka 5 m/s (yön 1, 0, 0) → çöz"],
        expect: "Kafa kafaya çarpışma; 1 · Çarpma hızı artık uygulanmaz.",
      },
    ],
  },
  {
    title: "Model 4 — Plaka delinme (hazır senaryo)",
    setup: ["+ Yeni crash vakası → “Plaka delinme / darbe (rijit küre)” → Senaryoyu koş (geometri, mesh, kurulum otomatik)"],
    tests: [
      {
        id: "T13",
        title: "Kopma: basit (EPS_p_max) ve /FAIL",
        area: "Malzeme",
        learn: "Kopma kapalıyken hiçbir şey yırtılmaz.",
        change: "Yalnız 3 Davranış ve kopma",
        steps: [
          "İlk koşu: kopma kapalı (senaryonun kendisi)",
          "Kopma / hasar → Çekme gerinimi: ε_t1 = 0.2, ε_f1 = 0.3 → 4 · Crash → çöz",
          "Çekme gerinimini kapat; LAW2 → EPS_p_max = 0.3 → çöz",
        ],
        observe: "Silinen eleman, animasyonda delik",
        expect: "Kopma açıkken eleman silinir, küre plakayı delebilir.",
      },
      {
        id: "T14",
        title: "Parça başına malzeme modeli",
        area: "Malzeme",
        learn: "Çok parçalı modelde her parçaya ayrı kart.",
        change: "Kopma kapalı; parça #1 (küre) için ayrı kart",
        steps: ["#1 “ayrı” → LAW1; #0 (plaka) LAW2 → çöz"],
        expect: "Küre deforme olmaz, plaka çöker.",
      },
    ],
  },
  {
    title: "Model 6 — Alüminyum kutu (can) ezme: açılı C-kesit çarpıcı + sabit blok",
    setup: [
      "+ Yeni crash vakası → senaryo “Alüminyum kutu (can) ezme — açılı C-kesit çarpıcı” (şablon can_crush_shell, varsayılan parametreler)",
      "3 · Material → kütüphane 6061-T6 (kutu), çarpıcı ve blok çelik; 4 · Crash → Parçalar: çarpıcı Hareketli + Rijit gövde ✓, blok Sabit, kutu Serbest; Temaslar: Tüm model",
    ],
    tests: [
      {
        id: "T23",
        title: "Can crush: açılı C-kesit çarpıcı + sabit blok",
        area: "Sınır koşulu",
        learn: "Rijit çarpıcı + ilk hız, genel temas, kabuk silindirin katlanması (Ansys Explicit örneği).",
        change: "Senaryo: Alüminyum kutu (can) ezme",
        steps: ["+ Yeni crash vakası → senaryo “Alüminyum kutu (can) ezme” → Senaryoyu koş", "Parçalar: çarpıcı Rijit gövde ✓ (hareketli), blok Sabit, kutu Serbest; Temaslar: Tüm model → çöz", "Çarpıcı açısını değiştir (şablon parametresi) → çöz"],
        observe: "Von Mises ve plastik gerinim konturu, katlanma yeri",
        expect: "Kutu önce çarpıcının altında çöker, sonra yana yatarak katlanır; açı büyüdükçe asimetri artar. Genel temas olmadan cidar kendi içinden geçer.",
      },
    ],
  },
  {
    title: "Model 5+ — Diğer hazır senaryolar (her test kendi modeliyle)",
    setup: ["Her test: + Yeni crash vakası → ilgili senaryo → Senaryoyu koş"],
    tests: [
      {
        id: "T15",
        title: "Bölgeyi kilitle (patlama yüklü plaka)",
        area: "Sınır koşulu",
        learn: "Parçanın tamamı değil bir bölgesi kilitlenir.",
        change: "Senaryo: Patlama yüklü plaka; sonra kenar kilidini kaldır",
        steps: ["Olduğu gibi → çöz", "Ek tanımlar'daki kenar kilidi kartını sil → çöz"],
        expect: "Kilit yokken plaka tümüyle uçar — kilit yükün tepkisini taşır.",
      },
      {
        id: "T16",
        title: "Sabit hızla it (kapı intrüzyonu)",
        area: "Sınır koşulu",
        learn: "İlk hız ≠ sabit hız; parça yavaşlamaz.",
        change: "Senaryo: Kapı intrüzyonu",
        steps: ["Senaryoyu koş"],
        observe: "Temas kuvveti–zaman, kirişin eğilmesi",
        expect: "Silindir hızı sabit kalır, kiriş giderek eğilir; ilk hız verilseydi silindir yavaşlardı.",
      },
      {
        id: "T17",
        title: "Yerçekimi (düşme testi)",
        area: "Sınır koşulu",
        learn: "Sabit ivme; düşme testleri.",
        change: "Senaryo: Düşme testi; sonra yerçekimini kapat",
        steps: ["Yerçekimi açık → çöz", "Kapalı → çöz"],
        expect: "Kısa sürede fark küçük — veri.",
      },
      {
        id: "T18",
        title: "Kesit kuvveti (S-kiriş)",
        area: "Çıktı",
        learn: "Modelin içinden geçen düzlemde iç kuvvet.",
        change: "Senaryo: S-kiriş; Çıktı ayarları → + Kesit ekle",
        steps: ["Kirişin ortasından geçen M, M1, M2 ver → çöz", "Sonuçta kesit kuvveti eğrisine bak"],
        expect: "Kesit kuvveti duvar kuvvetinden farklıdır — iç yükü gösterir.",
      },
      {
        id: "T25",
        title: "Karşılaştırma + enerji dengesi okuma",
        area: "Çıktı",
        learn: "IE / KE / HG / toplam enerji eğrilerini birlikte okumak; enerji dengesi ne zaman kötü.",
        change: "Üç koşuyu Karşılaştır; eğri grubu Enerji",
        steps: ["Crash geçmişi → T1b, T2 (a 400), T10 (hourglass) koşularını işaretle → Karşılaştır", "Eğri: Enerji → Toplam enerji, İç enerji, Kinetik enerji, Hourglass sırayla", "Skaler tabloda “Enerji dengesi” ve “HG son / IE son” satırları"],
        observe: "Toplam enerji düz mü, HG/IE yüzde kaç",
        expect: "Toplam enerji yatay kalmalı; düşüyorsa temas/sönüm kaybı, yükseliyorsa hourglass. HG/IE > %10 koşuyu şüpheli yapar (T10'daki ayarla düşer).",
      },
      {
        id: "T26",
        title: "Mini DOE + vekil tahmin",
        area: "Çıktı",
        learn: "20 koşuluk DOE'nin vekil modele yetmediğini görmek; aralık dışı (OOD) uyarısı.",
        change: "ML tezgahı → crash → DOE",
        steps: ["ML tezgahı → Crash → DOE: şablon crash_box, parametreler Wall t 2–4 mm, Hız 8–15 m/s, 20 nokta (LHS) → DOE başlat (Codespaces'te bekle)", "Eğit · 5-fold CV → hedef başına R² / MAE'ye bak", "Tahmin et: t 3, v 10 (aralık içi) ve t 6 (aralık dışı)"],
        observe: "R² değerleri ve OOD uyarısı",
        expect: "20 noktayla R² düşük ve kararsızdır (ezber). Aralık dışı girdi uyarı alır; tahmin güvenilmez. 200 nokta bu yüzden gerekli.",
      },
      {
        id: "T27",
        title: "Kuş / yumuşak cisim çarpması (SPH)",
        area: "Sınır koşulu",
        learn: "SPH parçacık projesi; parçacık aralığı ve kütle tutarlılığı.",
        change: "Senaryo: Kuş / yumuşak cisim çarpması",
        steps: ["Senaryoyu koş", "SPH kartında parçacık aralığını yarıya indir → çöz", "Deck'te /SPHCEL ve /INTER/TYPE7 (SPH ↔ plaka) kartlarına bak"],
        observe: "Plaka tepe kuvveti ve SPH toplam kütle (deck özeti)",
        expect: "Parçacık aralığı küçüldükçe kuvvet eğrisi yumuşar, koşu süresi büyür; toplam kütle ve ilk KE aynı kalmalı.",
      },
      {
        id: "T28",
        title: "Direk (pole) yan çarpması",
        area: "Sınır koşulu",
        learn: "Uç kütleli kirişin direğe çarpması; temas tipi ve uç kütle etkisi.",
        change: "Senaryo: Direk yan çarpması; uç kütleleri",
        steps: ["Senaryoyu koş", "Ek tanımlar → uç kütle kartlarından birini sil → çöz", "Direk yarıçapını şablonda değiştir → çöz"],
        observe: "Kirişin orta sehimi ve temas kuvveti",
        expect: "Uç kütle kalkınca kiriş daha az eğilir, kuvvet daha erken düşer. İnce direk daha derin intrüzyon, daha düşük tepe.",
      },
      {
        id: "T29",
        title: "LS-DYNA .k içe aktarma",
        area: "Çıktı",
        learn: "Hangi kartlar çevrilir, hangileri atlanır; içe aktarılan kurulum neden elle kontrol edilmeli.",
        change: "Crash geçmişi → LS-DYNA içe aktar",
        steps: ["Basit bir .k (tek parça, *MAT_PLASTIC_KINEMATIC, *RIGIDWALL_PLANAR, *INITIAL_VELOCITY) hazırla → LS-DYNA içe aktar", "Çevrilen kartlar / atlananlar listesini oku; 4 · Crash'te malzeme ve duvar kartlarını kontrol et → çöz", "Aynı modeli elle kurup Fmax'ı karşılaştır"],
        observe: "Atlanan kart listesi",
        expect: "Çevrilen kartlar bire bir eşleşir (Fmax aynı); *CONTACT_AUTOMATIC_SINGLE_SURFACE → Tüm model, desteklenmeyen kartlar listede uyarıyla kalır.",
      },
    ],
  },
];
