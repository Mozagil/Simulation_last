/**
 * Crash eğitim testleri (T1–T17) — Belgeler'in son sayfası (kullanıcı
 * 2026-10-08). Kaynak metin docs/CRASH_EGITIM.md ile aynı; biri değişince
 * diğeri de güncellenir.
 */

export interface TrainingTest {
  id: string;
  title: string;
  learn: string;
  setup?: string;
  steps: string[];
  observe?: string;
  expect: string;
  answer?: string;
}

export interface TrainingGroup {
  title: string;
  tests: TrainingTest[];
}

export const TRAINING_BASE = [
  "Crash sekmesi → 1 · Geometry → şablon “Crash box — kabuk (orta yüzey)” → Model üret → (pencerede) Modeli üret",
  "2 · Mesh → 5 mm · 2D shell · quad → Mesh üret",
  "3 · Material → 1 Kütüphane: S235 → 2 Parçalara ata: “S235 ata”",
  "4 · Crash → Çarpma: Rijit duvara · Hız 10 · Süre 3 · yön +X · konum -1, 25, 20 → Parçalar: #0 Hareketli → “OpenRadioss çalıştır” ✓ → .rad üret / çöz",
  "Karşılaştırma: alttaki Crash geçmişi → koşuları işaretle → Karşılaştır",
];

export const TRAINING_RECORD =
  "Her testte not al: koşu # · değiştirdiğin · IE_final · KE_final · RWALL Fmax · impuls · HG/IE · silinen eleman · gözlem.";

export const CRASH_TRAINING: TrainingGroup[] = [
  {
    title: "A — Malzeme (3 · Material)",
    tests: [
      {
        id: "T1",
        title: "LAW1 elastik vs LAW2 plastik",
        learn: "Malzeme modeli enerjinin yutulup yutulmadığını belirler.",
        steps: ["Taban; 3 Davranış: LAW1 → çöz", "LAW2 → tekrar çöz", "Geçmişte iki koşuyu karşılaştır"],
        observe: "IE_final, KE_final, impuls, animasyon",
        expect: "LAW1 → IE çok küçük, KE ≈ başlangıç, impuls ≈ 2·m·v (seker, ezilmez). LAW2 → IE büyür, ön uç katlanır.",
        answer: "Elastik malzeme çarpıp geri seker, enerji yutmaz; ezilen metal için LAW2 (elasto-plastik) gerekir.",
      },
      {
        id: "T2",
        title: "Akma ve pekleşme (a, b, n)",
        learn: "σ = a + b·εₚⁿ — akma ve sertleşme kuvveti nasıl değiştirir.",
        steps: ["LAW2: b = 0, n = 1 → çöz", "b = 500 MPa, n = 0.5 → çöz", "a = 400e6 Pa → çöz"],
        observe: "RWALL Fmax, ortalama kuvvet (grafik), IE",
        expect: "b ve a büyüdükçe kuvvet artar, aynı sürede daha az ezilir.",
      },
      {
        id: "T3",
        title: "Hız etkisi (Johnson–Cook c, ε̇₀)",
        learn: "Metal hızlı yüklemede sertleşir.",
        steps: ["LAW2, Hız 15 m/s: c = 0 → çöz", "c = 0.05, ε̇₀ = 1 → çöz"],
        expect: "c > 0 → tepe ve ortalama kuvvet yükselir.",
      },
      {
        id: "T4",
        title: "Sıcaklık etkisi",
        learn: "Plastik iş ısıya döner, malzeme yumuşar.",
        steps: ["T3 (c = 0.05) + m = 1, T_melt = 1800 K, T_r = 293 K, ρCp = 3.8e6 → çöz"],
        expect: "Kuvvet T3'e göre biraz düşer (etkisi küçük olabilir — veri).",
      },
      {
        id: "T5",
        title: "Kopma: basit (EPS_p_max) ve /FAIL",
        learn: "Kopma kapalıyken hiçbir şey yırtılmaz.",
        setup: "+ Yeni crash vakası → Plaka delinme (rijit küre) → Senaryoyu koş (kopma kapalı)",
        steps: [
          "3 · Material → Kopma / hasar → Çekme gerinimi: ε_t1 = 0.2, ε_f1 = 0.3 → 4 · Crash → çöz",
          "Ek: LAW2 → EPS_p_max = 0.3 ile dene (basit sınır)",
        ],
        observe: "Silinen eleman, animasyonda delik",
        expect: "Kopma açıkken eleman silinir, küre plakayı delebilir.",
      },
      {
        id: "T6",
        title: "LAW36 tablo",
        learn: "Ölçülmüş σ–ε eğrisiyle malzeme.",
        steps: ["Taban; LAW36 → Eğri 1: 0 235 / 0.1 320 / 0.3 380 → çöz", "T2 (b = 0) ile karşılaştır"],
        expect: "Eğri sertleştikçe kuvvet artar; LAW2 ile benzer eğride benzer sonuç.",
      },
      {
        id: "T7",
        title: "Parça başına malzeme modeli",
        learn: "Çok parçalı modelde her parçaya ayrı kart.",
        setup: "Plaka delinme senaryosu",
        steps: ["3 Davranış: parça #1 (küre) “ayrı” → LAW1; #0 (plaka) LAW2 → çöz"],
        expect: "Küre deforme olmaz, plaka çöker.",
      },
    ],
  },
  {
    title: "B — Sınır koşulları (4 · Crash)",
    tests: [
      {
        id: "T8",
        title: "Duvar yönü, konum, açı, Modelden seç",
        learn: "/RWALL tanımı ve viewport işaretleri.",
        steps: [
          "Taban (LAW2); yön +X, konum “⌖ Modelden seç” ile ön uca tıkla → çöz",
          "Açı 15° → çöz",
          "Bilerek yanlış yön (−X) → çöz",
        ],
        expect: "15°: eğik çarpma, kuvvet düşer. Yanlış yön: parça duvardan uzaklaşır → kuvvet ≈ 0 (kurulum hatası böyle görünür).",
      },
      {
        id: "T9",
        title: "Duvarsız mod ve parça rolleri",
        learn: "Hareketli / Sabit / Serbest; duvarsız çarpışma temasla olur.",
        setup: "Şablon “Crash box + çarpma plakası (iki parça)” (3D solid, 10 mm) → malzeme ata → Duvarsız · yön −X · kutu Hareketli, plaka Sabit",
        steps: ["Temas YOK → çöz", "Temas ekle TYPE7 kutu → plaka → çöz", "Plaka Serbest → çöz"],
        expect: "Temas yokken kutu plakanın içinden geçer; temasla çarpışır; serbest plaka itilip uzaklaşır.",
        answer: "Duvarsız modda iki parça ancak temas tanımlıysa çarpışır.",
      },
      {
        id: "T10",
        title: "Öz temas ve TYPE7 / TYPE24",
        learn: "Katlanan kabuğun katları birbirine girmesin.",
        setup: "Crash box + Kızak testi (40 kg, rayda), Süre 25 ms",
        steps: ["Temas yok → çöz", "TYPE7 #0↔#0 → çöz", "TYPE24 #0↔#0 → çöz"],
        observe: "Animasyon (katlar), ortalama kuvvet",
        expect: "Temas yok → katlar iç içe geçer, kuvvet düşük; öz temasla gerçekçi katlanma.",
      },
      {
        id: "T11",
        title: "Kızak: rayda vs serbest",
        learn: "Rijit gövde + kütle; ray (DOF) neden gerekli.",
        setup: "Kızak testi 50 kg, şablonda et kalınlığı 2 mm, 12 m/s, 30 ms",
        steps: ["Hareket: Rayda → çöz", "Hareket: Serbest → çöz"],
        expect: "Serbest: ~120 mm sonra kutu yana yatar, kuvvet çöker (DOE pilotunda yaşandı). Rayda: katlanarak ezilir, kızak durur.",
      },
      {
        id: "T12",
        title: "Bölgeyi kilitle (BCS) — tam ve kısmi",
        learn: "Parçanın tamamı değil bir bölgesi; DOF seçimi.",
        setup: "+ Yeni vaka → Patlama yüklü plaka (kenarlar ankastre)",
        steps: ["Olduğu gibi → çöz", "Kenar kilidini kaldır (kartı sil) → çöz"],
        expect: "Kilit yokken plaka tümüyle uçar — kilit yükün tepkisini taşır.",
      },
      {
        id: "T13",
        title: "Sabit hızla it (IMPVEL)",
        learn: "İlk hız ≠ sabit hız; parça yavaşlamaz.",
        setup: "+ Yeni vaka → Kapı intrüzyonu (silindir sabit hızla itilir)",
        steps: ["Senaryoyu koş"],
        observe: "Kuvvet–zaman (temas), kirişin eğilmesi",
        expect: "Silindir hızı sabit kalır, kiriş giderek eğilir; ilk hız verilseydi silindir yavaşlardı.",
      },
      {
        id: "T14",
        title: "Parçaya ayrı ilk hız",
        learn: "Farklı hızlarla gelen parçalar.",
        setup: "T9 (temaslı) kurulumu, iki parça Serbest",
        steps: ["Ek tanımlar → Parçaya ayrı ilk hız: kutu 10 m/s (−X), plaka 5 m/s (+X) → çöz"],
        expect: "Kafa kafaya çarpışma; 1 · Çarpma hızı artık uygulanmaz.",
      },
      {
        id: "T15",
        title: "Yerçekimi",
        learn: "Sabit ivme; düşme testleri.",
        setup: "+ Yeni vaka → Düşme testi (H ile v = √(2gH))",
        steps: ["Yerçekimi açık → çöz", "Kapalı → çöz"],
        expect: "Kısa sürede fark küçük — veri.",
      },
    ],
  },
  {
    title: "C — Uzman ve çıktı",
    tests: [
      {
        id: "T16",
        title: "Hourglass (Uzman ayarları)",
        learn: "HG/IE ne demek, nasıl düşer.",
        steps: ["T11 (rayda) koşusunda HG/IE'ye bak (≈ %7)", "Uzman → Ishell 24 → tekrar çöz"],
        expect: "HG/IE düşer; kuvvet biraz değişebilir.",
      },
      {
        id: "T17",
        title: "Çıktı ayarları (preprocess) + CFC (post-process)",
        learn: "Neyin kaydedildiği ile nasıl süzüldüğü farklı şeyler.",
        steps: [
          "4 · Crash → Çıktı ayarları: TH aralığı 0.1 ms vs boş → tepe değişir mi?",
          "S-kiriş senaryosunda kesit ekle → kesit kuvveti",
          "5 · Sonuçlar → CFC 60 / 600 → Uygula",
        ],
        expect: "Kaba TH tepeyi kaçırır; CFC tepeyi düşürür (ham eğri korunur).",
      },
    ],
  },
];
