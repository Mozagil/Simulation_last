/**
 * Crash eğitim testleri (T1–T18) — Belgeler'in son sayfası (kullanıcı
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
  answer?: string;
}

export interface TrainingGroup {
  title: string;
  /** Modeli kurma adımları (grup başında bir kez). */
  setup: string[];
  tests: TrainingTest[];
}

export const TRAINING_RECORD =
  "Her testte not al: koşu # · değiştirdiğin · IE_final · KE_final · RWALL Fmax · impuls · HG/IE · silinen eleman · gözlem. Karşılaştırma: alttaki Crash geçmişi → koşuları işaretle → Karşılaştır.";

export const CRASH_TRAINING: TrainingGroup[] = [
  {
    title: "Model 1 — Crash box (3 mm), rijit duvara 10 m/s",
    setup: [
      "Crash sekmesi → 1 · Geometry → şablon “Crash box — kabuk (orta yüzey)” → parametreler (varsayılan): Box Length L 300 · Box Height h 50 · Box Width b 40 · Wall t 3 (mm) → Model üret → (pencerede) Modeli üret",
      "2 · Mesh → 5 mm · 2D shell · quad → Mesh üret",
      "3 · Material → 1 Kütüphane: S235 → 2 Parçalara ata: “S235 ata”",
      "4 · Crash → Çarpma: Rijit duvara · Hız 10 · Süre 3 · yön +X · konum -1, 25, 20 → Parçalar: #0 Hareketli → “OpenRadioss çalıştır” ✓",
    ],
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
      },
      {
        id: "T3",
        title: "Hız etkisi (Johnson–Cook c, ε̇₀)",
        area: "Malzeme",
        learn: "Metal hızlı yüklemede sertleşir.",
        change: "a, b, n'yi varsayılana döndür; Hız 15 m/s; Hız etkisi alanları",
        steps: ["c = 0 → çöz", "c = 0.05, ε̇₀ = 1 → çöz"],
        expect: "c > 0 → tepe ve ortalama kuvvet yükselir.",
      },
      {
        id: "T4",
        title: "Sıcaklık etkisi",
        area: "Malzeme",
        learn: "Plastik iş ısıya döner, malzeme yumuşar.",
        change: "T3'ün c = 0.05 koşusuna Sıcaklık alanlarını ekle",
        steps: ["m = 1, T_melt = 1800 K, T_r = 293 K, ρCp = 3.8e6 → çöz"],
        expect: "Kuvvet T3'e göre biraz düşer (etkisi küçük olabilir — veri).",
      },
      {
        id: "T5",
        title: "LAW36 tablo",
        area: "Malzeme",
        learn: "Ölçülmüş σ–ε eğrisiyle malzeme.",
        change: "Hız 10'a dön; LAW2 yerine LAW36",
        steps: ["Eğri 1: 0 235 / 0.1 320 / 0.3 380 → çöz", "T2'nin b = 0 koşusuyla karşılaştır"],
        expect: "Eğri sertleştikçe kuvvet artar; benzer eğride LAW2 ile benzer sonuç.",
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
    ],
  },
];
