/**
 * Akış (CFD, OpenFOAM) kullanıcı belgesi — Belgeler penceresinin "Akış"
 * kitabı (Faz 2). Format `crashDoc.ts` ile aynı (`DocSection`); `card`
 * sütunu OpenFOAM sözlüğü / dosyası ya da API ucudur.
 *
 * Sayılar repodaki gerçek koşulardan: `docs/CFD_VALIDATION.md`,
 * `docs/ROADMAP.md` (Faz 2, R1–R6). Görseller `public/docs/cfd/`.
 *
 * Araç mühendise karar vermez: "Ne zaman" satırları tipik kullanımı anlatır;
 * çözücü, mesh seviyesi, gevşetme gibi değerler mühendisindir.
 */
import type { DocScenario, DocSection } from "./crashDoc";

const IMG = (f: string) => `/docs/cfd/${f}`;

export const CFD_DOC: DocSection[] = [
  {
    id: "cfd-akis",
    title: "Genel akış",
    intro:
      "AKIŞ sekmesi dört adımda kurulur: 1 · Geometry → 2 · Mesh (CFD tüneli) → 3 · Akış (çözüm) → sonuçlar ve koşu geçmişi. " +
      "Solver OpenFOAM (ESI v2412) sunucuda Docker imajında koşar; kullanıcı tarafında hiçbir CAE yazılımı gerekmez. " +
      "İç akış (kanal), dış akış (rüzgâr tüneli içinde gövde) ve roket aerodinamiği aynı yoldan çözülür.",
    items: [
      { name: "1 · Geometry", what: "STEP/IGES yükle ya da AKIŞ şablonlarından üret: roket, küre (V-C2), Ahmed gövdesi (V-C4). Yüzey bölgeleri (Physical Group) yamaların adı olur: burun, govde, kanatcik, taban …" },
      { name: "2 · Mesh", what: "Gövdenin çevresine dikdörtgen rüzgâr tüneli kurulur; snappyHexMesh ya da cfMesh ile hacim ağı üretilir; checkMesh tablosu ve katman kapsaması gösterilir." },
      { name: "3 · Akış", what: "Yama rolleri, hız, akışkan, türbülans, çözücü ve çözüm ayarları, kuvvet yamaları. Çalıştır → canlı residual grafiği → özet (Cd, Cl, CdA, Fx) ve alan görselleştirme." },
      { name: "Koşu geçmişi", what: "Tüm CFD koşuları (cfd_runs): en çok 6 koşu yan yana, dışla / geri al, koşu başına PDF rapor." },
      { name: "ML Stüdyo · Akış", what: "Roket CFD DOE → vekil model (Random Forest, K-fold CV) → tahmin. Bkz. “DOE ve vekil model”." },
    ],
  },
  {
    id: "cfd-mesh",
    title: "Mesh: rüzgâr tüneli",
    intro:
      "Gövde STL'e çevrilir (bölge başına ayrı yama), sınır kutusunun x boyu L esas alınarak tünel kurulur. Mesafeler L'nin katıdır. " +
      "Arka plan blockMesh hücresi taban boydur; yüzeyde n seviye inceltme hücreyi taban / 2ⁿ yapar. Mesh'leyici NLGEOM gibi seçilir; otomatik seçim yok.",
    items: [
      { name: "Tünel (giriş / çıkış / yan)", what: "Girişe, çıkışa ve yanlara uzaklık (× L). Yamalar: inlet, outlet, sides (zemin açıksa ground).", card: "system/blockMeshDict" },
      { name: "Zemin", what: "Açıksa tünel tabanı gövdenin altında verilen açıklıkla duvar olur (araç, Ahmed). Roket tünelinde zemin olmaz.", when: "Yer etkisi olan dış akış." },
      { name: "snappyHexMesh", what: "Yüzey seviyesi min–max, kenar (feature) seviyesi, iz (wake) kutusu, sınır katmanı sayısı / büyüme oranı / son katman kalınlığı.", card: "system/snappyHexMeshDict" },
      { name: "cfMesh (cartesianMesh)", what: "Kartezyen çekirdek + sınır katmanı; tünel kutusu ve gövde tek domain.stl. Özel imaj: simsurrogate-openfoam:2412-cfmesh.", card: "system/meshDict" },
      { name: "STL üçgen boyu", what: "Gmsh yüzey üçgenlemesinin en büyük kenarı (mm). Kaba STL, eğri yüzeyde (burun) basamaklanır.", card: "constant/triSurface/body.stl" },
      { name: "checkMesh", what: "Hücre sayısı, en büyük non-orthogonality, skewness, en-boy oranı; başarısız kontrol sayısı. Yalnız veri.", card: "checkMesh" },
      { name: "Katman kapsaması", what: "Yama başına eklenen katman oranı (snappy log'undan).", card: "log.snappyHexMesh" },
    ],
  },
  {
    id: "cfd-bc",
    title: "Yamalar (sınır koşulları)",
    intro:
      "Her yamaya bir rol verilir; alan dosyaları (0/U, 0/p, 0/k, 0/omega, 0/nut) buna göre yazılır. " +
      "Varsayılanlar mesh'ten okunur (inlet → giriş, outlet → çıkış, sides → kayma, gövde yamaları → duvar); mühendis değiştirir.",
    items: [
      { name: "inlet (giriş)", what: "Sabit hız U; p sıfır gradyan; k, ω yoğunluk ve uzunluk ölçeğinden.", card: "fixedValue / zeroGradient" },
      { name: "outlet (çıkış)", what: "Sabit basınç (sıkıştırılamazda kinematik p/ρ, sıkıştırılabilirde mutlak Pa); U inletOutlet.", card: "fixedValue / inletOutlet" },
      { name: "wall (duvar)", what: "Kaymasız; türbülanslı akışta duvar fonksiyonları (nutkWallFunction, omegaWallFunction).", card: "noSlip" },
      { name: "slip (kayma)", what: "Sürtünmesiz duvar — tünel yanları için.", card: "slip" },
      { name: "farfield (serbest akım)", what: "Akış yönüne göre giriş ya da çıkış davranır; hücum açılı roket tünelinde tüm tünel sınırları.", card: "freestreamVelocity / freestreamPressure" },
      { name: "symmetry / empty", what: "Simetri düzlemi; 2B kanal ve pitzDaily'de ön-arka yüzler.", card: "symmetry / empty" },
    ],
  },
  {
    id: "cfd-solver",
    title: "Çözücü ve çözüm ayarları",
    intro:
      "Üç çözücü bulunur, NLGEOM gibi elle seçilir — Mach sayısı yalnız veri olarak gösterilir, çözücü otomatik değişmez. " +
      "Üst katmanlar (API, veritabanı, arayüz) çözücüden bağımsızdır; case yazıcı seçime göre dosyaları üretir.",
    items: [
      { name: "simpleFoam", what: "Daimi, sıkıştırılamaz (SIMPLE). Basınç kinematik (p/ρ).", when: "Mach ≲ 0.3; iç akış, araç, düşük hızlı roket.", card: "application simpleFoam" },
      { name: "rhoSimpleFoam", what: "Daimi, sıkıştırılabilir; mutlak basınç, sıcaklık (0/T), alphat; hava mükemmel gaz (hePsiThermo), μ = ρ·ν. “Transonik basınç denklemi” seçeneği.", when: "Mach ~0.3–0.8.", card: "constant/thermophysicalProperties" },
      { name: "rhoCentralFoam", what: "Yoğunluk tabanlı, şok yakalayan (Kurganov akısı); yerel zaman adımı (localEuler) ile daimi sonuca ilerler; Courant sınırı parametre.", when: "Mach ~0.8 üstü (süpersonik roket).", card: "fluxScheme Kurganov; maxCo" },
      { name: "Türbülans", what: "Laminer ya da k-ω SST; giriş yoğunluğu ve uzunluk ölçeği k ve ω başlangıç değerlerini verir.", card: "constant/momentumTransport" },
      { name: "İterasyon / residual", what: "En çok iterasyon ve p, U residual hedefi; hedefe inince “yakınsadı”, yoksa “iterasyon sınırına ulaştı”.", card: "system/fvSolution residualControl" },
      { name: "Gevşetme", what: "U ve diğer alanlar için SIMPLE gevşetme katsayıları. Hücum açılı kaba ağlı roket 0.9 / 0.9 ile ıraksadı, 0.5 / 0.3 ile yakınsadı (veri).", card: "relaxationFactors" },
      { name: "Çekirdek sayısı", what: "> 1 ise decomposePar (scotch) → mpirun -np N … -parallel → reconstructPar. Docker'a 1 GB paylaşımlı bellek verilir.", card: "system/decomposeParDict" },
    ],
  },
  {
    id: "cfd-sonuc",
    title: "Sonuçlar",
    intro:
      "Koşu bitince özet, yama başına kuvvet, kuvvet katsayısı geçmişi ve alan görselleştirme gösterilir. " +
      "Katsayılar son N iterasyonun ortalaması ± std'dir (N: “Ortalama son N”).",
    image: IMG("02-alan.png"),
    imageCaption: "Alan görselleştirme: gövdede Cp, gövde merkezinden y-kesitinde |U|, gövde önünden 25 akım çizgisi (roket, 40 m/s, α 4°).",
    items: [
      { name: "Residual grafiği", what: "Her alanın ilk residual'ı; log / doğrusal eksen.", card: "log.<çözücü>" },
      { name: "Cd, Cl, CdA, Fx", what: "forceCoeffs: referans hız, alan, uzunluk ve sürükleme / taşıma yönleriyle. CdA = Cd · A_ref.", card: "forceCoeffs" },
      { name: "Yama başına kuvvet", what: "forces: her gövde yaması için basınç + viskoz bileşenler (N) ve moment.", card: "forces" },
      { name: "Alan görselleştirme", what: "Gövde yüzeyinde Cp = (p − p∞)/(½ρ∞U∞²), kesit düzleminde |U|, akım çizgileri |U| renkli. Katmanlar aç/kapa; renk ölçeği katman başına min–max.", card: "surfaces · streamLine" },
      { name: "PDF rapor", what: "Koşu geçmişinde çözülmüş her koşu için: kurulum, yamalar, katsayılar, yama kuvvetleri, roket / Barrowman, residual ve Cd grafikleri.", card: "GET /cfd/runs/{id}/report.pdf" },
    ],
  },
  {
    id: "cfd-roket",
    title: "Roket modülü (R1–R6)",
    intro:
      "Akademik roket yarışmaları için: parametrik roket şablonu ya da gerçek roketin STEP modeli, rüzgâr tüneli içinde dış akış. " +
      "Moment ağırlık merkezine (boşsa burun ucuna) göre alınır; çözüm motor kapalı (power-off).",
    items: [
      { name: "R1 · Roket şablonu", what: "Burun (ogive, konik, elips, von Kármán), gövde tüpü, N yamuk kanatçık, isteğe bağlı boat-tail. Bölgeler: burun, govde, kanatcik, taban." },
      { name: "R2 · Barrowman", what: "Analitik CNα ve basınç merkezi; bileşen tablosu ve kararlılık (kalibre). CFD sonucuyla yan yana gösterilir.", card: "POST /cfd/rocket/barrowman" },
      { name: "R3 · Roket koşusu", what: "Hız V, hücum açısı α, ağırlık merkezi, sıcaklık (Mach için). U∞ = V·(cos α, 0, sin α). Sonuç: CA, CN, CD, CL, Cm, x_cp, CNα, kararlılık.", card: "POST /cfd/rocket/solve" },
      { name: "R4 · Çözücü seçimi", what: "simpleFoam / rhoSimpleFoam / rhoCentralFoam; sıkıştırılabilirde ρ = p∞/(R·T). Paralel koşu." },
      { name: "R5 · Mach × α taraması", what: "Mach listesi × α listesi, her nokta bir R3 koşusu (sıralı, aynı mesh ve çözücü). Mach başına CD (en küçük |α|), CNα (CN–α en küçük kareler eğimi), x_cp ortalaması; tablo ve nokta CSV'si.", card: "POST /cfd/rocket/sweep" },
      { name: "R6 · OpenRocket .ork", what: "Roket şablonunda “OpenRocket .ork içe aktar”: ilk aşamanın burun, gövde tüpleri, ilk yamuk kanatçık seti ve daralan arka geçişi forma dolar; eşlenemeyenler not olarak listelenir. Geometri üretimi mühendisin onayıyla.", card: "POST /cfd/rocket/ork" },
    ],
  },
  {
    id: "cfd-ml",
    title: "DOE ve vekil model (2.9)",
    intro:
      "ML Stüdyo → Akış. Roket CFD DOE'si: seçilen şablon parametreleri ve/veya Mach, α aralıkları LHS ile örneklenir; her örnek " +
      "geometri → tünel mesh'i → roket koşusu. Korpus çözücü başına ayrıdır; hedef başına Random Forest, metrikler K-fold çapraz doğrulamadan.",
    items: [
      { name: "DOE değişkenleri", what: "Mach, α, kanatçık açıklığı / kök / uç veteri / ok mesafesi, burun ve gövde boyu. Seçilmeyenler şablon varsayılanı.", card: "POST /cfd/ml/doe" },
      { name: "Korpus", what: "Çözülmüş, dışlanmamış roket koşuları; girdiler flow.mach, flow.alpha_deg, flow.x_ref_m, geom.<parametre>; tüm koşularda aynı olanlar “sabit” olarak ayrılır.", card: "POST /cfd/ml/corpus" },
      { name: "Hedefler", what: "CD, CL, CA, CN, Cm, x_cp. Hedef başına en az 8 dolu satır." },
      { name: "CV metrikleri", what: "R², MAE, MAPE — her satırın tahmini o satırı görmemiş modelden. Kabul eşiği yok.", card: "POST /cfd/ml/train" },
      { name: "Tahmin", what: "Girdi kutularında eğitim aralığı gösterilir; aralık dışı girdi engellenmez, “eğitim aralığı dışında” diye listelenir.", card: "POST /cfd/ml/predict" },
    ],
  },
  {
    id: "cfd-dogrulama",
    title: "Doğrulama (V-C1–V-C4)",
    intro:
      "Ayrıntı `docs/CFD_VALIDATION.md`. Sayılar ölçülen veridir; ağ yakınsaması ayrı çalışma.",
    items: [
      { name: "V-C1 · Kanal (Poiseuille)", what: "Laminer 2B kanal; basınç düşümü analitik değere karşı (girişteki gelişme bölgesi dahil Δp +%2.9)." },
      { name: "V-C2 · Küre", what: "Re 20–1000; Schiller–Naumann ve Clift–Grace–Weber korelasyonlarına karşı Cd; en ince ağda +%1.4–1.9." },
      { name: "V-C3 · pitzDaily", what: "Basamak arkası yeniden bağlanma uzunluğu; k-ω SST öğretici ağı x_r/h 7.89 (deney 7.0, +%12.7)." },
      { name: "V-C4 · Ahmed gövdesi", what: "φ 25°, 217k hücre, 40 m/s: Cd 0.367 (deney 0.285) — kaba ağ." },
      { name: "Roket ↔ Barrowman", what: "56k hücreli kaba ağ: simpleFoam taraması CNα 10.74 /rad (Barrowman 10.81); tek α'lı koşularda CNα +%28–51. α 0'da CN 0.218 — ağın simetri dışı olması." },
    ],
  },
];

export const CFD_TEMPLATES: DocScenario[] = [
  {
    id: "rocket",
    title: "Roket",
    template: "rocket",
    setup: "Burun + gövde tüpü + N yamuk kanatçık + isteğe bağlı boat-tail; boyutlar mm. OpenRocket .ork ile doldurulabilir.",
    features: ["burun", "govde", "kanatcik", "taban", "Barrowman", "R3 roket koşusu", "R5 tarama", "2.9 DOE"],
    validation: "Barrowman CNα / x_cp ile yan yana (veri).",
    reference: "Barrowman (1967) — subsonik ince gövde + kanatçık.",
  },
  {
    id: "cfd_sphere",
    title: "Küre (V-C2)",
    template: "cfd_sphere",
    setup: "Çapı D olan küre; dış akış tüneli, zemin yok.",
    features: ["kure", "forceCoeffs", "Re taraması"],
    validation: "Cd(Re) — Schiller–Naumann, Clift–Grace–Weber.",
    reference: "Clift, Grace & Weber (1978).",
  },
  {
    id: "ahmed_body",
    title: "Ahmed gövdesi (V-C4)",
    template: "ahmed_body",
    setup: "Standart Ahmed gövdesi, arka eğim açısı φ 0–40°; zeminli tünel.",
    features: ["govde", "zemin", "iz kutusu", "k-ω SST"],
    validation: "Cd(φ) deney tablosu.",
    reference: "Ahmed, Ramm & Faltin (1984).",
  },
];
