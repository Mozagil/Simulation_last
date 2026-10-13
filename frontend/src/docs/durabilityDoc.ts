/**
 * Durability (CalculiX — statik + modal) kullanıcı belgesi. Crash belgesiyle
 * (`crashDoc.ts`) aynı biçim: her özellik / düğme / kart için ne yapar, tipik
 * kullanım ve yazılan CalculiX kartı. Kart adları yalnız
 * `backend/app/solvers/calculix.py`'nin gerçekten yazdığı anahtar kelimeler.
 * Görseller sonra eklenecek (`public/docs/durability/`); her bölümün üstündeki
 * `// görsel:` yorumu alınacak ekran görüntüsünü tarif eder.
 *
 * Araç mühendise karar vermez: "Ne zaman" satırları tipik kullanımı
 * anlatır, değer önermez.
 */

import type { DocSection } from "./crashDoc";

export interface DurabilityTemplateDoc {
  id: string;
  title: string;
  /** Şablon grubu (backend `tags`): grup1 … grup4. */
  group: string;
  models: string;
  /** Şablonla gelen bölgeler (Physical Group adları). */
  regions: string[];
  /** Şablonla BC listesine yüklenen varsayılan sınır koşulları. */
  defaultBcs: string;
  /** Analitik referans (Sonuç panelinde "Analitik referans" tablosu). */
  reference: string;
}

export const DURABILITY_TEMPLATES: DurabilityTemplateDoc[] = [
  {
    id: "cantilever_beam",
    title: "Ankastre kiriş (dikdörtgen kesit)",
    group: "grup1",
    models: "Bir ucu ankastre, serbest ucundan tekil yükle eğilen dikdörtgen kesitli kiriş (L 500 · T 10 · W 50 mm). İsteğe bağlı kök filleti (r > 0 → duvar bloğu + fillet).",
    regions: ["ankastre_uc", "yuk_yuzeyi"],
    defaultBcs: "Fixed → ankastre_uc · Nokta/yüzey yük Fy = −500 N → yuk_yuzeyi",
    reference: "Euler–Bernoulli: δ = F·L³/(3·E·I), σ = F·L·(T/2)/I, I = W·T³/12. Varsayılanla 23,81 mm / 300 MPa.",
  },
  {
    id: "simply_supported_beam",
    title: "Basit mesnetli kiriş (dikdörtgen kesit)",
    group: "grup1",
    models: "İki ucu mesnetli kiriş, açıklık ortası üst kenarına tekil yük.",
    regions: ["mesnet_sol", "mesnet_sag", "yuk_orta", "yuk_yayili"],
    defaultBcs: "Displacement Ux=Uy=Uz=0 → mesnet_sol · Displacement Uy=Uz=0 → mesnet_sag · yük Fy = −500 N → yuk_orta (kenar)",
    reference: "δ = F·L³/(48·E·I), σ = (F·L/4)·(T/2)/I.",
  },
  {
    id: "plate_with_hole",
    title: "Delikli plaka (çekme)",
    group: "grup1",
    models: "Merkezi dairesel delikli dikdörtgen plaka, x yönünde çekme.",
    regions: ["tutulan_uc", "yuk_cekme", "delik_cidari"],
    defaultBcs: "Fixed → tutulan_uc · Fx = 50 000 N → yuk_cekme",
    reference: "Kirsch Kt = 3 (sonsuz plaka); sonlu genişlikte Heywood net Kt.",
  },
  {
    id: "dogbone",
    title: "Çekme numunesi (dogbone)",
    group: "grup1",
    models: "ISO 6892 / ASTM E8 oranlı sac çekme numunesi.",
    regions: ["tutulan_uc", "yuk_cekme", "olcu_alani"],
    defaultBcs: "Fixed → tutulan_uc · Fx = 7500 N → yuk_cekme",
    reference: "Nominal ölçü gerilmesi σ = F/(b·t).",
  },
  {
    id: "thick_walled_tube",
    title: "Kalın cidarlı boru (iç basınç)",
    group: "grup1",
    models: "Açık uçlu kalın cidarlı silindir, iç basınç.",
    regions: ["tutulan_uc", "ic_cidar", "dis_cidar"],
    defaultBcs: "Fixed → tutulan_uc · Pressure 10 → ic_cidar",
    reference: "Lamé: iç cidarda en büyük çevresel gerilme ve von Mises.",
  },
  {
    id: "torsion_shaft",
    title: "Burulma mili (dairesel kesit)",
    group: "grup1",
    models: "Bir ucu ankastre dairesel mil; serbest uç dış çemberine teğetsel yük.",
    regions: ["ankastre_uc", "yuk_burulma"],
    defaultBcs: "Fixed → ankastre_uc · Fz = 500 N → yuk_burulma",
    reference: "T = F·R, τ = T·R/J, von Mises = √3·τ.",
  },
  {
    id: "i_beam",
    title: "I-kesit kiriş (ankastre)",
    group: "grup2",
    models: "I-profil ankastre kiriş, uçtan −y yük.",
    regions: ["ankastre_uc", "yuk_yuzeyi"],
    defaultBcs: "Fixed → ankastre_uc · Fy = −2000 N → yuk_yuzeyi",
    reference: "Euler–Bernoulli, I = (b·h³ − (b−tw)·(h−2tf)³)/12.",
  },
  {
    id: "box_tube",
    title: "Kutu profil (ankastre)",
    group: "grup2",
    models: "Dikdörtgen içi boş profil, ankastre, uç yükü.",
    regions: ["ankastre_uc", "yuk_yuzeyi"],
    defaultBcs: "Fixed → ankastre_uc · Fy = −1000 N → yuk_yuzeyi",
    reference: "I = (b·h³ − bi·hi³)/12.",
  },
  {
    id: "circular_tube",
    title: "Dairesel tüp (ankastre eğilme)",
    group: "grup2",
    models: "İçi boş dairesel boru, ankastre, uç yükü −y.",
    regions: ["ankastre_uc", "yuk_yuzeyi"],
    defaultBcs: "Fixed → ankastre_uc · Fy = −1000 N → yuk_yuzeyi",
    reference: "I = π/4·(R⁴ − r⁴).",
  },
  {
    id: "l_angle",
    title: "L-köşebent (ankastre)",
    group: "grup2",
    models: "Eşit bacaklı L profil, ankastre, uç yükü −y.",
    regions: ["ankastre_uc", "yuk_yuzeyi"],
    defaultBcs: "Fixed → ankastre_uc · Fy = −500 N → yuk_yuzeyi",
    reference: "I ve c kesit ağırlık merkezine göre.",
  },
  {
    id: "notched_bar",
    title: "Çentikli çubuk (U / V, çekme)",
    group: "grup4",
    models: "Dikdörtgen çubuk, orta açıklıkta karşılıklı U veya V çentik, çekme.",
    regions: ["tutulan_uc", "yuk_cekme", "centik_civari"],
    defaultBcs: "Fixed → tutulan_uc · Fx = 32 000 N → yuk_cekme",
    reference: "σ_max = Kt·F/((W−2a)·T), Kt (Neuber) = 1 + 2√(a/r).",
  },
  {
    id: "keyway_shaft",
    title: "Kama kanallı mil (burulma)",
    group: "grup4",
    models: "Dairesel mil, orta boyda dikdörtgen kama yuvası, burulma.",
    regions: ["ankastre_uc", "yuk_burulma", "kama_yuvasi"],
    defaultBcs: "Fixed → ankastre_uc · Fz = 500 N → yuk_burulma",
    reference: "τ_max = Kt·T·R/J, von Mises = √3·τ_max.",
  },
  {
    id: "t_bracket",
    title: "T-braket (kaburgalı / kaburgasız)",
    group: "grup3",
    models: "Duvara bağlı sırt plakası + konsol raf; isteğe bağlı üçgen kaburga.",
    regions: ["duvar_yuzu", "raf_ucu"],
    defaultBcs: "Fixed → duvar_yuzu · Fy = −500 N → raf_ucu",
    reference: "Kaburgasız raf için kiriş teorisi.",
  },
  {
    id: "l_bracket_bolted",
    title: "L-braket (cıvata delikli)",
    group: "grup3",
    models: "Dik bacağı iki cıvata deliğinden tutulan L-braket; yatay bacak ucundan −y yük.",
    regions: ["civata_delikleri", "bacak_ucu"],
    defaultBcs: "Fixed → civata_delikleri · Fy = −500 N → bacak_ucu",
    reference: "Yatay bacak için kiriş teorisi.",
  },
  {
    id: "flange",
    title: "Flanş (cıvata delikli)",
    group: "grup3",
    models: "Halka plaka, n cıvata deliği tutulu, boru deliği yüzeyinden eksenel çekme.",
    regions: ["civata_delikleri", "boru_delik_yuzeyi"],
    defaultBcs: "Fixed → civata_delikleri · Fx = 5000 N → boru_delik_yuzeyi",
    reference: "Kapalı form referans yok.",
  },
  {
    id: "stepped_shaft",
    title: "Kademeli mil (omuz filleti)",
    group: "grup3",
    models: "İki çaplı mil, omuzda fillet; büyük uç ankastre, küçük uçtan −y yük.",
    regions: ["ankastre_uc", "yuk_yuzeyi"],
    defaultBcs: "Fixed → ankastre_uc · Fy = −500 N → yuk_yuzeyi",
    reference: "Omuz gerilmesi Kt (Peterson/Norton), uç sehimi Castigliano.",
  },
];

export const DURABILITY_DOC: DocSection[] = [
  // görsel: Durability sekmesi açık, ankastre kiriş çözülmüş — sol ağaç, üst adım şeridi (1 · GEOMETRY … 6 · RESULTS), ortada von Mises konturu, altta metrik kartlar ve Analiz geçmişi.
  {
    id: "akis",
    title: "Genel akış",
    intro:
      "Durability (statik) analiz altı adımda kurulur: 1 · GEOMETRY → 2 · MESH → 3 · MATERIAL → 4 · BOUNDARY CONDITIONS → 6 · RESULTS. " +
      "Modal analiz için sol raydan MODAL seçilir; 4 · BOUNDARY CONDITIONS yerine 5 · MODAL adımı görünür. " +
      "Solver CalculiX (implicit) sunucuda koşar; kullanıcı tarafında hiçbir CAE yazılımı gerekmez. Birim sistemi mm · N · MPa (alt durum çubuğunda “birim mm”).",
    items: [
      { name: "ANALİZ TİPİ · DURABILITY", what: "CalculiX statik çözüm (*STATIC). Adımlar 1–4 ve 6.", card: "*STATIC" },
      { name: "ANALİZ TİPİ · MODAL", what: "CalculiX doğal frekans çözümü (*FREQUENCY). Aynı geometri, mesh, malzeme ve mesnetleri kullanır.", card: "*FREQUENCY" },
      { name: "1 · GEOMETRY", what: "STEP/IGES yükle ya da şablondan parametrik geometri üret; onarım (HEAL), fillet kaldırma, orta yüzey (MİD), yüzey kopyala, offset ve bölge (Physical Group) araçları." },
      { name: "2 · MESH", what: "2D shell (kabuk) ya da 3D solid; tet / quad / mix; eleman boyutu, yüzey başına yerel boyut, kenar düğüm sayısı; kalite raporu ve mesh araçları." },
      { name: "3 · MATERIAL", what: "Kütüphane malzemesi (E, ν, ρ, Rp0.2, Rm, A, S-N), parçaya atama, özel malzeme, component / kabuk kalınlığı, ürün ağacı." },
      { name: "4 · BOUNDARY CONDITIONS", what: "Sekiz BC türü (Fixed, Nokta/yüzey yük, Pressure, Displacement, Sliding, Bearing, Gravity, Rigid body), BC listesi ve çözüm seçenekleri (NLGEOM, Plastisite). “.inp üret / çöz” düğmesi." },
      { name: "5 · MODAL", what: "Yalnız MODAL sekmesinde: mesnet, mod sayısı, frekans bandı, “Modal çöz”, mod şekli kartları ve animasyon." },
      { name: "6 · RESULTS", what: "Çözüm mesajı, .inp indirme, analitik referans tablosu, von Mises ve deplasman istatistikleri/histogramları. 3B kontur, renk skalası ve deformasyon ölçeği görünümün üzerindeki yüzen panellerde." },
      { name: "‹ Geri / İleri ›", what: "Sağ panelin altında; adımlar arasında sırayla geçer." },
    ],
  },
  // görsel: Üst şerit — seçim modu düğmeleri (Parça/Yüzey/Kenar/Nokta, Mesh eleman/Mesh düğüm), görünüm araç çubuğu (geri al, yakınlaştır, mesh göster, tel kafes, solid/surface gizle, kalite) ve “🔄 Yeni Case Başlat”.
  {
    id: "ust",
    title: "Seçim ve görünüm araçları",
    intro:
      "Viewport'taki tüm seçimler (BC, malzeme, bölge, yerel mesh boyutu) bu modlarla yapılır. CAD seçimi ile mesh seçimi karşılıklı dışlayıcıdır.",
    items: [
      { name: "Parça / Yüzey / Kenar / Nokta", what: "CAD seçim modu. Tıklanan varlık seçilir, Ctrl ile çoklu. Durum çubuğu seçimi özetler." },
      { name: "Mesh eleman / Mesh düğüm", what: "Mesh üzerinde seçim. Eleman: tıklanan elemanın CAD yüzeyi seçilir. Düğüm: ham mesh düğüm numaraları (yalnız o mesh için geçerli; mesh yeniden üretilince anlamını yitirir)." },
      { name: "Mesh seçim · Face / Attached", what: "Mesh elemanına tıklandıktan sonra çıkan çubuk. Face = elemanın ait olduğu tüm yüzey; Attached = bağlı tüm parça." },
      { name: "2. mertebe düğüm göster", what: "C3D10 kenar-ortası düğümlerini gösterir/gizler. 1. mertebe veya 2D mesh'te pasif." },
      { name: "Geri al", what: "Son geometri işlemini (kopya / heal / midsurface …) geri alır. Tek seviyeli." },
      { name: "Yakınlaştır / Uzaklaştır / Görünümü sığdır", what: "Kamera kontrolleri." },
      { name: "Mesh göster / Mesh tel kafes", what: "Mesh önizlemesini açar/kapar; tel kafes yalnız kenarları çizer." },
      { name: "Solid / Surface göster–gizle", what: "Seçili parçanın katısını veya seçili yüzeyleri gizler/gösterir." },
      { name: "Mesh kalite hesapla (grafik simgesi)", what: "2 · MESH'teki “Kalite” ile aynı." },
      { name: "🔄 Yeni Case Başlat", what: "Çalışma alanını sıfırlar. Önceki analiz Analiz geçmişi'nde kalır; Sil ile kaldırılır." },
      { name: "Model ağacı", what: "Sol üstte: Geometri (yüzey sayısı), Bölgeler (ad + varlık sayısı), Component'ler (Parça #n → atanan malzeme ya da “atama yok”), Mesh (şema · boyut). Parça satırına tıklamak o parçayı seçer. Alt kenarından sürüklenerek boyutlanır." },
    ],
  },
  // görsel: GEOMETRİ YÜKLE alanı + sağda “Şablondan üret” paneli (şema görseli, Şablon listesi, parametre alanları, Model üret) ve açılan Kısıtlar/Yük penceresi.
  {
    id: "geometri",
    title: "1 · Geometry",
    image: "/docs/durability/02-geometri.jpg",
    imageCaption: "Şablondan üret → Ankastre kiriş: şema, parametreler ve kısıt/yük önizleme penceresi.",
    intro:
      "Geometri ya dosyadan (STEP/IGES) yüklenir ya da parametrik şablondan üretilir. Şablon, bölgeleri (Physical Group) ve varsayılan sınır koşullarını da getirir; BC listesi bunlarla doldurulur ve serbestçe düzenlenir.",
    items: [
      { name: "GEOMETRİ YÜKLE · Dosya seç", what: "Dosyayı bırak ya da seç. Gmsh (OpenCASCADE) ile içe alınır, parça/yüzey/kenar/nokta numaralanır." },
      { name: "Şablondan üret · Şablon", what: "Dosya yüklemeden parametrik geometri. Liste yalnız durability şablonlarını gösterir (bkz. Şablonlar). Seçince şema görseli ve parametre alanları (sembol + birim) gelir." },
      { name: "Model üret → Modeli üret", what: "Açılan pencerede şablonun Kısıtlar'ı listelenir, Yük alanları (Fx/Fy/Fz N, Basınç MPa, Yatak kuvveti N, gx/gy/gz mm/s²) düzenlenir. “Modeli üret” geometriyi, bölgeleri ve varsayılan BC'leri yükler; “Vazgeç” kapatır." },
      { name: "STEP indir", what: "Geçerli geometriyi (onarım/midsurface sonrası hali dahil) STEP dosyası olarak indirir." },
      { name: "HEAL", what: "Tolerans onarımı + silindirik delikleri kapatma. Onay ister; yüzey/kenar numaraları değişebilir — mevcut bölge atamaları yanlış yüzeyi gösterebilir. Sonuç mesajı parça ve yüzey sayısının öncesi/sonrasını verir.", when: "Dışarıdan gelen kirli CAD; küçük delikler mesh'i gereksiz sıklaştırıyorsa." },
      { name: "FİLLET", what: "Fillet kaldırma. Yüzey seçiliyse seçili fillet yüzlerini kaldırır; seçim yoksa “Radius eşiği” alanı açılır, eşiğin altındaki filletler kaldırılır.", when: "Gerilme yığılmasıyla ilgilenilmeyen bölgelerde detay sadeleştirme." },
      { name: "MİD", what: "Orta yüzey (midsurface). Parça modunda katı seçiliyse ince cidarların orta yüzeyi otomatik; Yüzey modunda iki karşılıklı yüzey seçiliyse ikisinin arasına tek yüzey.", when: "2D shell mesh için zorunlu ön adım (kabuk mesh yalnız katıya bağlı olmayan yüzeylere atılır)." },
      { name: "KOPYA", what: "Seçili yüzey(ler)i bağımsız yüzey olarak kopyalar.", when: "Dış yüzeyden kabuk modeli kurmak." },
      { name: "OFFSET", what: "Seçili yüzeyleri kalınlık/2 kadar kaydırır. “Kalınlığı otomatik tespit et” en yakın paralel yüzeye göre ölçer; kapalıysa kalınlık elle girilir. “Yönü ters çevir” varsayılan içe yönü dışa çevirir. Uygula ile çalışır.", when: "Dış yüzeyden kopyalanmış kabuğu orta düzleme taşımak." },
      { name: "KENARLAR", what: "CAD kenar çizgilerini gösterir/gizler." },
      { name: "BÖLGELER (Physical Group)", what: "Şablondan gelen ya da elle oluşturulan adlandırılmış yüzey/kenar grupları. Çipe tıklamak grubu viewport'ta vurgular. Yüzey modunda seçim varken “Grup adı” + “+ Grup oluştur” yeni grup açar.", when: "BC'leri ve sonuç sorgularını adla takip etmek; şablon BC'leri bölge adına bağlıdır." },
    ],
  },
  // görsel: Şablon listesi açık (durability şablonları) ve örnek olarak “Ankastre kiriş (dikdörtgen kesit)” şeması.
  {
    id: "sablonlar",
    title: "Durability şablonları",
    intro:
      "Her şablon parametrik geometri + bölgeler + varsayılan BC + (varsa) kapalı form analitik referans getirir. Analitik referans, çözümden sonra 6 · RESULTS'ta “Analitik referans” tablosunda FEA ile yan yana gösterilir. Gruplar: grup1 temel doğrulama, grup2 profiller, grup3 braket/mil/flanş, grup4 gerilme yığılması.",
    items: DURABILITY_TEMPLATES.map((t) => ({
      name: `${t.title} · ${t.id}`,
      what: `${t.models} Bölgeler: ${t.regions.join(", ")}. Varsayılan BC: ${t.defaultBcs}.`,
      when: `Analitik: ${t.reference}`,
    })),
  },
  // görsel: 2 · MESH paneli — Eleman boyutu, 2D shell / 3D solid, Eleman tipi, 2. mertebe optimizasyonu, Mesh üret, “Yerel boyut / remesh” bölümü; viewport'ta kenar düğüm sayıları görünür.
  {
    id: "mesh",
    title: "2 · Mesh",
    intro:
      "Mesh Gmsh ile sunucuda üretilir. Sonuç kutusu boyut/şema, düğüm ve eleman sayısı ve eleman tipi dağılımını gösterir. Mesh boyutu (2D/3D) değişince eski mesh ve sonuçlar geçersiz sayılır.",
    items: [
      { name: "Eleman boyutu", what: "Global hedef kenar uzunluğu (mm)." },
      { name: "2D shell", what: "Kabuk mesh — yalnız orta yüzeylere (MİD/KOPYA/OFFSET ile oluşturulmuş, katıya bağlı olmayan yüzeyler) atılır; katılar mesh'ten çıkarılır. Elemanlar S3 (üçgen) / S4 (dörtgen), düğümde 6 serbestlik. Kalınlık 3 · MATERIAL'dan.", card: "*SHELL SECTION" },
      { name: "3D solid", what: "Hacim mesh. tet → her zaman 2. mertebe C3D10 (10 düğümlü); quad → hex C3D8 (1. mertebe, 8 düğümlü). Düğümde 3 öteleme serbestliği.", card: "*SOLID SECTION" },
      { name: "Eleman tipi · tet", what: "2D'de üçgen (S3), 3D'de 2. mertebe tetrahedron (C3D10).", card: "*ELEMENT" },
      { name: "Eleman tipi · quad", what: "2D'de dörtgen (S4; düzlem yüzeylerde Frontal-Delaunay-for-quads, eğri yüzeylerde Frontal-Delaunay + birleştirme). 3D'de hexahedron (C3D8).", card: "*ELEMENT" },
      { name: "Eleman tipi · mix", what: "2D'de dörtgen ağırlıklı karışık (üçgen + dörtgen). 3D'de tet ile aynı (C3D10)." },
      { name: "2. mertebe optimizasyonu", what: "3D tet mesh'te C3D10 kenar-ortası düğümlerini eğri yüzeye oturturken oluşan ters (negatif Jacobian) elemanları düzeltir (Gmsh HighOrder optimize). 2. mertebeyi açıp kapatmaz — 3D tet zaten 2. mertebedir.", when: "Eğri yüzeyli parçalarda Kalite raporu negatif Jacobian gösteriyorsa." },
      { name: "Kenar düğüm sayısı (+ / −)", what: "Viewport'ta kenar üzerindeki sayı o kenardaki düğüm sayısıdır; +/− ile değiştirilir. Komşu bölgelerde topoloji sıçramasını sabitlemek için." },
      { name: "Mesh üret", what: "Ayarlarla mesh üretir; sonuç kutusunda Shell/Solid · şema · size, düğüm/eleman sayısı ve tip dağılımı." },
      { name: "Yerel boyut / remesh", what: "Mesh üzerinde elemana tıkla (Ctrl ile çoklu) → tıklanan elemanın yüzeyi seçilir; boyut yaz → “Seçili yüzeylere uygula + remesh”. Yalnız o yüzeyler yerel boyutla, diğerleri global boyutla. Çipler (yüzey n · s mm, × ile kaldır) sonraki mesh'lerde de geçerli. “Tümünü yeniden mesh'le” listeyle yeniden üretir.", when: "Delik / çentik / fillet çevresinde sıklaştırma." },
      { name: "Mesh'i sil", what: "Mevcut mesh'i kaldırır." },
    ],
  },
  // görsel: Kalite sonucu açık — Jacobian/Aspect/Skewness/Warpage min/mean/max satırları, “Renk metriği” seçici, histogram ve viewport'ta renklendirilmiş mesh (kırmızı = kötü eleman); yanında Free edge sonucu.
  {
    id: "mesh-kalite",
    title: "2 · Mesh → Kalite ve mesh araçları",
    image: "/docs/durability/03-mesh-kalite.jpg",
    imageCaption: "3D tet mesh (5 mm, 21185 düğüm) kalite sonucu: Jacobian/Aspect/Skewness/Warpage min/mean/max, renk metriği ve dağılım.",
    intro:
      "Mesh araçları satırı: Kalite · Free edge · Equivalence · Rigid body · NSET. Hepsi mesh varken aktif. Değerler min / mean / max olarak verilir; eşik koyma ve karar kullanıcıdadır.",
    items: [
      { name: "Kalite · Jacobian (minSJ)", what: "Ölçeklenmiş Jacobian'ın eleman içindeki en küçük değeri. 1 = ideal şekil, ≤ 0 = ters (geçersiz) eleman." },
      { name: "Kalite · Aspect", what: "En uzun kenar / en kısa kenar. 1 = eşkenar." },
      { name: "Kalite · Skewness", what: "Eşaçısal çarpıklık: 0 = mükemmel (üçgende 60°, dörtgende 90° referans), 1 = dejenere." },
      { name: "Kalite · Warpage (°)", what: "Dörtgen yüzün düzlemden sapma açısı. 0 = düzlemsel." },
      { name: "Renk metriği + histogram", what: "Seçilen metrik viewport'ta mesh üzerine renklenir (kırmızı = kötü eleman) ve dağılımı histogramda." },
      { name: "Free edge", what: "Yalnız bir elemana ait kenarları bulur ve viewport'ta çizer; mesajda sayı. Kabukta beklenmeyen serbest kenar = birleşmemiş (dikişsiz) yüzeyler." },
      { name: "Equivalence", what: "Çakışan (aynı konumdaki) düğümleri sayar; onaylanırsa birleştirir. Mesaj: düğüm sayısı öncesi → sonrası.", when: "Kopyalanmış/ayrı yüzeylerden oluşan kabuklarda bağlantıyı kurmak." },
      { name: "Rigid body", what: "Seçili yüzey/kenarı Rigid body BC'nin köle seti olarak kilitler ve 4 · BOUNDARY CONDITIONS'a geçer; ardından Nokta modunda REF nokta seçilip BC eklenir.", card: "*RIGID BODY" },
      { name: "NSET", what: "Seçili yüzey/kenar/noktanın mesh düğüm setlerini raporlar (set adı, düğüm sayısı, ilk 12 düğüm no). Solver'a giden seti doğrulamak için.", card: "*NSET" },
    ],
  },
  // görsel: 3 · MATERIAL paneli — Kütüphane seçici, E/ν/ρ/Rp0.2/Rm/A/S-N özellik kutusu, ATA / + ÖZEL, “Gelişmiş (component / kalınlık)” açık, Ürün ağacı ve Atamalar listesi.
  {
    id: "malzeme",
    title: "3 · Material",
    image: "/docs/durability/04-malzeme.jpg",
    imageCaption: "3 · MATERIAL: kütüphane malzemesi (6061-T6) ve özellikleri; ağaçta Parça #0 → 6061-T6.",
    intro:
      "Kütüphane SI biriminde saklar (E Pa, ρ kg/m³); deck'e yazılırken MPa ve tonne/mm³'e çevrilir. Malzemesi atanmamış parça varsa varsayılan çelik (E 210 GPa, ν 0,3, ρ 7850) yazılır. Sonuç panelindeki MATERIAL=true / SECTION=true bayrakları kartların yazıldığını gösterir.",
    items: [
      { name: "Kütüphane", what: "Malzeme listesi (ad + kategori). Hazır: S235, S275, S355 (çelik), 6061-T6, 7075-T6 (alüminyum) ve eklenen özel malzemeler.", card: "*MATERIAL" },
      { name: "E · elastisite modülü", what: "Elastik kartın ilk alanı (GPa gösterilir, MPa yazılır).", card: "*ELASTIC" },
      { name: "ν · Poisson", what: "Elastik kartın ikinci alanı.", card: "*ELASTIC" },
      { name: "ρ · yoğunluk", what: "Kütle — Gravity yükü ve modal frekanslar bunu kullanır. Statik yalnız yükte etkisizdir.", card: "*DENSITY" },
      { name: "Rp0.2 · akma", what: "SAFETY FACTOR = Rp0.2 / max von Mises. Plastisite açıkken pekleşme tablosunun ilk noktası.", card: "*PLASTIC" },
      { name: "Rm · çekme dayanımı", what: "Tahmini S-N eğrisinin ve plastisite tablosunun ikinci noktasının kaynağı." },
      { name: "A · kopma uzaması (%)", what: "Plastisitede Rm noktasının gerinimi olarak kullanılır (tekdüze uzama yerine — kabul). A yoksa mükemmel plastik yazılır." },
      { name: "S-N", what: "Yorulma eğrisi durumu: tahmini / test / var / yok. FATIGUE LIFE metrik kartı bunu kullanır." },
      { name: "ATA", what: "Seçili kütüphane malzemesini seçili parçaya atar (Parça modunda parça ya da mesh elemanı + Face/Attached). Atamalar listesinde “Parça #n → malzeme”." },
      { name: "+ ÖZEL → Özel malzeme ekle", what: "Ad, E (GPa), ν, ρ, Rp0.2 (MPa), Rm (MPa). “Oluştururken tahmini S-N ekle” işaretliyse S-N Rm'den üretilir." },
      { name: "Gelişmiş · Component adı / Property / Kalınlık", what: "Mesh parçası için component kaydı: Property shell (kalınlık, mm) ya da solid. “Component güncelle” kaydeder. 2D çözümde kabuk kalınlığı önce ürün ağacındaki component'ten, yoksa bu alandan alınır.", card: "*SHELL SECTION" },
      { name: "Tahmini S-N üret", what: "Seçili malzemeye Rm'den ampirik 3 noktalı S-N yazar: 10³ çevrimde 0,90·Rm, 10⁶'da 0,45·Rm, 10⁷'de 0,40·Rm. Test verisinin yerini tutmaz." },
      { name: "Ürün ağacı", what: "Component'i olan her parça: kalınlık ve malzeme satır içinde düzenlenir, kaydedilir." },
      { name: "Atamalar", what: "Parça → malzeme (kategori) listesi; model ağacında da görünür." },
    ],
  },
  // görsel: 4 · BOUNDARY CONDITIONS paneli — BC türü düğmeleri (Fixed … Rigid body), seçili türün ipucu satırı ve alanları, “Listeye ekle”, BC LİSTESİ kartları; viewport'ta seçili yüzey vurgulu.
  {
    id: "bc",
    title: "4 · Boundary conditions — BC türleri",
    image: "/docs/durability/05-bc.jpg",
    imageCaption: "4 · BOUNDARY CONDITIONS: BC türü düğmeleri ve seçim ipucu; üstte bölge kısayolları (ankastre_uc, yuk_yuzeyi).",
    intro:
      "Akış: viewport'ta seçim yap → BC türü düğmesi → alanları doldur → Listeye ekle. Seçim önceliği: 3D solid'de CAD yüzey seçimi, 2D shell'de mesh eleman seçimi önce gelir. " +
      "Kısıt kartları (*BOUNDARY, *TRANSFORM, *RIGID BODY) adımın dışında, yük kartları (*CLOAD, *DLOAD) *STEP içinde yazılır. En az bir Fixed / Displacement / Sliding olmadan çözüm düğmesi pasiftir (aksi halde rijit cisim hareketi).",
    items: [
      { name: "Fixed", what: "Seçilen yüzey/kenar/nokta düğümlerinin tüm serbestlikleri sıfır: 3D solid'de 1–3 (öteleme), 2D shell'de 1–6 (öteleme + dönme).", when: "Ankastre uç, kaynaklı / cıvatayla tutulan yüzey (idealize rijit).", card: "*BOUNDARY" },
      { name: "Nokta/yüzey yük", what: "Fx/Fy/Fz = seçimin TAMAMINA uygulanan toplam kuvvet (N); kaç yüz/kenar seçildiğinden bağımsız. Yalnız yüzey seçiliyse alanla orantılı tutarlı düğüm ağırlıklarıyla (2. mertebede köşe düğümleri 0), karışık seçimde düğümlere eşit bölünür. Seçim: mesh yüzeyi ya da CAD yüzey/kenar/nokta.", when: "Uç yükü, tekil kuvvet, toplam kuvveti bilinen bağlantı yükü.", card: "*CLOAD" },
      { name: "Pressure", what: "2D shell: yüzey eleman setine dağıtılmış basınç (P, MPa), eleman normali doğrultusunda; dx/dy/dz kullanılmaz. 3D solid: yüzey eleman seti yazılmaz — |P| seçili yüzün düğümlerine eşit bölünmüş kuvvet olarak dx/dy/dz yönünde (boşsa −z) yazılır; yani 3D'de değer yüze dik basınç değil toplam kuvvet (N) gibi davranır.", when: "Kabukta yayılı yük / iç basınç.", card: "*DLOAD" },
      { name: "Displacement", what: "Ux/Uy/Uz (mm) zorlanmış deplasman. Arayüzden eklenen BC üç bileşeni de yazar (0 dahil); yalnız bazı bileşenleri tutan kayıtlar şablondan gelir (ör. basit mesnet sağ uç Uy=Uz=0).", when: "Deplasman kontrollü yükleme, bilinen mesnet hareketi, simetri (0 bileşen).", card: "*BOUNDARY" },
      { name: "Sliding", what: "Yüzey/kenar düğümlerine Nx/Ny/Nz normalli yerel eksen tanımlanır; yalnız normal yönü tutulur, teğet düzlemde kayma serbest.", when: "Kaygan mesnet, simetri düzlemi, düzleme dayanan yüzey.", card: "*TRANSFORM" },
      { name: "Bearing", what: "Büyüklük (toplam kuvvet, N) Axis x/y/z yönünde seçili yüzün düğümlerine kosinüs ağırlıklı dağıtılır (eksen boşsa −z).", when: "Cıvata/pim deliğine yatak yükü.", card: "*CLOAD" },
      { name: "Gravity", what: "Seçim gerekmez. gx/gy/gz (mm/s², varsayılan gz = −9810) tüm parçalara kütle yükü olarak; yoğunluk (ρ) kullanılır.", when: "Öz ağırlık.", card: "*DLOAD" },
      { name: "Rigid body", what: "Köle yüzey/kenar düğümlerini bir REF NODE'a (CAD nokta, Nokta modu) rijit bağlar. Önce köle yüzey seçilip Rigid body'ye basılır (ya da Mesh araçlarındaki Rigid body), sonra Nokta modunda REF seçilip eklenir. REF nokta köle yüzeyin üzerinde olmamalı.", when: "Yükü/kısıtı bir referans noktasından dağıtmak; rijit kabul edilen bağlantı.", card: "*RIGID BODY" },
      { name: "Listeye ekle", what: "Taslak BC'yi BC LİSTESİ'ne ekler (özet: tür, değerler, seçim). Kart sağındaki ⋯ kaldırır. Şablon BC'leri buraya yüklenir." },
      { name: "Lineer teori satırı", what: "Analitik referansı olan şablonda yük eklenince: beklenen sehim (mm), L'ye oranı, eşik (%10), σ (MPa) ve “büyük deformasyon bandında” bilgisi. Yalnız bilgi." },
    ],
  },
  // görsel: BC panelinin alt kısmı — Case adı, “ccx çalıştır (kuruluysa)”, NLGEOM, Plastisite + Pekleşme tablosu, Artım sayısı ve “.inp üret / çöz”; ayrıca ön kontrol onay penceresi.
  {
    id: "cozum",
    title: "4 · Boundary conditions → Çözüm seçenekleri",
    image: "/docs/durability/06-cozum.jpg",
    imageCaption: "BC listesi, Case adı, ccx çalıştır, NLGEOM, Plastisite, lineer teori ön tahmini ve “.inp üret / çöz”.",
    intro:
      "Varsayılan çözüm lineer statik: tek adım, tek artım. NLGEOM veya Plastisite açılınca artımlı çözüme geçilir ve tepki kuvveti (RF) de yazılır. Çıktı: düğümde U (+RF), elemanda S (+ plastikte PEEQ).",
    items: [
      { name: "Case adı", what: "İsteğe bağlı koşu adı (ör. “9kN - orijinal”); Analiz geçmişi'nde görünür." },
      { name: "ccx çalıştır (kuruluysa)", what: "İşaretliyse CalculiX çalıştırılır ve sonuçlar okunur; değilse yalnız .inp üretilir." },
      { name: "NLGEOM (büyük deformasyon)", what: "Denge denklemleri deforme geometride kurulur, yük artımlı uygulanır. Lineer çözüme göre belirgin daha yavaş.", when: "Sehim / boy oranı büyükken (lineer çözüm burada hata vermez, deforme olmamış geometride çözer).", card: "*STEP, NLGEOM" },
      { name: "Ön kontrol penceresi", what: "NLGEOM kapalıyken lineer analitik sehim L'nin %10'unu aşıyorsa sorar: Tamam = NLGEOM, İptal = lineer devam. Ön kontrol yapılamazsa sorulmaz." },
      { name: "Plastisite", what: "Akma sonrası izotropik pekleşme: kütüphanedeki Rp0.2 / Rm / A'dan iki noktalı gerçek gerilme – plastik gerinim tablosu (σ_true = σ·(1+ε), ε_true = ln(1+ε)). Son noktadan sonra sabit gerilme.", when: "Gerilme akmayı aşıyorsa ve kalıcı şekil değiştirme / limit yük isteniyorsa.", card: "*PLASTIC" },
      { name: "Pekleşme tablosu (isteğe bağlı)", what: "Satır başına “σ_gerçek MPa, ε_plastik”. Boşsa kütüphaneden türetilir; doluysa kabul atlanır.", card: "*PLASTIC" },
      { name: "Artım sayısı (1–500)", what: "NLGEOM / Plastisite açıkken: ilk artım = 1/n, en büyük artım = 1/n, en küçük = 1/(100·n); adımda en fazla max(100, 5n) artım.", card: "*STATIC" },
      { name: ".inp üret / çöz", what: "Girdi destesini üretir, ccx işaretliyse çözer (sunucuda kuyrukta; durum mesajı güncellenir) ve 6 · RESULTS'a geçer.", card: "*STEP" },
    ],
  },
  // görsel: MODAL sekmesi, 5 · MODAL paneli — mesnet sayacı, “+ Fixed Mesnet Ekle”, MESNETLER, Mod sayısı, f min / f max, frekans grafiği ve mod şekli kartları; ayrıca “Tüm modları göster” ızgarası.
  {
    id: "modal",
    title: "5 · Modal",
    intro:
      "Sol raydan MODAL seçilir. Aynı mesh, malzeme ve mesnetler kullanılır; yükler (Nokta/yüzey yük, Pressure, Gravity) modal adıma yazılmaz. Lanczos özdeğer çözümü, mod şekilleri saklanır.",
    items: [
      { name: "mesnet / mesh özeti", what: "Kaç Fixed/Displacement/Sliding mesnet olduğu ve mesh boyutu (2D/3D)." },
      { name: "+ Fixed Mesnet Ekle", what: "Mesh elemanına tıklanır (Face = tüm yüzey) → Fixed mesnet eklenir. Diğer mesnet türleri 4 · BOUNDARY CONDITIONS'tan.", card: "*BOUNDARY" },
      { name: "MESNETLER", what: "Yalnız kısıtlar listelenir; ⋯ kaldırır." },
      { name: "Mod sayısı", what: "İstenen öz değer sayısı (1–200).", card: "*FREQUENCY" },
      { name: "f min / f max (Hz, opsiyonel)", what: "İkisi birlikte girilirse yalnız bu banttaki modlar aranır.", card: "*FREQUENCY" },
      { name: "ccx çalıştır (kuruluysa)", what: "İşaretli değilse yalnız .inp üretilir; frekans listesi için gerekli." },
      { name: "Modal çöz", what: "Frekans adımını çözer. En az bir mesnet gerekir; mesnetsiz (serbest–serbest) çözüm bu arayüzden başlatılmaz." },
      { name: "f (Hz) · mode grafiği", what: "Doğal frekansların mod numarasına göre çizgisi." },
      { name: "Mod şekilleri · kart", what: "Her kart bir mod: küçük şekil, Mode n ve frekans. Göster = 3B kontur (|U|, mod başına normalize); Animasyon = ± salınım, Durdur." },
      { name: "Tüm modları göster (ızgara)", what: "Tüm modlar yan yana: ▶ Animasyon, Kameraları eşle (birini döndürünce hepsi döner), Genlik kaydırıcısı (%1–20), ← Tüm modlar (tek moddan dönüş), |u|/|u|max renk skalası." },
    ],
  },
  // görsel: 6 · RESULTS paneli — çözüm mesajı, MATERIAL/SECTION/ccx/ran bayrakları, “.inp indir”, Analitik referans tablosu (Metrik/Analitik/FEA/Sapma), von Mises ve Deplasman istatistik tablosu + histogramlar.
  {
    id: "sonuc",
    title: "6 · Results",
    intro:
      "Statik ve modal sonuçlar burada özetlenir; 3B görselleştirme viewport'un üzerindeki yüzen panellerdedir. Kabukta CalculiX genişletilmiş düğüm yazar; üst/alt yüzey çifti orta yüzey düğümüne katlanır (von Mises için en büyüğü, deplasman için ortalaması).",
    items: [
      { name: "Sonuç mesajı + bayraklar", what: "Solver mesajı ve MATERIAL / SECTION kartları yazıldı mı, ccx mevcut mu, çalıştı mı (ran)." },
      { name: ".inp indir", what: "Üretilen CalculiX girdi destesini (.inp) indirir — yazılan tüm kartlar burada görülür." },
      { name: "Analitik referans", what: "Analitik referansı olan şablonlarda: metrik, analitik değer, FEA değeri, sapma." },
      { name: "Von Mises (MPa)", what: "Düğüm von Mises değerlerinin min / max / ortalama / medyan tablosu ve dağılım histogramı.", card: "*EL FILE" },
      { name: "Deplasman (mm)", what: "|U| için aynı tablo ve histogram.", card: "*NODE FILE" },
      { name: "Modal sonuçta", what: "Seçili mod ve frekansı, mod şekli |U| tablosu ve histogramı (mod şekli normalize — mutlak genlik anlamlı değil)." },
      { name: "TAHMİN bandı", what: "Sonuç vekil modelden (ML Stüdyo) geldiyse: “TAHMİN — tam CalculiX çözümü değil”, gerekirse “eğitim uzayı dışı”." },
    ],
  },
  // görsel: Viewport — sağ üstte renk skalası paneli (VON MISES başlığı, Von Mises / Deplasman / SF, Max/Min alanları), sağ altta Deformasyon ölçeği kaydırıcısı + ▶ Animasyon; altta metrik kartlar (MAX STRESS, SAFETY FACTOR, FATIGUE LIFE, CRITICAL NODE).
  {
    id: "sonuc-3b",
    title: "6 · Results → 3B kontur ve metrik kartlar",
    intro:
      "Sonuç alındığında viewport'ta kontur ve kontroller belirir. Metrik kartlar viewport'un altında, statik çözümde.",
    items: [
      { name: "Sonuçları göster (n nokta)", what: "Konturu açar/kapar." },
      { name: "Alan · Von Mises / Deplasman / SF", what: "Kontur alanı. SF = düğüm başına Rp0.2 / σ_vM. Modal sonuçta alan seçimi yok (MODE n)." },
      { name: "Renk skalası · Max / Min", what: "Skala sınırları; boşsa otomatik (0 – en büyük değer). Altında gerçek Max." },
      { name: "Deformasyon ölçeği", what: "Deforme şeklin büyütme katsayısı (×) ve karşılık gelen kayma; kaydırıcının üst sınırı modelin boyutuna göre uyarlanır. 0 = deforme olmamış geometri." },
      { name: "▶ Animasyon / ⏸ Durdur", what: "Deforme şekli 0 ile seçili ölçek arasında oynatır." },
      { name: "KİNEMATİK / MALZEME · KİNEMATİK", what: "NLGEOM ve/veya PLASTİK koşularda: artım sayısı, en büyük PEEQ (%), cutback sayısı, yakınsadı / YAKINSAMADI.", card: "*STEP, NLGEOM" },
      { name: "TEPKİ KUVVETİ", what: "Sabit uçtaki toplam tepki (N, son artım); artımlı çözümlerde. Artımlardaki tepe son değerden büyükse “tepe … N” ve ilk akmaya oranı da yazılır." },
      { name: "MAX STRESS", what: "En büyük von Mises (MPa) ve düğüm no." },
      { name: "SAFETY FACTOR", what: "Rp0.2 / max von Mises (statik akma kıstası, yorulma güvenliği değil). < 1 kırmızı." },
      { name: "FATIGUE LIFE", what: "Max von Mises tek genlik kabul edilip malzemenin S-N eğrisinden log-log interpolasyonla çevrim sayısı. Eğrinin üst noktasının üzerindeyse o nokta (ekstrapole edilmez); en alt noktanın altındaysa en alt noktanın N'i + “runout”. S-N yoksa “—”." },
      { name: "CRITICAL NODE", what: "Max von Mises'in düğüm numarası." },
    ],
  },
  // görsel: Alttaki “Analiz geçmişi” açık (süzgeçler, klasörle, iki koşu işaretli, Karşılaştır) ve karşılaştırma ekranı (iki viewport, ORTAK COLORBAR, Kamera senkron, Probe, PDF A / PDF B).
  {
    id: "gecmis",
    title: "Analiz geçmişi, karşılaştırma ve PDF",
    intro:
      "Her çözüm veritabanına kaydedilir ve alttaki Analiz geçmişi'nde listelenir (durability ve modal; crash koşuları ayrı dock'ta).",
    items: [
      { name: "Analiz geçmişi (Aç / Gizle)", what: "Koşu satırı: ad, durum, geometri dosyası, 2D/3D, tarih, şablon parametreleri, VM max ve deplasman max. Üst kenardan sürüklenerek boyutlanır." },
      { name: "Süzgeçler", what: "Şablona göre (tüm şablonlar), DOE setine göre (tüm koşular / elle çözülenler / DOE #n), klasörle (eğitim durumuna / DOE setine göre), dışlananları gizle." },
      { name: "Satıra tıklama", what: "Koşuyu inceleme ekranında tek başına açar." },
      { name: "Düzenle", what: "Koşunun geometri, mesh, malzeme ve BC'lerini çalışma alanına yükler." },
      { name: "Dışla / Geri al", what: "Koşuyu deneme/mükerrer/kalitesiz olarak işaretler; silinmez, ML eğitim setine girmez." },
      { name: "Sil", what: "Koşuyu kalıcı siler." },
      { name: "Karşılaştır", what: "İki koşu işaretlenince (n/2 seçili) açılır: iki viewport yan yana, ortak renk skalası, max σ / SF / ömür özetleri, dağılım ve düğüm tabloları." },
      { name: "Karşılaştırma araçları", what: "← Düzenlemeye dön, Von Mises / Deplasman, Kamera senkron (iki görünüm birlikte döner), Probe (tıklanan noktadaki en yakın düğümün σ / |U| / id değeri)." },
      { name: "PDF / PDF A / PDF B", what: "Koşunun sunucuda üretilen PDF raporunu açar (tek koşuda PDF, karşılaştırmada her koşu için ayrı)." },
    ],
  },
  // görsel: ML Stüdyo → Yakınsama sekmesi — sabit geometri, malzeme, basamaklar, kaba→ince kaydırıcısı ve sonuç tablosu (es, oran, düğüm, değer, Δönceki, Δen ince).
  {
    id: "yakinsama",
    title: "Mesh yakınsama taraması (ML Stüdyo)",
    intro:
      "Üst çubuktaki “ML Stüdyo” → Yakınsama. Aynı şablon geometrisini kabadan inceye birkaç eleman boyutunda gerçekten çözer ve metriklerin değişimini tabloya döker. Karar (hangi boyutun yeterli olduğu) kullanıcıdadır.",
    items: [
      { name: "Sabit geometri / Malzeme", what: "Taranacak şablon parametreleri ve malzeme." },
      { name: "Basamaklar (← kaba · ince →)", what: "Eleman boyutu basamakları; solver her basamakta çalışır (8 basamak ≈ 100 s), çözülemeyen basamak atlanır." },
      { name: "Sonuç tablosu", what: "es (mm), oran, düğüm sayısı, durum ve her metrik için değer, Δönceki (bir önceki basamağa göre), Δen ince (en ince basamağa göre)." },
    ],
  },
];
