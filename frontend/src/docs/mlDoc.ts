/**
 * ML Stüdyo (vekil / surrogate model) kullanıcı belgesi — durability
 * (CalculiX) ve crash (OpenRadioss). Format `crashDoc.ts` ile aynı
 * (`DocSection`); `dyna` alanı kullanılmaz, `card` yalnız API ucu ya da
 * dosya adı için.
 *
 * Sayılar repodaki gerçek kayıtlardan: `uploads/models/**.joblib` metrikleri,
 * `uploads/reports/crash_doe_3/report.json`, `docs/ROADMAP.md` (0.5–0.6,
 * 1.19), `docs/validation/crash_validation.md`.
 *
 * Araç mühendise karar vermez: metinler ekranın ne gösterdiğini ve verinin
 * ne söylediğini anlatır, eşik / ayar önermez.
 */
import type { DocSection } from "./crashDoc";

export interface MlExample {
  id: string;
  title: string;
  domain: "crash" | "durability";
  setup: string;
  inputs: string[];
  targets: string[];
  results: string[];
  lesson: string;
}

export const ML_DOC: DocSection[] = [
  {
    id: "ml-genel",
    title: "Genel bakış",
    intro:
      "ML Stüdyo, çözülmüş FEA koşularından bir vekil model (surrogate) eğitir: parametre girilir, solver çalışmadan " +
      "saniyenin altında skaler sonuç (maks deplasman, gerilme, tepe kuvvet, yutulan enerji …) döner. Vekil model FEA'nın " +
      "yerine geçmez; FEA'nın ürettiği verinin içinden ara değer okur. Tezgahtaki “ML Stüdyo” çipiyle açılır, " +
      "“Tezgaha dön” ile çıkılır. Üst şeritte alan seçilir: Durability (CalculiX) ya da Crash (OpenRadioss) — " +
      "korpuslar ve modeller ayrıdır, birbirine karışmaz.",
    items: [
      {
        name: "FEA ↔ vekil model",
        what:
          "FEA: her tasarım için mesh + çözüm (dakikalar). Vekil model: DOE ile önceden çözülmüş N koşudan öğrenilen " +
          "fonksiyon (milisaniyeler). Model yalnız eğitildiği hedefleri ve eğitildiği aralığı bilir.",
      },
      {
        name: "Ne zaman güvenilir",
        what:
          "Girdi eğitim aralığının içindeyse ve o hedefin holdout / CV metriği (R², MAPE) ekranda görünür durumdaysa. " +
          "Aralık dışındaki girdi engellenmez, “uzay dışı” olarak işaretlenir; güvenilirlik kararı mühendisindir.",
      },
      {
        name: "Her şablon ayrı model",
        what:
          "Korpus tek şablondan eğitilir (üst şerit: “Her şablon ayrı model · korpus tek şablondan eğitilir”). " +
          "Durability'de lineer ve NLGEOM modelleri de ayrıdır; crash'te model şablon × senaryo başınadır.",
      },
      {
        name: "Ham kartlı koşular (crash)",
        what:
          "Ham kart editörüyle eklenen kartlar parametre değildir, girdi sütunu olamaz; aynı parametrelerle farklı " +
          "model demektir. Bu koşular korpusa varsayılan girmez (özette “düşen · raw_cards”). Model sekmesindeki " +
          "“Ham kartlı koşuları dahil et” kutusu ile alınır — karar mühendisin.",
      },
      {
        name: "Aşamalar",
        what:
          "Durability: DOE → Veri seti → Yakınsama → Model → Tahmin. Crash: DOE → Model → Tahmin → Doğrulama. " +
          "Aşama çubuğunun altındaki kısa satır canlı durumdur (örn. “#14 · 200 örnek”, “hybrid · σ %1.86”).",
      },
    ],
  },
  {
    id: "ml-kavramlar",
    title: "Kavramlar",
    intro: "Ekranlarda geçen terimler. Tanımlar, aracın bunları nasıl hesapladığına göre yazıldı.",
    items: [
      {
        name: "DOE (deney tasarımı)",
        what:
          "Taranacak parametreler ve aralıkları + örnek sayısı. Her örnek bir FEA koşusudur; sonuçlar korpusun hammaddesi.",
      },
      {
        name: "LHS (Latin Hypercube)",
        what:
          "Her parametre aralığı N eşit dilime bölünür, her dilimden tam bir örnek alınır; boyutlar arasında rastgele " +
          "eşlenir. Aynı tohum (seed) aynı örnekleri üretir — çalışma yinelenebilir.",
      },
      {
        name: "Tohum (seed)",
        what: "LHS'nin rastgele sayı başlangıcı. Tohum + aralıklar + N kaydedilir; aynı üçlü aynı tasarımı verir.",
      },
      {
        name: "Korpus",
        what:
          "Eğitime giren koşuların tablosu: satır = koşu, sütun = girdiler + hedefler. Durability'de “canlı süzgeç” " +
          "(eğitim anında süzgeçten geçen run'lar) ya da donmuş set (adı ve run listesi sabit). Crash'te şablon + " +
          "senaryo + kaynak (tüm çözülmüş koşular ya da tek DOE çalışması).",
      },
      {
        name: "Girdi / hedef",
        what:
          "Girdi (feature): modele verilen sayılar — geometri parametreleri, hız, kütle, yük, eleman boyutu. " +
          "Hedef (target): modelin tahmin ettiği sonuç skalerleri. Tüm koşularda aynı kalan girdi “sabit” olarak " +
          "ayrılır, modele girmez (veriden etkisi öğrenilemez).",
      },
      {
        name: "Holdout",
        what:
          "Durability skaler modelleri: korpusun %25'i eğitimden ayrılır, metrik bu görülmemiş kısımda ölçülür " +
          "(“test”). En az 12 örnek gerekir; altında kart “holdout yok” der ve yalnız eğitim metriği vardır.",
      },
      {
        name: "K-fold CV (çapraz doğrulama)",
        what:
          "Crash modelleri: korpus K parçaya (varsayılan 5) bölünür; her satırın tahmini o satırı görmemiş modelden " +
          "gelir. Raporlanan metrik budur, eğitim skoru gösterilmez. Hedef başına en az 8 dolu satır.",
      },
      {
        name: "R²",
        what:
          "1 − (artık kareler toplamı / hedefin varyansı). 1 = tam isabet; 0 = ortalamayı söylemek kadar. Hedefin " +
          "korpustaki yayılımına bağlıdır: dar aralıklı hedefte küçük hata da R²'yi düşürür.",
      },
      {
        name: "MAE",
        what: "Ortalama mutlak hata, hedefin biriminde (mm, MPa, kN, J). Tahmin kutusundaki “±” değeri crash'te CV MAE'dir.",
      },
      {
        name: "MAPE",
        what:
          "Ortalama mutlak yüzde hata, mean(|y − ŷ| / |y|). Küçük değerli hedeflerde (kısa ezilme, küçük sehim) " +
          "yüzde büyür; MAE ile birlikte okunur.",
      },
      {
        name: "Aralık dışı (out_of_domain)",
        what:
          "Bir girdi eğitim korpusundaki [min, maks] dışında. Durability'de hangi girdinin, hangi yönde, kaç kat dışarıda " +
          "olduğu listelenir; crash'te dışarıdaki girdi adları listelenir ve form satırı işaretlenir. Tahmin yine üretilir.",
        card: "out_of_domain / domain_violations",
      },
      {
        name: "Ekstrapolasyon",
        what:
          "Eğitim aralığının dışında tahmin. Random Forest dışarıda sabit bir değer döndürür (son yapraktaki ortalama) ve " +
          "bunu hata vermeden yapar. Log-log model güç yasası öğrendiği için dışarıda makul kalabilir ama garanti yoktur.",
      },
      {
        name: "Model türleri",
        what:
          "Random Forest (RF): ağaç topluluğu, parçalı-sabit. Log-log lineer: log(hedef) = Σ aᵢ·log(xᵢ) — katsayılar üs " +
          "olarak okunur (kirişte u ∝ L³·T⁻³·W⁻¹). Hibrit: log-log + artığına RF. GNN alan modeli: prototip, " +
          "başarı ölçütünü tutmadı (aşağıda). Crash: hedef başına RF.",
      },
    ],
  },
  {
    id: "ml-dur-doe",
    title: "Durability · 1 — DOE",
    intro:
      "Sol pano tasarım uzayı, sağ pano çalışma sonuçları. Şablon seçilir, her parametre için Aralık ya da Sabit verilir; " +
      "açık mavi bant taranan aralık, ▼ şablon varsayılanıdır. Başlangıç değeri şablon varsayılanının ±%20'si.",
    items: [
      { name: "Şablon", what: "Parametrik geometri ailesi (kiriş, delikli plaka …). Değiştirince aralıklar sıfırlanır." },
      {
        name: "Parametre satırı · Aralık / Sabit",
        what: "Aralık: min–maks, LHS bu aralığı tarar. Sabit: tüm örneklerde tek değer (korpusta sabit sütun olur).",
      },
      {
        name: "Eleman boyutu · Oranlı / Sabit mm",
        what:
          "Oranlı: eleman = oran × şablonun karakteristik uzunluğu (es/t). Sabit mm: mutlak eleman boyutu aralığı. " +
          "Eleman boyutu modelin girdisidir.",
      },
      { name: "Yük katsayısı (k)", what: "Şablon yükünün çarpanı (× şablon yükü); yön ve tip korunur, aralık olarak taranır." },
      { name: "Malzeme çipleri", what: "Birden fazla seçilirse örnekler malzemeler arasında dengeli dağılır." },
      { name: "Örnek / Tohum", what: "LHS örnek sayısı ve tohum." },
      { name: "ccx çalıştır", what: "Kapalıysa yalnız örnekler ve girdi dosyaları üretilir, çözücü koşmaz." },
      {
        name: "200'lük kalite seti",
        what:
          "Şablona özgü sabit aralıklarla 200 örnek, tohum 2026 — referans set. Formdaki aralıklar kullanılmaz.",
        card: "POST /doe/quality-set",
      },
      { name: "DOE başlat", what: "Çalışmayı oluşturur ve kuyruğa alır; hatalı örnek diğerlerini durdurmaz.", card: "POST /doe/studies" },
      {
        name: "Çalışma çipleri (#id ●)",
        what: "Son çalışmalar; ● çalışıyor demektir. Seçilen çalışmanın Sonuç dağılımı sağda açılır.",
      },
      {
        name: "Sonuç dağılımı",
        what:
          "Kalite şeridi (ok / analytic_warn / diğer etiket oranları), dört strip grafik (maks deplasman, maks von Mises, " +
          "Δ deplasman ve Δ von Mises — analitiğe göre %), “En çok sapan 4 örnek” (tıklayınca run tezgahta açılır). " +
          "“Tabloyu aç”: tüm örneklerin parametre + skaler + sapma tablosu, başlığa tıklayınca sıralanır.",
        card: "GET /doe/studies/{id}/results",
      },
    ],
  },
  {
    id: "ml-dur-veri",
    title: "Durability · 2 — Veri seti",
    intro:
      "Eğitim verisinin sayımı, donmuş korpuslar ve yedekleme. Analiz geçmişi ve çözüm dosyaları yalnız çalışılan ortamda " +
      "yaşar; ortam silinirse veri de gider (ekrandaki uyarı şeridi). Başlıkta “son yedek …” rozeti bu tarayıcıdaki son arşiv indirmesidir.",
    items: [
      { name: "Sayaçlar", what: "Çözülmüş run, eğitim .npz, geometri, malzeme, çözülmemiş." },
      { name: "Şablona göre", what: "Şablon başına çözülmüş / çözülmemiş / dışlanan çubukları." },
      {
        name: "+ Yeni set dondur",
        what:
          "Canlı süzgeçten geçen run listesini bir adla sabitler (örn. kiris-v2). Sonradan çözülen run'lar sete kendiliğinden girmez; " +
          "eğitim yinelenebilir olur.",
        card: "POST /surrogate/corpus/freeze",
      },
      { name: "Donmuş set listesi", what: "Ad, şablon, dondurulma tarihi, elle eklenen run sayısı, run sayısı." },
      { name: "Tümünü indir", what: "Tüm DB satırları + çözüm dosyaları (.frd.gz, .train.npz) tek arşivde; “Yalnız çözülmüş run'lar” seçeneği.", card: "GET /dataset/export" },
      { name: "Eğitim setini indir", what: "Yalnız seçili donmuş setin run'ları + setin tanımı." },
      { name: "Seçili run'lar", what: "Analiz Geçmişi'nde işaretlenen run'ları indirir; seçim yoksa pasif." },
      {
        name: "İçe aktar",
        what: ".tar.gz / .tgz arşivi. Hiçbir kaydı silmez, ekler — aynı arşivi iki kez almak kayıtları çoğaltır.",
        card: "POST /dataset/import",
      },
      { name: "Son işlemler", what: "Bu oturumdaki dışa / içe aktarma ve dondurma günlüğü." },
    ],
  },
  {
    id: "ml-dur-yakinsama",
    title: "Durability · 3 — Yakınsama",
    intro:
      "Tek geometri, artan çözünürlük: hedef skalerlerin düğüm sayısıyla nasıl değiştiğini ölçer. DOE'den farkı geometrinin " +
      "sabit olması — burada ölçülen şey mesh hatasıdır. Panel kararlı bant çizmez; ardışık sapma, en inceye göre sapma ve " +
      "(şablonda varsa) analitik referans gösterilir.",
    items: [
      { name: "Geometri kartları / malzeme çipleri", what: "Taramanın sabit geometrisi ve malzemesi." },
      {
        name: "Basamaklar · Oran · es/t / Mutlak mm",
        what:
          "Kabadan inceye eleman boyutları. Varsayılan oran: 1.5, 1.2, 1.0, 0.8, 0.6, 0.5, 0.4, 0.3; mutlak: 15 … 3 mm. " +
          "“+ Basamak”, “×” (en az 2 basamak), “Varsayılana dön”.",
      },
      {
        name: "Taramayı başlat",
        what: "Solver gerçekten çalışır (8 basamak ≈ 100 s); patlayan basamak atlanır.",
        card: "POST /doe/convergence",
      },
      {
        name: "Yakınsama kartları",
        what: "Maks deplasman ve maks von Mises — düğüm sayısına karşı; son iki basamak farkı ve analitik çizgisi.",
      },
      { name: "Basamak başına Δ karoları", what: "Her basamağın bir öncekine göre yüzde değişimi." },
      { name: "Tabloyu aç", what: "es (mm), oran, düğüm, her hedef için değer / Δönceki / Δen ince, durum." },
    ],
  },
  {
    id: "ml-dur-model",
    title: "Durability · 4 — Model",
    intro:
      "Şablon + korpus seçilir, üç skaler model eğitilir ve holdout metrikleri kartlarda görünür. Hedefler: max_displacement, " +
      "max_von_mises (ham tepe), max_von_mises_away (kısıttan uzak, maskeli), max_von_mises_near_peak. Kart çubuğu test MAPE'dir.",
    items: [
      { name: "Şablon", what: "Seçim kutusu; her şablonun yanında kayıtlı model sayısı ya da “model yok”." },
      {
        name: "Kullanılan set",
        what:
          "“canlı süzgeç”: eğitim anında süzgeçten geçen run'lar. Donmuş set çipi: “ad · N run (+elle)”. " +
          "Süzgeç gerekçeleri: u/L eşiği aşıldı, mesh oranı medyandan uzak, başka şablon / malzeme, analitik sapma uyarısı, " +
          "statik değil, rijit cisim, yakınsamadı, dejenere mesh, özellik eksik, çözülmemiş.",
      },
      {
        name: "NLGEOM",
        what:
          "Lineer (küçük deformasyon) ve NLGEOM (büyük deformasyon) ayrı korpus, ayrı model. NLGEOM seçili ve model yoksa " +
          "not çıkar; tahmin lineer modele düşmez.",
      },
      {
        name: "Model kartları · Random Forest / Log-log lineer / Hibrit",
        what:
          "Durum (eğitilmedi / eğitildi / aktif), örnek sayısı, “holdout yok” notu, u ve σ test MAPE çubukları. " +
          "“… eğit” düğmesi o türü eğitir; “Aktif yap” Tahmin aşamasının kullandığı türü seçer.",
        card: "POST /surrogate/scalar/train",
      },
      { name: "Üçünü de eğit", what: "RF, log-log ve hibriti sırayla aynı korpusta eğitir." },
      {
        name: "Alan modeli · GNN (prototip)",
        what:
          "Düğüm başına deplasman / von Mises RMSE ve holdout u_max gösterilir. Başarı ölçütü (holdout u_max hatası < %5) " +
          "karşılanmadı; kart “GNN alan modeli prototip — sonuçlar geçersiz” der. “GNN eğit (prototip)” düğmesi durur.",
        card: "POST /surrogate/gnn/train",
      },
      {
        name: "Eğitim seti · dondur, açık run'ı karneyle ekle",
        what:
          "“Seti dondur”: canlı süzgeci adla sabitler. “Run N karnesi”: tezgahta açık run süzgeçten geçiyor mu, u/L ve mesh " +
          "sapmasıyla. “Sete ekle” ya da (süzgeçten geçmediyse) “Yine de ekle (override)” — karar kullanıcının.",
        card: "POST /surrogate/corpus/{name}/evaluate · /add",
      },
      { name: "Açık run tahmini", what: "Tezgahta açık run/geometri için tahmin; sonuç tezgah viewport'unda “tahmin” olarak ayrı gösterilir.", card: "POST /surrogate/predict" },
      {
        name: "Doğrulama · Tahmin ↔ FEA",
        what:
          "Çözülmüş run'lar aktif modelden geçirilir, ccx çalışmaz. Seçenekler: hedef u / σ, “yalnız <korpus>”, Son N run, " +
          "Ad içerir. “Tabloyu oluştur” → saçılım (açık bant ±%5, kahverengi = uzay dışı run), Örnek / Ort. |Δσ| / Ort. |Δu| / " +
          "Maks |Δu| ve satır tablosu (FEA u_max, tahmin, sapma, FEA σ, tahmin, sapma, durum: uzay dışı / u/L).",
        card: "GET /surrogate/validate",
      },
      {
        name: "Öğrenilen üsler",
        what:
          "Log-log ve hibritte u ∝ Π xᵢ^aᵢ katsayıları. Sabit ya da eşdoğrusal sütunun katsayısı üs olarak okunamaz — " +
          "tahmin bundan zarar görmez, yorum görür.",
      },
    ],
  },
  {
    id: "ml-dur-tahmin",
    title: "Durability · 5 — Tahmin",
    intro:
      "Parametreden tahmin, ccx yok. Soldaki satırlarda bant = eğitim kutusu (tahmin sonrası, uzay dışı girdide), ■ = girilen değer.",
    items: [
      { name: "Parametre satırları + Fy", what: "Şablon parametreleri ve kuvvet. Satır altında “eğitim kutusunda” ya da “eğitim a – b · k× altında/üstünde”." },
      { name: "Malzeme", what: "Akma kontrolü için; “yok” seçilirse akma kontrolü atlanır." },
      { name: "Model (RF / loglinear / hybrid)", what: "Aktif modeli seçer; bu şablonda eğitilmemiş türün ipucu “bu şablonda eğitilmedi” der." },
      {
        name: "Gerilme kaynağı · auto / maskeli / ham tepe",
        what: "Maskeli: kısıttan 1×T uzakta (tekillik dışarıda). Ham tepe: mesh'teki en yüksek değer, tekillik dahil.",
      },
      { name: "Diğer yük bileşenleri, isteğe bağlı geometri, malzeme sabitleri, mesh", what: "Fx, Fz, E, ν, eleman boyutu ve isteğe bağlı şablon alanları." },
      { name: "Run #N ile karşılaştır", what: "Açık run varsa tahminin yanına FEA kıyası kartı: FEA u_max, Sapma u, FEA VM_max, Sapma VM." },
      { name: "Tahmin et", what: "Sonuç: model türü · uzay içi / uzay dışı; u_max, σ_max.", card: "POST /surrogate/predict/params" },
      {
        name: "Akma kartı",
        what: "Kullanım oranı (σ / akma) ve durum: elastik bölgede / limit aşılmadı ama sınırda / akma aşılıyor — malzeme plastik, tahmin geçersiz.",
      },
      {
        name: "Uzay dışı listesi",
        what:
          "Her ihlal: girdi = değer · alt sınırın altında / üst sınırın üstünde · eğitim aralığı · k×. “X'yi sınıra çek” " +
          "düğmesi değeri eğitim sınırına taşır (isteğe bağlı).",
      },
      {
        name: "Toplu tarama",
        what:
          "Bir parametre seçilir (geometri, Fy/Fx/Fz, eleman), Min / Max / adım sayısı (2–200) → “Tara”. σ_max eğrisi, akma " +
          "çizgisi, uzay dışı noktalar ve nokta tablosu. Taranmayan girdiler soldaki formdan alınır.",
        card: "POST /surrogate/predict/sweep",
      },
    ],
  },
  {
    id: "ml-crash-doe",
    title: "Crash · 1 — DOE",
    intro:
      "Taban senaryo sabit, taranan alanlar LHS [alt, üst]. Taban bir /crash/scenario gövdesidir (JSON); taranan alan bu gövdenin " +
      "noktalı yoludur. Hangi alanın hangi aralıkta taranacağı mühendisindir; yol listesi yalnız yazım kolaylığı.",
    items: [
      { name: "Şablon çipleri", what: "Crash şablonları (crash_box, plate_ball, drop …). Değiştirince taban JSON'daki geometry silinir, template_id yazılır." },
      {
        name: "Taranan alanlar · yol / alt / üst",
        what:
          "Örnek yollar: speed_m_s, angle_deg, t_end_ms, thickness_mm, element_size_mm, drop_height_mm, ball_total_mass_kg, " +
          "end_mass_kg, model.sigma_y_pa, model.harden_b_mpa, model.harden_n, geometry.<şablon parametresi>, " +
          "rigid_bodies.0.mass_kg (liste elemanı indeksle). “+ alan ekle”, “×” siler. Üst > alt olmalı.",
      },
      {
        name: "Taban senaryo (JSON)",
        what:
          "Boş alanlar senaryo varsayılanı. Kutunun durması için t_end_ms yeterli olmalı; aksi halde ezilme hedefi boş kalır.",
      },
      { name: "Ad / Örnek / Tohum", what: "Örnek 1–500 tam sayı. Şablon doğrulamasına takılan örnek yeniden çekilir; geçerli örnek azsa mesaj “k/N geçerli örnek” der." },
      { name: "DOE başlat", what: "Örnekler sırayla /crash/scenario ile koşar; patlayan örnek diğerlerini durdurmaz.", card: "POST /crash/doe/studies" },
      { name: "Çalışma çipleri", what: "Son 8 çalışma, ● çalışıyor. Çalışan çalışma varken liste 5 s'de bir yenilenir." },
      {
        name: "İlerleme",
        what: "Durum, ilerleme çubuğu (biten / hata), Şablon, Tohum, Biten k/N, Hata; örnek tablosu: # · taranan değerler · durum · koşu · mesaj.",
      },
      {
        name: "Devam ettir (n)",
        what: "Yarıda kalan çalışmayı sürdürür; bitmiş (solved / rad_only) örnek tekrar koşulmaz.",
        card: "POST /crash/doe/studies/{id}/run",
      },
    ],
  },
  {
    id: "ml-crash-model",
    title: "Crash · 2 — Model",
    intro:
      "Korpus özeti + eğitim + K-fold CV metrikleri. Kabul eşiği yok, sayılar gösterilir. Hedefler (kg–mm–ms; kN, J, mm): " +
      "Tepe duvar kuvveti = max |F_rwall|; Ortalama duvar kuvveti = temas penceresinde (F > %5 tepe) zaman ortalaması; " +
      "Yutulan enerji = iç enerji son değeri; Ezilme mesafesi = ∫ v dt, v = v0 − I_rwall/m, hız sıfıra inene kadar (koşu sonunda hız > 0 ise boş).",
    items: [
      { name: "Şablon / Senaryo", what: "Senaryo rigid_wall ya da plate_ball; şablon seçilince kendiliğinden ayarlanır." },
      {
        name: "Kaynak",
        what:
          "“Tüm çözülmüş koşular (elle dahil)” ya da tek DOE çalışması (“DOE #id · ad · N örnek”). Tek çalışma seçilirse elle " +
          "yapılmış dağınık denemeler eğitime karışmaz. Dışlanan koşular hiçbir zaman girmez.",
      },
      {
        name: "Korpus özeti",
        what:
          "Koşu, Değişen girdi, Sabit (tüm koşularda aynı, modele girmez), düşen satırlar (other_template / other_scenario / " +
          "no_target), girdi adları (geom.<ad>, req.<yol>) ve hedef başına dolu satır (k/N).",
        card: "POST /crash/ml/corpus",
      },
      {
        name: "Eğit · 5-fold CV",
        what:
          "Hedef başına Random Forest (200 ağaç); hedef kendi dolu satırlarıyla eğitilir, en az 8 dolu satır. Eksik değerli " +
          "girdi sütunu modele alınmaz, sayısı listelenir.",
        card: "POST /crash/ml/train",
      },
      {
        name: "CV metrikleri tablosu",
        what:
          "hedef · birim · n · R² · MAE · MAPE · fold. Başlıkta şablon / senaryo · kaynak · koşu sayısı; kayıtlı model seçili " +
          "kaynaktan farklıysa “seçili kaynaktan farklı”. Model dosyası uploads/models/crash/<şablon>/<senaryo>.joblib.",
        card: "GET /crash/ml/models",
      },
    ],
  },
  {
    id: "ml-crash-tahmin",
    title: "Crash · 3 — Tahmin",
    intro:
      "Kayıtlı model seçilir; modelin girdi sütunları için form açılır (başlangıç = eğitim aralığının ortası, aralık yanında). " +
      "Aralık dışı girdi engellenmez, listelenir.",
    items: [
      { name: "Model", what: "şablon / senaryo · kaynak · koşu sayısı." },
      { name: "girdi / değer / eğitim aralığı", what: "Aralık dışındaki satır tahmin sonrası işaretlenir." },
      { name: "Tahmin et", what: "Hedef karoları: değer + birim, altında “± CV MAE · R²”; eğitilmemiş hedefte gerekçe.", card: "POST /crash/ml/predict" },
      { name: "Aralık ortası", what: "Tüm girdileri eğitim aralıklarının ortasına döndürür." },
      { name: "Eğitim aralığı dışında: …", what: "Aralık dışındaki girdi adlarının listesi (out_of_domain)." },
    ],
  },
  {
    id: "ml-crash-dogrulama",
    title: "Crash · 4 — Doğrulama",
    intro:
      "Crash validasyon raporu (V1–V18): her vakada simülasyon / analitik ya da literatür referansı oranı, enerji dengesi ve " +
      "HG/IE. Vekil modelin değil, modeli besleyen FEA'nın doğrulamasıdır. Eşikleri mühendis girer; araç yalnız eşiğe göre işaretler.",
    items: [
      { name: "Özet tablo", what: "vaka · koşu · oran (en küçük – en büyük) · denge · HG/IE · eşik (girilmemişse —)." },
      {
        name: "Kabul eşikleri (mühendis)",
        what: "Boş = kontrol yok; vaka satırındaki boş alan varsayılanı kullanır; oran ve denge kesir (0.05 = %5). “Eşikleri kaydet”.",
      },
      { name: "Vaka ayrıntısı", what: "büyüklük · sim · referans · oran; mesh serilerinde eleman mm · δ · Pm · /W&A · /A&J · HG/IE · süre." },
      {
        name: "V3 — kızaklı eksenel ezilme",
        what:
          "Crash box DOE'nin dayandığı vaka: 5 → 2.5 mm elemanda Pm 59.5 → 56.0 kN; Wierzbicki–Abramowicz (48.73 kN) oranı " +
          "1.22 → 1.15, Abramowicz–Jones (66.57 kN) oranı 0.89 → 0.84; enerji dengesi ≤ %0.18.",
        card: "docs/validation/crash_validation.md",
      },
    ],
  },
  {
    id: "ml-ornekler",
    title: "Örnekler",
    intro:
      "Repodaki gerçek çalışmalardan sayılar (ML_EXAMPLES). Her kart: kurulum, girdiler, hedefler, sonuçlar ve verinin " +
      "gösterdiği ders. Durability metrikleri holdout (test), crash metrikleri 5-fold CV'dir.",
  },
  {
    id: "ml-yorum",
    title: "Sık hatalar / yorumlama",
    intro: "Ölçülmüş verinin ne gösterdiği. Öneri değil — ekrandaki sayıyı okurken akılda tutulacak bağlam.",
    items: [
      {
        name: "Ortalama kuvvet R² diğer hedeflerden düşük",
        what:
          "Crash box DOE #3'te mean force CV R² 0.831 (diğerleri 0.91–0.98). Ezilmesi < 20 mm olan 28 koşuda CV MAPE %10.4, " +
          "40 mm üstündeki 54 koşuda %6.6. Kısa ezilmede temas penceresi ilk katlanma tepesinin ağırlığını taşır; " +
          "W–A teorisine oran da < 20 mm'de 1.35, > 40 mm'de 1.20.",
      },
      {
        name: "Yutulan enerji ≈ ½mv²",
        what:
          "Kızak duruyorsa enerji neredeyse tamamen kinetik enerjiden gelir: DOE #3'te E / ½(m_kızak + m_kutu)v² = 0.93–0.98. " +
          "R² 0.981 büyük ölçüde bu ilişkiden; RF önem katsayısı hız 0.89, kütle 0.10, et kalınlığı 0.006.",
      },
      {
        name: "Ezilme boş kalıyor",
        what:
          "Koşu bitiminde kızak hâlâ hareket ediyorsa (t_end_ms kısa) crush_mm tanım gereği boştur; korpus o satırı o hedef için " +
          "atlar, n azalır.",
      },
      {
        name: "Aynı büyüklük iki girdi sütununda",
        what:
          "Kayıtlı crash box modelinde geom.wall ile req.parts.0.thickness_mm aynı değeri, req.barrier.wall.point.2 ise " +
          "geom.box_width / 2 değerini taşır (6 girdi, 4 bağımsız). Tahmin formunda bunlar tutarsız girilirse korpusta hiç " +
          "olmayan bir kombinasyon sorulmuş olur; aralık denetimi bunu yakalamaz (her sütun kendi aralığında kalabilir).",
      },
      {
        name: "RF aralık dışında sessizce sabitlenir",
        what:
          "Ölçülen: eğitim aralığı dışındaki bir kirişte gerçek sehim 2976 mm iken RF 109 mm verdi (%96 hata, uyarısız). " +
          "Bu yüzden uzay dışı işareti var; tahmin yine de üretilir.",
      },
      {
        name: "Eğitim R² yüksek, test düşük",
        what:
          "NLGEOM kiriş RF'sinde eğitim R²(u) 0.941, holdout R²(u) 0.626. Kart test metriğini gösterir; eğitim metriği " +
          "modelin veriyi ezberleyip ezberlemediğini söylemez.",
      },
      {
        name: "Holdout yok",
        what:
          "12 örneğin altındaki korpusta test ayrılmaz; metrik yalnız eğitimdir. Örnek: şu an kayıtlı lineer kiriş RF modeli 8 " +
          "run'lık “kiris” setiyle eğitilmiş (R²(u) ≈ 0, σ MAPE %0 — 8 run'ın hepsi aynı tasarım).",
      },
      {
        name: "Ham tepe gerilme mesh'le büyür",
        what:
          "Ankastre köşedeki tepe von Mises tekildir; mesh yakınsama çalışmasında (kiriş 8 basamak) tepe %5.6 gürültü / +%10 " +
          "sapma, maskeli (max_von_mises_away) %1.2 / −%0.8. Ham tepeyle eğitilen model mesh'i de öğrenir.",
      },
      {
        name: "Sabit sütunun üssü okunamaz",
        what:
          "Tek malzemeli korpusta E ve ν sabittir; üs ekranında “korpus boyunca sabit” görünür. Başka malzemeye genelleme " +
          "veriden gelmez.",
      },
      {
        name: "Doğrulama tablosu ≠ bağımsız test",
        what:
          "“Tahmin ↔ FEA” son N çözülmüş run'ı kullanır; bunlar modelin eğitim setinde olabilir. “yalnız <korpus>” işaretliyken " +
          "satırlar doğrudan eğitim korpusudur.",
      },
    ],
  },
];

export const ML_EXAMPLES: MlExample[] = [
  {
    id: "crash-box-doe3",
    title: "Crash box eksenel ezilme — 150 koşu, RF + 5-fold CV",
    domain: "crash",
    setup:
      "DOE #3, şablon crash_box_shell, senaryo rigid_wall, LHS 150 örnek, 150/150 çözüldü (düşen satır yok). S235 " +
      "(σ0 235 MPa, ρ 7850), kutu boyu 300 mm, yükseklik 50 mm, eleman 5 mm, t_end 30 ms. Model " +
      "uploads/models/crash/crash_box_shell/rigid_wall.joblib.",
    inputs: [
      "speed_m_s 6–12 m/s",
      "geometry.wall (et kalınlığı) 2–3 mm",
      "rigid_bodies.0.mass_kg (kızak) 30–50 kg",
      "geometry.box_width 40–60 mm",
    ],
    targets: [
      "peak_force_kn — 85.7–156.0 kN (ort. 117.9)",
      "mean_force_kn — 28.7–84.1 kN (ort. 47.2)",
      "energy_absorbed_j — 599–3294 J (ort. 1657)",
      "crush_mm — 5.7–90.8 mm (ort. 34.9)",
    ],
    results: [
      "Yutulan enerji: R² 0.981 · MAE 73.1 J · MAPE %4.9",
      "Tepe kuvvet: R² 0.953 · MAE 2.46 kN · MAPE %2.1 (önem: et kalınlığı 0.78, genişlik 0.18)",
      "Ezilme: R² 0.909 · MAE 3.65 mm · MAPE %11.7 (önem: hız 0.76, et kalınlığı 0.15)",
      "Ortalama kuvvet: R² 0.831 · MAE 3.59 kN · MAPE %7.5 (önem: et kalınlığı 0.78, hız 0.14)",
      "FEA ortalama kuvvet / Wierzbicki–Abramowicz: ort. 1.24 (0.98–1.88); ezilme > 40 mm'de 1.20, < 20 mm'de 1.35",
      "SEA 0.46–3.34 J/g",
    ],
    lesson:
      "Enerji ve tepe kuvvet tek bir baskın girdiyle açıklanıyor (enerji ≈ ½mv², tepe ≈ et kalınlığı); ortalama kuvvet ve " +
      "ezilme kısa ezilmeli koşularda ilk katlanma tepesinden etkileniyor, metrikleri buna göre daha düşük. Kayıtlı modelde " +
      "6 girdi sütunu var, ikisi türetilmiş (thickness_mm = wall, wall.point.2 = width/2).",
  },
  {
    id: "kiris-lineer-v2",
    title: "Ankastre kiriş, lineer — korpus kiris-v2 (192 run)",
    domain: "durability",
    setup:
      "DOE study 3 (200 örnek) → süzgeç sonrası 192 run, donmuş korpus kiris-v2. Holdout %25: 144 eğitim / " +
      "48 test, tohum 2026. Çelik, E 210 GPa, ν 0.3 (sabit sütun).",
    inputs: [
      "length 401–699 mm",
      "thickness 10.0–16.0 mm",
      "width 40.1–69.9 mm",
      "element_size 5.2–12.4 mm",
      "load_fy −219 … −40.5 N",
    ],
    targets: ["max_displacement", "max_von_mises", "max_von_mises_away", "max_von_mises_near_peak"],
    results: [
      "Log-log lineer test: u R² 1.0000 · MAPE %0.19; σ (ham tepe) MAPE %1.75; σ maskeli MAPE %0.66",
      "Hibrit test: u MAPE %0.20; σ ham tepe %1.74; σ maskeli %0.65",
      "Öğrenilen üsler (u): L 2.991, T −2.988, W −1.007 (teori 3, −3, −1)",
      "RF (aynı 200 örneklik korpus, 150/50 ayrımı, model docstring kaydı): test R²(u) 0.895, MAPE %18.87",
      "Şu an diskteki lineer RF dosyası 8 run'lık “kiris” setiyle yeniden eğitilmiş (holdout yok) — 192 run'lık RF metriği dosyada değil",
    ],
    lesson:
      "Hedef çarpımsal güç yasası olduğunda log-log model teorik üsleri veriden buluyor ve RF'den iki mertebe isabetli; " +
      "RF parçalı-sabit olduğu için aynı veride %19 hata veriyor.",
  },
  {
    id: "kiris-nlgeom-v1",
    title: "Ankastre kiriş, NLGEOM — korpus kiris-nlgeom-v1 (150 run)",
    domain: "durability",
    setup:
      "Study 6, 150 run, donmuş korpus kiris-nlgeom-v1 (2026-09-27). Holdout 112 eğitim / 38 test, tohum 2026. " +
      "Alüminyum E 68.9 GPa, ν 0.33 (sabit). Lineer modelden ayrı klasör: uploads/models/cantilever_beam/nlgeom/.",
    inputs: [
      "length 902–1199 mm",
      "thickness 4.0–6.5 mm",
      "width 25.4–49.8 mm",
      "element_size 3.1–6.3 mm",
      "load_fy −61.4 … −5.3 N",
    ],
    targets: ["max_displacement", "max_von_mises", "max_von_mises_away", "max_von_mises_near_peak"],
    results: [
      "Hibrit test: u R² 0.9996 · MAPE %0.49; σ ham tepe MAPE %2.20; σ maskeli MAPE %0.77",
      "Log-log test: u MAPE %0.47; σ ham tepe %2.22; σ maskeli %0.68",
      "RF test: u R² 0.626 · MAPE %19.4; σ MAPE %10.6 (eğitim R²(u) 0.941)",
      "Öğrenilen üsler (u): L 2.874, T −2.810, W −0.945 — lineer teoriden (3, −3, −1) sapma büyük deformasyonun etkisi",
    ],
    lesson:
      "Büyük deformasyonda ilişki saf güç yasası değil, yine de log-log %0.5 içinde kalıyor; üslerin teoriden ayrılması " +
      "NLGEOM'un sertleştirici etkisini veriden gösteriyor.",
  },
  {
    id: "plaka-v1",
    title: "Delikli plaka çekme — korpus plaka-v1 (198 run)",
    domain: "durability",
    setup: "Study 5, 198 run, holdout 148 / 50, tohum 2026. Çelik E 210 GPa, ν 0.3 (sabit).",
    inputs: [
      "height 150–300 mm",
      "width 70.8–139.5 mm",
      "thickness 4.0–12.0 mm",
      "diameter 12.1–39.9 mm",
      "element_size 1.8–9.2 mm",
      "load_fx 5.1–59.7 kN",
    ],
    targets: ["max_displacement", "max_von_mises", "max_von_mises_away", "max_von_mises_near_peak"],
    results: [
      "Hibrit test: u MAPE %0.29; σ MAPE %1.30; near_peak MAPE %7.78",
      "Log-log test: u MAPE %1.53; σ MAPE %2.22",
      "RF test: u MAPE %19.6; σ MAPE %16.1",
    ],
    lesson:
      "Gerilme yığılma katsayısı delik çapı / genişlik oranına güç yasası dışında bağlı; log-log tek başına %2.2'de kalıyor, " +
      "artığına RF eklenen hibrit %1.3'e iniyor. Plakada delik kenarı tekil değil, ham tepe ile maskeli aynı çıkıyor.",
  },
  {
    id: "kiris-ood",
    title: "Aralık dışı sorgu — RF'nin sessiz hatası",
    domain: "durability",
    setup: "Ankastre kiriş RF modeli, eğitim aralığının dışında bir tasarım (ROADMAP 0.5.8 ölçümü).",
    inputs: ["Eğitim kutusunun dışında geometri / yük"],
    targets: ["max_displacement"],
    results: ["FEA 2976 mm, RF tahmini 109 mm — %96 hata, model uyarı vermedi"],
    lesson:
      "Ağaç modelleri aralık dışında sabit değer döndürür. Bu ölçüm “uzay dışı” işaretinin ve ihlal listesinin (hangi girdi, " +
      "kaç kat) gerekçesidir; tahmin engellenmez, mühendis görür.",
  },
  {
    id: "kiris-yakinsama",
    title: "Mesh yakınsaması — tepe ve maskeli gerilme",
    domain: "durability",
    setup: "Yakınsama aşaması: kiriş 8 basamak, plaka 5 basamak, sabit geometri (ROADMAP 0.6.2).",
    inputs: ["Eleman boyutu (oran × karakteristik uzunluk)"],
    targets: ["max_von_mises", "max_von_mises_away"],
    results: [
      "Kiriş tepe von Mises: %5.6 gürültü, +%10 sapma (yakınsamıyor — ankastre köşe tekil)",
      "Kiriş maskeli von Mises: %1.2 gürültü, −%0.8 sapma (yakınsıyor)",
      "Plaka: ham tepe zaten yakınsıyor (delik kenarı tekil değil)",
    ],
    lesson:
      "Eleman boyutu DOE girdisi olduğundan, yakınsamayan hedefle toplanan veri modele ayrıklaştırma hatasını fizik diye " +
      "öğretir. Kirişte maskeli hedefin hibrit MAPE'si %0.6–0.8.",
  },
];
