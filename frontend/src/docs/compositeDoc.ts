/**
 * Kompozit kullanıcı belgesi — Belgeler penceresinin "Kompozit" kitabı (Faz 3.14).
 * Format `crashDoc.ts` ile aynı (`DocSection`); `card` sütunu CalculiX kartı
 * ya da API ucudur.
 *
 * Sayılar repodaki gerçek koşulardan: `docs/COMPOSITE_VALIDATION.md`,
 * `docs/ROADMAP.md` (Faz 3). Görseller `public/docs/composite/`.
 *
 * Araç mühendise karar vermez: dizilim, rozet, nint, dayanım ve kabul eşiği
 * mühendisindir; araç sayıyı verir.
 */
import type { DocScenario, DocSection } from "./crashDoc";

const IMG = (f: string) => `/docs/composite/${f}`;

export const COMPOSITE_DOC: DocSection[] = [
  {
    id: "comp-akis",
    title: "Genel akış",
    intro:
      "Kompozit ayrı bir çözücü değildir: CalculiX'in katmanlı kabuk kesitinin (*SHELL SECTION, COMPOSITE) üzerine kurulu bir " +
      "hazırlık ve sonuç katmanıdır. KOMPOZİT sekmesi: 1 · Geometry → 2 · Mesh (2D kabuk, 2. mertebe) → 3 · Kompozit (ply " +
      "kütüphanesi, dizilim, rozet, sonuçlar). Durability /solve yolu değişmez; kompozit yalnız parçaya dizilim atanmışsa devreye girer.",
    items: [
      { name: "1 · Geometry", what: "STEP/IGES yükle. Kabuk için orta yüzey (midsurface) ya da doğrudan yüzey geometrisi gerekir." },
      { name: "2 · Mesh", what: "2D shell, Kabuk mertebesi = 2 (S6 / S8R). CalculiX COMPOSITE kesiti yalnız S6 / S8R kabul eder; 1. mertebe (S3 / S4) ağla koşu “failed” olur." },
      { name: "3 · Kompozit", what: "Ply kütüphanesi → parça başına dizilim (alt → üst) + canlı ABD → rozet (0° yönü) → koşu → Katman sonuçları paneli." },
      { name: "Koşu", what: "Mesh + dizilim + rozet + sınır koşulları CalculiXAdapter'a gider; koşu composite_runs tablosuna yazılır. Şu an API üzerinden başlatılır (arayüzde koşu kartı yok).", card: "POST /composite/solve" },
      { name: "Plan paneli", what: "Faz 3 mikro-adımları (3.0–3.14) ve verilen kararlar — veri olarak." },
    ],
  },
  {
    id: "comp-ply",
    title: "Ply kütüphanesi",
    intro:
      "Tek yönlü (UD) ortotrop ply: dokuz elastik sabit + dayanımlar. Seed malzemeler tipik değerlerdir (T300/epoxy, E-glass/epoxy) — " +
      "mill test verisi değildir. Formda GPa / MPa girilir, veritabanında Pa saklanır.",
    items: [
      { name: "E1, E2, E3", what: "Lif yönü (1), enine (2) ve kalınlık (3) yönü elastisite modülleri.", card: "*ELASTIC, TYPE=ENGINEERING CONSTANTS" },
      { name: "ν12, ν13, ν23", what: "Poisson oranları (νij: i yönünde çekmede j yönündeki daralma).", card: "*ELASTIC, TYPE=ENGINEERING CONSTANTS" },
      { name: "G12, G13, G23", what: "Kayma modülleri; G13, G23 kalınlık boyunca kesme (kabuk enine kesme).", card: "*ELASTIC, TYPE=ENGINEERING CONSTANTS" },
      { name: "ρ", what: "Yoğunluk (kg/m³ → ccx'te tonne/mm³).", card: "*DENSITY" },
      { name: "Xt, Xc, Yt, Yc, S12", what: "Lif çekme / basma, enine çekme / basma, düzlem içi kesme dayanımları (pozitif büyüklük). Tsai-Wu ve Hashin bunlarla hesaplanır.", card: "** PLY_STRENGTH_MPA (yorum)" },
      { name: "S23 (isteğe bağlı)", what: "Enine kesme dayanımı. Varsa Hashin matris basma tam biçimle; yoksa (σ2/Yc)² + (τ12/S12)² ile hesaplanır ve özet bunu belirtir.", card: "** PLY_STRENGTH_MPA (yorum)" },
      { name: "Kullanıcı tanımlı ply", what: "Formdan yeni ortotrop ply eklenir; seed satırları düzenlenemez.", card: "POST /composite/materials" },
    ],
  },
  {
    id: "comp-dizilim",
    title: "Dizilim ve CLT",
    intro:
      "Parça başına katman listesi, alttan üste: malzeme, açı θ (°, rozetin 0° yönünden), kalınlık t (mm). Tablo değiştikçe Klasik " +
      "Laminat Teorisi (CLT) ile ABD matrisleri canlı hesaplanır. Araç dizilim önermez.",
    items: [
      { name: "Katman satırı", what: "Malzeme, θ, t; ↑↓ ile sıra değişir. Kaydet dizilimi parçaya yazar.", card: "PUT /composite/layups" },
      { name: "A (N/mm)", what: "Düzlem içi rijitlik. [±45]s'de A11 = A22, A16 = 0; [0/90/0]'da A11 > A22.", card: "POST /composite/clt" },
      { name: "B (N)", what: "Düzlem içi – eğilme bağlaşımı. Simetrik dizilimde B = 0.", card: "POST /composite/clt" },
      { name: "D (N·mm)", what: "Eğilme rijitliği.", card: "POST /composite/clt" },
      { name: "CLT önizleme paneli", what: "Kayıt yapmadan dizilim dene: katman ekle / sil, ABD hesapla.", card: "POST /composite/clt" },
    ],
  },
  {
    id: "comp-rozet",
    title: "Rozet (0° yönü)",
    intro:
      "Paralel rozet: katman açıları dir0 vektörüne göre ölçülür (varsayılan global X). Atama tüm parçaya ya da seçili yüzeylere. " +
      "Viewport'ta 0° oku gösterilir. Her farklı katman açısı için bir *ORIENTATION yazılır (taban eksenler + yerel 3 ekseni etrafında θ).",
    items: [
      { name: "dir0 (x, y, z)", what: "0° yönü; normalize edilir. Yüzeye dik verilirse yerel eksen tanımsız kalır.", card: "*ORIENTATION, SYSTEM=RECTANGULAR" },
      { name: "Hedef: parça | yüzey", what: "Rozetin uygulandığı bölge.", card: "PUT /composite/orientations" },
      { name: "Katman açısı", what: "COMPOSITE satırının 4. alanı açı değil ORIENTATION adıdır (OR_0_k); açı her ORIENTATION'ın “3, θ” satırındadır.", card: "*ORIENTATION … 3, θ" },
    ],
  },
  {
    id: "comp-kesit",
    title: "Ağ ve CalculiX kesiti",
    intro:
      "2. mertebe kabuk ağı gmsh serendipity elemanlarıdır (quad8, tri6) ve ccx'e S8R / S6 olarak yazılır. ccx kabuğu içeride katı " +
      "elemana genişletir (S8R → C3D20R); her katman kalınlık boyunca nint integrasyon noktasıyla temsil edilir.",
    items: [
      { name: "Kabuk mertebesi", what: "Mesh panelinde 1 (S3 / S4) | 2 (S6 / S8R). Kompozit için 2. Eğri kenarlarda “2. mertebe optimizasyonu” ters elemana karşı açılabilir.", card: "shell_order" },
      { name: "Katman kartı", what: "Her katman bir satır: kalınlık, nint, malzeme, orientation adı. Alt katman ilk satır.", card: "*SHELL SECTION, ELSET=PART_n, COMPOSITE" },
      { name: "Kenar yükü", what: "Kenara verilen toplam kuvvet eleman boyuyla orantılı dağıtılır (kuadratik kenar: köşe ⅙, orta ⅔). Toplam her zaman girilen kuvvettir.", card: "*CLOAD" },
      { name: "Katman çıktısı", what: "Kompozit koşuda adıma eleman integrasyon noktası gerilmesi eklenir (.dat).", card: "*EL PRINT, ELSET=PART_n / S" },
    ],
  },
  {
    id: "comp-gerilme",
    title: "Katman gerilmesi",
    intro:
      "Kaynak .frd değil .dat'tır: .frd düğüm değerleri katman sınırında ortalanır. ccx 2.23 katman başına 2×2×2 integrasyon noktası " +
      "yazar (alttan üste), gerilmeler ply eksenlerindedir: 1 = lif, 2 = enine.",
    items: [
      { name: "σ11, σ22, τ12", what: "Ply eksenli düzlem gerilmesi (MPa). Kontur eleman başına katmanın IP ortalamasıdır.", card: "<job>.dat" },
      { name: "Katman uç değerleri", what: "Her katman için σ11 / σ22 / τ12 en küçük ve en büyük; koşu skalerlerine yazılır.", card: "ply{k}_s11_min|max …" },
      { name: "Ply alanı", what: "Eleman × katman dizileri (gerilme, IRF, Hashin kipi) koşu klasöründe; sonuç paneli bunu okur.", card: "<job>_ply.json" },
    ],
  },
  {
    id: "comp-hasar",
    title: "Hasar: Tsai-Wu ve Hashin",
    intro:
      "Her integrasyon noktasında iki ölçüt hesaplanır ve IRF (inverse reserve factor) olarak verilir: yük λ ile ölçeklenince ölçütün " +
      "1'e ulaştığı λ = R için IRF = 1/R. IRF = 1 ölçütün sağlandığı yüktür; RF = 1/IRF. Araç eşik veya kabul kriteri koymaz.",
    items: [
      { name: "Tsai-Wu", what: "Düzlem gerilme Tsai-Wu (1971); F12 = F12*·√(F11·F22), F12* parametre (varsayılan −0.5). Katman IRF'i IP'lerin en büyüğü.", card: "tsai_wu_irf_max" },
      { name: "Hashin (1980)", what: "Dört kip: lif çekme, lif basma, matris çekme, matris basma. Hashin IRF dört kipin en büyüğü; kip ayrıca verilir.", card: "hashin_irf_max, hashin_mode" },
      { name: "Konum", what: "En büyük IRF'in elemanı ve katmanı (her iki ölçüt için) ve katman başına en büyük IRF.", card: "tsai_wu_element / _ply, ply{k}_tsai_wu_irf_max" },
      { name: "Dayanım yoksa", what: "Malzemede Xt…S12 eksikse o katmanın IRF'i boş kalır (hesaplanmaz, sıfır sayılmaz).", card: "IRF = null" },
      { name: "Sonraya", what: "Puck, LaRC, ilerleyen hasar (degradasyon) Dalga 2+." },
    ],
  },
  {
    id: "comp-sonuc",
    title: "Sonuç ekranı",
    intro:
      "Katman sonuçları paneli ccx ile çözülmüş koşuları listeler. Özet kartları en büyük IRF ve en küçük RF'yi, yerini ve Hashin kipini " +
      "gösterir; katman seçici zarf (tüm katmanların en büyüğü) ya da tek katman; kontur eleman başına renklidir, üzerine gelince değer.",
    image: IMG("01-sonuc.png"),
    imageCaption:
      "Delikli plaka 200×100 mm, Ø40, [0/45/−45/90]s T300, 5 kN çekme, 770 S8R (uygulama ağı): Tsai-Wu IRF zarfı. En büyük 0.636 " +
      "(RF 1.57) 90° katmanda, delik kenarında; Hashin 0.585, matris çekme.",
    items: [
      { name: "Koşu seçimi", what: "Yalnız ply alanı olan (ccx koşmuş) koşular listelenir.", card: "GET /composite/runs" },
      { name: "Özet kartları", what: "Tsai-Wu ve Hashin en büyük IRF, en küçük RF, eleman, katman, kip; model (eleman, katman sayısı, F12*, S23 kullanımı).", card: "GET /composite/runs/{id}/plies" },
      { name: "Katman seçici", what: "Σ zarf + üstten alta katmanlar; çubuk katmanın en büyük IRF'i (seçili ölçüte göre).", card: "—" },
      { name: "Büyüklük", what: "Tsai-Wu IRF | Hashin IRF | σ11 | σ22 | τ12. IRF ölçeği 0'dan başlar; gerilmede min–maks. Zarfta gerilme mutlak değeri en büyük (işaretli) değerdir.", card: "—" },
      { name: "Kontur", what: "Eleman başına tek renk (mavi düşük, kırmızı yüksek); ince eksen boyunca bakılır, döndürülebilir; üzerine gelince eleman no + değer. Gri = değer yok.", card: "—" },
    ],
  },
  {
    id: "comp-dogrulama",
    title: "Doğrulama (V-P1)",
    intro:
      "Klasik laminat teorisi (CLT) ile ccx karşılaştırması; ayrıntı docs/COMPOSITE_VALIDATION.md. Plakalar 200 × 50 mm (20 × 6 S8R) " +
      "ve 200 × 200 mm (20 × 20 S8R), T300, katman 0.25 mm. Farklar veridir.",
    items: [
      { name: "a · [0/90]s zar (Nx = 10 N/mm)", what: "εx CLT 1.3725e-4, ccx 1.3749e-4 (+0.17 %). εy %3.8 daha negatif: laminat kalınlığında tek C3D20R elemanın kalınlık Poisson etkisi (ν13 = ν23 = 0 ile %0.9)." },
      { name: "b · [30]₄ zar", what: "εx, εy, γxy CLT ile %0.001 içinde; γxy işareti doğru (dengesiz dizilimde kayma bağlaşımı)." },
      { name: "c · [0/90]s SS kare plaka, basınç", what: "Merkez çökme Navier serisi 0.18007 mm, ccx 0.18042 mm (+0.19 %)." },
      { name: "Katman gerilmesi [30/0/90/−45]s", what: "Orta sıra elemanlarında σ1 CLT'ye −0.25 % … +0.10 %." },
      { name: "Hasar (Nx = 100 N/mm)", what: "Orta sırada Tsai-Wu +0.07 … +1.46 %, Hashin +0.16 … +1.68 %. Plakanın en büyük değeri serbest kenar / yük girişindeki köşe elemanında CLT'nin %7 üstünde (CLT kenar etkisini içermez)." },
      { name: "Bulunan hata", what: "İlk kesit yazıcısı COMPOSITE satırına açıyı sayı olarak yazıyordu; ccx “nonexistent orientation” ile duruyordu. Açı başına ORIENTATION ile düzeltildi." },
    ],
  },
  {
    id: "comp-sinir",
    title: "Sınırlar ve sonraya",
    intro: "Dalga 1 kapsamı: ortotrop ply, rozet, dizilim, CLT, COMPOSITE kesit, Tsai-Wu / Hashin, katman sonuçları.",
    items: [
      { name: "Eleman", what: "Yalnız 2. mertebe kabuk (S6 / S8R). Katmanlı katı (solid) eleman yok." },
      { name: "Dalga 2+", what: "Draping, sandviç / çekirdek, ply drop-off, üretim ply kesimi, Puck / LaRC, ilerleyen hasar, OpenRadioss kompozit (crash) — ayrı onay." },
      { name: "Koşu arayüzü", what: "Sınır koşulu + koşu kartı KOMPOZİT sekmesinde yok; koşu API ile başlatılır, sonuçlar panelde görülür." },
    ],
  },
];

/** Doğrulama vakaları — kitapta “şablonlar” tablosu biçiminde. */
export const COMPOSITE_CASES: DocScenario[] = [
  { id: "vp1a", title: "V-P1 a · zar, simetrik çapraz katlı", template: "[0/90]s", setup: "200 × 50 mm, 20 × 6 S8R; x = a'da Nx = 10 N/mm, x = 0'da u = 0, w = 0", features: ["COMPOSITE", "ORIENTATION", "tutarlı düğüm yükü"], validation: "εx +0.17 %, εy +3.8 % (kalınlık Poisson)", reference: "CLT A⁻¹" },
  { id: "vp1b", title: "V-P1 b · zar, dengesiz açılı", template: "[30]₄", setup: "a ile aynı", features: ["kayma bağlaşımı A16"], validation: "εx, εy, γxy ≤ 0.001 %", reference: "CLT A⁻¹" },
  { id: "vp1c", title: "V-P1 c · basit mesnetli kare plaka", template: "[0/90]s", setup: "200 × 200 mm, 20 × 20 S8R, q = 1e-4 MPa, dört kenar w = 0", features: ["eğilme D"], validation: "merkez w +0.19 %", reference: "Navier serisi" },
  { id: "vp1f", title: "V-P1 · katman gerilmesi ve hasar", template: "[30/0/90/−45]s", setup: "200 × 50 mm, Nx = 100 N/mm, T300 dayanımları", features: ["*EL PRINT", "Tsai-Wu", "Hashin"], validation: "σ1 −0.25 … +0.10 %; IRF orta sırada ≤ 1.7 %", reference: "CLT + ölçüt" },
  { id: "hole", title: "Delikli plaka (uygulama ağı)", template: "[0/45/−45/90]s", setup: "200 × 100 mm, Ø40, 770 S8R, sol kenar ankastre, sağ kenar 5 kN", features: ["shell_order 2", "/composite/solve", "Katman sonuçları"], validation: "Tsai-Wu 0.636 (90°, delik kenarı), Hashin 0.585 matris çekme", reference: "uçtan uca koşu (karşılaştırma yok)" },
];
