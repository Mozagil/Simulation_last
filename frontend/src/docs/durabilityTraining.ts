/**
 * Durability eğitim testleri (D1–D16) — CalculiX statik + modal. Crash
 * eğitimiyle (`crashTraining.ts`) aynı düzen: modele göre sıralı, her model
 * bir kez kurulur, ardından gelen testler bir öncekinden yalnız TEK şeyi
 * değiştirir (geri dönüşler "change" satırında açıkça yazılır).
 *
 * Beklenen değerler kapalı form çözümlerden (kiriş teorisi) — veri olarak
 * verilir, öneri değildir. Kesit: L 500 · T 10 · W 50 mm → I = W·T³/12 =
 * 4166,7 mm⁴, c = T/2 = 5 mm.
 */

import type { TrainingGroup } from "./crashTraining";

export const DURABILITY_TRAINING_RECORD =
  "Her testte not al: koşu adı · değiştirdiğin · düğüm/eleman sayısı · Deplasman max · MAX STRESS · SAFETY FACTOR · FATIGUE LIFE · (varsa) TEPKİ KUVVETİ / PEEQ · Analitik referans sapması · gözlem. Karşılaştırma: alttaki Analiz geçmişi → iki koşuyu işaretle → Karşılaştır.";

export const DURABILITY_TRAINING: TrainingGroup[] = [
  {
    title: "Model 1 — Ankastre kiriş, 3D solid tet, S235, uçtan 500 N",
    setup: [
      "Sol ray ANALİZ TİPİ → DURABILITY → 1 · GEOMETRY → Şablondan üret: “Ankastre kiriş (dikdörtgen kesit)” (L 500 · T 10 · W 50 · r 0) → Model üret → pencerede Fy −500 → Modeli üret (BC listesine Fixed · ankastre_uc ve yük · yuk_yuzeyi gelir)",
      "2 · MESH → Eleman boyutu 5 · 3D solid · Eleman tipi tet → Mesh üret",
      "3 · MATERIAL → Kütüphane S235 → Parça modunda kirişe tıkla → ATA",
      "4 · BOUNDARY CONDITIONS → BC LİSTESİ'nde 2 kayıt → ccx çalıştır ✓ → Case adı “D0 taban” → .inp üret / çöz",
      "Taban (D0) beklenen: Deplasman max ≈ 23,8–23,9 mm (analitik F·L³/(3·E·I) = 23,81 mm), MAX STRESS ≈ 300 MPa üstü (analitik F·L·c/I = 300 MPa; ankastre köşede biraz fazlası)",
    ],
    tests: [
      {
        id: "D1",
        title: "Mesh yakınsaması (eleman boyutu)",
        area: "Mesh",
        learn: "Deplasman mesh'e erken yakınsar; ankastre köşedeki gerilme yakınsamaz (tekillik).",
        change: "Yalnız Eleman boyutu",
        steps: [
          "Eleman boyutu 10 → Mesh üret → çöz",
          "Eleman boyutu 5 → Mesh üret → çöz",
          "Eleman boyutu 2.5 → Mesh üret → çöz",
          "Üç koşuyu Analiz geçmişi'nde karşılaştır",
        ],
        observe: "düğüm sayısı, Deplasman max, MAX STRESS ve CRITICAL NODE konumu, Analitik referans sapması",
        expect:
          "Deplasman max üç koşuda da ≈ 23,8–23,9 mm (fark binde birler mertebesinde). MAX STRESS inceldikçe artmaya devam eder; CRITICAL NODE ankastre yüzün köşesinde. Köşeden uzakta (kök kesitinin ortası) σ ≈ 300 MPa.",
        answer:
          "Fixed tüm yüz düğümlerini kilitler, Poisson daralmasını da engeller — köşede kuramsal olarak sonsuz gerilme oluşur; inceltmek tepeyi büyütür. Global büyüklük (sehim) ve tekillikten uzak gerilme mesh'e yakınsar.",
      },
      {
        id: "D2",
        title: "tet (C3D10) vs quad (C3D8)",
        area: "Mesh",
        learn: "Eleman mertebesi eğilme rijitliğini değiştirir.",
        change: "Eleman boyutu 5'e dön; Eleman tipi tet → quad",
        steps: ["quad → Mesh üret (sonuç kutusunda Hexahedron) → çöz", "D1'in 5 mm tet koşusuyla karşılaştır"],
        observe: "eleman tipi dağılımı, Deplasman max, MAX STRESS",
        expect:
          "3D tet her zaman 2. mertebe C3D10; quad 3D'de 1. mertebe hex C3D8. C3D8 ile sehim analitikten (23,81 mm) belirgin küçük çıkar — kalınlıkta (10 mm) yalnız 2 eleman var ve 1. mertebe tam integrasyonlu eleman eğilmede kayma kilitlenmesi gösterir.",
        answer: "Eğilmede 2. mertebe tet doğru sehimi verir; 1. mertebe hex kalınlık boyunca daha çok eleman ister.",
      },
      {
        id: "D3",
        title: "Güvenlik faktörü ve tahmini S-N",
        area: "Sonuç",
        learn: "SAFETY FACTOR ve FATIGUE LIFE kartlarının neyi okuduğu.",
        change: "Eleman tipi tet'e dön (5 mm); S235'e Tahmini S-N üret",
        steps: [
          "3 · MATERIAL → ▸ Gelişmiş → Tahmini S-N üret (özellik kutusunda S-N: tahmini)",
          "4 · BOUNDARY CONDITIONS → .inp üret / çöz",
          "6 · RESULTS ve metrik kartlara bak; kontur alanını SF'ye çevir",
        ],
        observe: "SAFETY FACTOR, FATIGUE LIFE, SF konturu",
        expect:
          "SAFETY FACTOR = 235 / MAX STRESS ≈ 0,7–0,8 (kırmızı, < 1). S-N noktaları (Rm 360): 10³ → 324 MPa, 10⁶ → 162 MPa, 10⁷ → 144 MPa. MAX STRESS ≈ 324 MPa ve üstü → FATIGUE LIFE ≈ 10³ çevrim (eğrinin üst noktası, ekstrapole edilmez). SF konturu kökte en düşük.",
        answer: "SF statik akma kıstasıdır (yorulma değil). Ömür tek genlik kabulüyle S-N'den okunur; tahmini eğri test yerine geçmez.",
      },
      {
        id: "D4",
        title: "Yük 500 → 300 N (doğrusallık + S-N aralığı)",
        area: "Sınır koşulu",
        learn: "Lineer statikte çıktı yükle orantılı; ömür S-N'de log-log ilerler.",
        change: "Yük kaydını sil (⋯) → Yüzey modunda x = L yüzü → Nokta/yüzey yük Fy −300 → Listeye ekle",
        steps: ["çöz", "D3 ile karşılaştır"],
        observe: "Deplasman max, MAX STRESS, SAFETY FACTOR, FATIGUE LIFE",
        expect:
          "Deplasman ve gerilme D3'ün tam 0,6 katı: δ ≈ 14,3 mm, analitik σ = 180 MPa (FEA tepesi D3'ün 0,6 katı). SF ≈ 1,2–1,3. MAX STRESS 162–324 MPa aralığında → FATIGUE LIFE 10⁵ mertebesi (log-log interpolasyon).",
        answer: "Yük %40 azalınca gerilme %40 azalır ama ömür ~100 kat artar — S-N eğrisi logaritmiktir.",
      },
      {
        id: "D5",
        title: "Kuvvet yerine deplasman kontrolü",
        area: "Sınır koşulu",
        learn: "Displacement BC üç bileşeni de yazar; Ux = 0 uç yüzün dönmesini de tutar.",
        change: "Yük kaydını sil → aynı x = L yüzüne Displacement Ux 0 · Uy −5 · Uz 0",
        steps: ["çöz"],
        observe: "Deplasman max, MAX STRESS, deforme şekil (Deformasyon ölçeği)",
        expect:
          "Deplasman max = 5 mm. Uç yüzün tüm düğümlerinde Ux = 0 → uç dönemez (kılavuzlu uç): σ = 6·E·δ·c/L² ≈ 126 MPa, gerilme kökte ve uçta eşit (ters işaretli), şekil S biçimli. Serbest dönmeli uçta olsaydı 3·E·δ·c/L² ≈ 63 MPa olurdu.",
        answer: "“Yalnız Uy verdim” sanılan BC, uç yüzü kilitleyebilir — Displacement'ın 0 bileşenleri de kısıttır.",
      },
      {
        id: "D6",
        title: "Öz ağırlık (Gravity)",
        area: "Sınır koşulu",
        learn: "Gravity yoğunluktan yayılı yük üretir.",
        change: "Displacement kaydını sil → Gravity gx 0 · gy −9810 · gz 0 (seçim gerekmez)",
        steps: ["çöz"],
        observe: "Deplasman max, MAX STRESS",
        expect:
          "q = ρ·g·A = 7,85e-9 t/mm³ · 9810 mm/s² · 500 mm² ≈ 0,0385 N/mm. δ = q·L⁴/(8·E·I) ≈ 0,34 mm; σ = (q·L²/2)·c/I ≈ 5,8 MPa.",
        answer: "Gravity'nin varsayılanı gz = −9810'dur; kiriş y'de eğildiği için yön elle y'ye verilir. ρ yanlışsa öz ağırlık da yanlıştır.",
      },
    ],
  },
  {
    title: "Model 2 — Aynı kiriş, doğrusal olmayan çözüm (6061-T6)",
    setup: [
      "Model 1 tabanına dön: tet 5 mm, S235, BC LİSTESİ = Fixed · ankastre_uc + yük Fy −500 · yuk_yuzeyi (gerekirse 🔄 Yeni Case Başlat ve Model 1 kurulumu)",
      "NLGEOM ve Plastisite kapalı",
    ],
    tests: [
      {
        id: "D7",
        title: "E değişimi: S235 → 6061-T6",
        area: "Malzeme",
        learn: "Lineer statikte sehim 1/E ile ölçeklenir; gerilme değişmez.",
        change: "3 · MATERIAL → 6061-T6 → ATA",
        steps: ["çöz", "ön kontrol penceresi çıkarsa İptal (lineer devam)"],
        observe: "ön kontrol penceresi, Deplasman max, MAX STRESS, SAFETY FACTOR",
        expect:
          "Lineer teori satırı ve ön kontrol: u/L ≈ %14,5 > %10 eşik → pencere açılır. δ ≈ 23,81·210/68,9 ≈ 72,6 mm; MAX STRESS ≈ D0 ile aynı (statikçe belirli kiriş, gerilme E'den bağımsız); SAFETY FACTOR = 276 / MAX STRESS ≈ 0,8–0,9.",
        answer: "Alüminyum çeliğin ~1/3 rijitliğinde: 3 kat sehim, aynı gerilme.",
      },
      {
        id: "D8",
        title: "NLGEOM (büyük deformasyon)",
        area: "Çözüm",
        learn: "Lineer çözüm denge denklemini deforme olmamış geometride kurar.",
        change: "NLGEOM (büyük deformasyon) ✓ · Artım sayısı 20",
        steps: ["çöz", "D7 ile karşılaştır (Deformasyon ölçeği 1×)"],
        observe: "KİNEMATİK kartı (NLGEOM, artım, yakınsadı), TEPKİ KUVVETİ, Deplasman max, deforme şekil",
        expect:
          "α = F·L²/(E·I) ≈ 0,44. Uç düşey sehimi lineerden ~%2 küçük; uç ayrıca −x yönünde ≈ (3/5)·δ²/L ≈ 6 mm kısalır (lineerde 0). TEPKİ KUVVETİ ≈ 500 N. Çözüm D7'den belirgin daha uzun sürer.",
        answer: "Bu yük düzeyinde fark küçük ama yöndeşir; u/L büyüdükçe lineer ve NLGEOM ayrışır.",
      },
      {
        id: "D9",
        title: "Plastisite (akma sonrası pekleşme)",
        area: "Çözüm",
        learn: "Elastik gerilme akmayı aşınca kalıcı şekil değiştirme ve PEEQ.",
        change: "Plastisite ✓ (pekleşme tablosu boş — Rp0.2 / Rm / A'dan türetilir); NLGEOM açık kalır",
        steps: ["çöz", "D8 ile karşılaştır"],
        observe: "MALZEME · KİNEMATİK kartı (PLASTİK + NLGEOM, PEEQ maks, yakınsadı), MAX STRESS, Deplasman max",
        expect:
          "İlk akma yükü ≈ 500·276/300 ≈ 460 N, tam plastik moment yükü F_p = Rp0.2·W·T²/(4·L) = 690 N → 500 N'da kökte kısmi plastik bölge: PEEQ > 0, MAX STRESS ≈ 276–310 MPa bandına sınırlanır (lineer tepe aşılmaz), sehim D8'den büyük.",
        answer: "Lineer elastik çözüm akma üstü gerilmeyi “olduğu gibi” gösterir; plastisite gerilmeyi akma eğrisine bağlar ve sehimi artırır.",
      },
    ],
  },
  {
    title: "Model 3 — Kabuk kiriş (2D shell, orta yüzey, t = 10 mm)",
    setup: [
      "🔄 Yeni Case Başlat → Model 1'in şablonu (Fy −500) → Modeli üret",
      "Parça modunda kirişi seç → MİD (orta yüzey y = 5 düzleminde, 500 × 50)",
      "2 · MESH → 5 · 2D shell · quad → Mesh üret (S4)",
      "3 · MATERIAL → S235 → mesh elemanına tıkla → ATA → ▸ Gelişmiş: Property shell · Kalınlık 10 → Component güncelle",
      "4 · BOUNDARY CONDITIONS → şablondan gelen iki kaydı sil (katı yüzlerine bağlı) → solidi gizle → Kenar modunda orta yüzeyin x = 0 kenarı → Fixed → x = L kenarı → Nokta/yüzey yük Fy −500 → çöz",
    ],
    tests: [
      {
        id: "D10",
        title: "Kabuk vs katı",
        area: "Mesh",
        learn: "Orta yüzey kabuğu aynı eğilmeyi çok daha az düğümle verir.",
        change: "3D solid (Model 1, D0) → 2D shell",
        steps: ["Kurulumdaki koşu", "D0 ile karşılaştır"],
        observe: "düğüm sayısı, Deplasman max, MAX STRESS",
        expect:
          "δ ≈ 23,6–23,8 mm (analitik 23,81), σ ≈ 300 MPa (kabuk yüzey gerilmesi — üst/alt yüzeyin en büyüğü). Kabukta Fixed 6 serbestliği (dönmeler dahil) tutar. Düğüm sayısı D0'ın çok altında.",
        answer: "İnce cidarlı parçada kabuk yeterli; kalınlık geometride değil Component'te tanımlıdır.",
      },
      {
        id: "D11",
        title: "Uç yükü vs yayılı basınç (aynı toplam kuvvet)",
        area: "Sınır koşulu",
        learn: "Toplam kuvvet aynıyken dağılım sehim ve gerilmeyi değiştirir.",
        change: "Yük kaydını sil → mesh elemanına tıkla (Face = tüm orta yüzey) → Pressure |P| 0.02",
        steps: [
          "çöz (toplam = 0,02 MPa · 50 · 500 = 500 N, q = 1 N/mm)",
          "sehim ters yöndeyse |P| = −0.02 ile tekrar çöz (işaret yüzey normaline bağlı)",
          "D10 ile karşılaştır",
        ],
        observe: "Deplasman max, MAX STRESS",
        expect:
          "δ = q·L⁴/(8·E·I) ≈ 8,9 mm = uç yüklü sehimin 3/8'i; kök momenti q·L²/2 → σ ≈ 150 MPa = uç yüklünün yarısı.",
        answer: "Basınç kabukta yüzeye dik yayılı yük olarak yazılır (dx/dy/dz kullanılmaz). Aynı toplam kuvvet yayılınca moment kolu yarıya iner.",
      },
    ],
  },
  {
    title: "Model 4 — Basit mesnetli kiriş, 3D solid tet, S235, ortadan 500 N",
    setup: [
      "🔄 Yeni Case Başlat → 1 · GEOMETRY → “Basit mesnetli kiriş (dikdörtgen kesit)” (L 500 · T 10 · W 50) → Model üret → Modeli üret",
      "2 · MESH → 5 · 3D solid · tet → Mesh üret · 3 · MATERIAL → S235 → ATA",
      "BC LİSTESİ (şablondan): Displacement 0,0,0 · mesnet_sol (x = 0 yüzü) · Displacement Uy = Uz = 0 · mesnet_sag (x = L yüzü) · yük Fy −500 · yuk_orta (üst orta kenar) → çöz (taban “D-SS”)",
      "Taban beklenen: sol yüzün tüm düğümlerinde Ux = 0 → sol uç dönemez (ankastre–basit mesnet): δ_orta = 7·F·L³/(768·E·I) ≈ 0,65 mm; Analitik referans (FL³/48EI = 1,49 mm) ile sapma büyük",
    ],
    tests: [
      {
        id: "D12",
        title: "Mesnet: yüz → kenar (gerçek basit mesnet)",
        area: "Sınır koşulu",
        learn: "Yüzün tamamını tutmak dönmeyi de tutar; basit mesnet bir çizgidir.",
        change: "mesnet_sol kaydını sil → Kenar modunda x = 0 yüzünün alt kenarı (y = 0) → Displacement Ux 0 · Uy 0 · Uz 0",
        steps: ["çöz", "taban ile karşılaştır"],
        observe: "Deplasman max, MAX STRESS ve konumu, Analitik referans sapması",
        expect:
          "δ_orta ≈ F·L³/(48·E·I) = 1,49 mm; σ = (F·L/4)·c/I = 75 MPa açıklık ortasında. Tabanda: δ ≈ 0,65 mm, en büyük moment sol uçta 3·F·L/16 → σ ≈ 56 MPa (+ köşe tekilliği). Sapma küçülür.",
        answer: "Mesnetin modellenme biçimi (yüz mü çizgi mi) sonucu %100'ün üzerinde değiştirebilir; mesnet idealleştirmesi mühendisin kararıdır.",
      },
      {
        id: "D13",
        title: "Sağ mesnet: Displacement → Sliding",
        area: "Sınır koşulu",
        learn: "Sliding yalnız normal yönü tutar, teğet düzlemde serbest bırakır.",
        change: "mesnet_sag kaydını sil → Yüzey modunda x = L yüzü → Sliding Nx 0 · Ny 1 · Nz 0",
        steps: ["çöz", "D12 ile karşılaştır"],
        observe: "Deplasman max, MAX STRESS",
        expect:
          "D12 ile hemen hemen aynı (δ ≈ 1,49 mm, σ ≈ 75 MPa). Fark: sağ uçta z de serbest; z'yi sol kenar zaten tuttuğu için rijit cisim hareketi oluşmaz.",
        answer: "Uy = Uz = 0 Displacement ile n = (0,1,0) Sliding'in farkı yalnız z serbestliği; Sliding eğik düzlemde de (ör. n = (1,1,0)) kullanılabilir.",
      },
    ],
  },
  {
    title: "Model 5 — Modal: ankastre kiriş, 3D solid tet, S235",
    setup: [
      "Model 1 kurulumu (geometri + tet 5 mm + S235); sol ray ANALİZ TİPİ → MODAL",
      "5 · MODAL → MESNETLER'de Fixed · ankastre_uc (şablondan; yük kaydı modal adıma yazılmaz)",
      "Mod sayısı 6 · f min / f max boş · ccx çalıştır ✓ → Modal çöz",
    ],
    tests: [
      {
        id: "D14",
        title: "Doğal frekanslar ve mod şekilleri",
        area: "Sonuç",
        learn: "Ankastre kirişin eğilme modları ve frekans formülü.",
        change: "Kurulumdaki koşu (statik yerine *FREQUENCY)",
        steps: ["f (Hz) · mode grafiğine bak", "Mod kartlarında Göster / Animasyon", "Tüm modları göster → Kameraları eşle"],
        observe: "ilk üç frekans, mod şekilleri",
        expect:
          "f = (βL)²/(2π)·√(E·I/(ρ·A·L⁴)). İnce yönde (y) 1. eğilme: β₁L = 1,875 → ≈ 33,4 Hz. Geniş yönde (z) 1. eğilme: I 25 kat → ≈ 167 Hz. İnce yönde 2. eğilme: β₂L = 4,694 → ≈ 209 Hz.",
        answer: "Mod şekli normalize gösterilir; renk genliği mutlak değil, şekli anlatır.",
      },
      {
        id: "D15",
        title: "Malzeme: S235 → 6061-T6",
        area: "Malzeme",
        learn: "Frekans √(E/ρ) ile ölçeklenir.",
        change: "3 · MATERIAL → 6061-T6 → ATA",
        steps: ["Modal çöz", "D14 ile karşılaştır"],
        observe: "ilk üç frekans",
        expect:
          "√((68,9/2700)/(210/7850)) ≈ 0,977 → f₁ ≈ 32,6 Hz, diğerleri de ≈ %2 düşük. Rijitlik 1/3'e inse de yoğunluk da ~1/3 olduğundan frekans neredeyse aynı.",
        answer: "Statik sehim E'ye, frekans E/ρ'ya bağlıdır.",
      },
      {
        id: "D16",
        title: "Frekans bandı (f min / f max)",
        area: "Çözüm",
        learn: "Özdeğer aramasını bir aralıkla sınırlamak.",
        change: "f min 100 · f max 300",
        steps: ["Modal çöz"],
        observe: "bulunan mod sayısı ve frekanslar",
        expect: "Yalnız bandın içindekiler (6061-T6 ile): ≈ 163 Hz (geniş yönde 1. eğilme) ve ≈ 204 Hz (ince yönde 2. eğilme); ≈ 33 Hz'lik 1. mod listede yok.",
        answer: "Band ile ilgilenilen aralıktaki modlar doğrudan alınır.",
      },
    ],
  },
];
