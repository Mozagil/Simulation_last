/**
 * Crash (OpenRadioss) kullanıcı belgesi — navbar "Belgeler" penceresinde
 * gösterilir (kullanıcı isteği 2026-10-08). Her özellik / düğme / kart: ne
 * yapar, hangi senaryoda kullanılır, OpenRadioss kartı ve LS-DYNA karşılığı
 * (≈, yalnız bilgi amaçlı ad — LS-DYNA kullanılmaz; eşleme
 * `lib/dynaKeywords.ts`). Görseller `public/docs/crash/`.
 *
 * Araç mühendise karar vermez: "Ne zaman" satırları tipik kullanımı
 * anlatır, değer önermez.
 */

export interface DocItem {
  name: string;
  what: string;
  when?: string;
  /** OpenRadioss kartı — LS-DYNA karşılığı `dynaFor(card)` ile bulunur. */
  card?: string;
  /** Eşleme tablosunda olmayan özel karşılık metni. */
  dyna?: string;
}

export interface DocSection {
  id: string;
  title: string;
  intro: string;
  image?: string;
  imageCaption?: string;
  items?: DocItem[];
  /** Ek görseller (bölüm sonunda). */
  gallery?: { src: string; caption: string }[];
}

export interface DocScenario {
  id: string;
  title: string;
  template: string;
  setup: string;
  features: string[];
  validation: string;
  reference: string;
}

const IMG = (f: string) => `/docs/crash/${f}`;

export const CRASH_DOC: DocSection[] = [
  {
    id: "akis",
    title: "Genel akış",
    intro:
      "Crash analizi beş adımda kurulur: 1 · Geometry → 2 · Mesh → 3 · Material → 4 · Crash → 5 · Sonuçlar. " +
      "Solver OpenRadioss (explicit) sunucuda Docker imajında koşar; kullanıcı tarafında hiçbir CAE yazılımı gerekmez. " +
      "Viewport'ta rijit duvar (mavi düzlem), hız oku (turuncu) ve parça rol etiketleri/renkleri kurulumla birlikte güncellenir.",
    image: IMG("01-genel.jpg"),
    imageCaption: "Crash box: 2D quad mesh, +X normalli rijit duvar x = −1, −X yönünde 10 m/s, parça #0 hareketli (altın).",
    items: [
      { name: "1 · Geometry", what: "STEP/IGES yükle ya da şablondan üret (crash box, S-kiriş, kapı, plaka–küre …). Bölgeler (Physical Group) şablondan gelir: kutu_on, kutu_arka, plaka_kenar …" },
      { name: "2 · Mesh", what: "2D kabuk (quad) ya da 3D solid (tet). Eğri yüzeylerde quad için yüzey başına ayrı algoritma; yerel remesh (mesh üzerinden yüzey seç + boyut); “Mesh'i sil”. Mesh sonrası CAD varsayılan gizli." },
      { name: "3 · Material", what: "Kütüphane malzemesi (E, ν, ρ, akma) + crash malzeme modeli (LAW1/2/36) ve kopma (/FAIL). Kabuk kalınlığı ürün ağacındaki bileşenden." },
      { name: "4 · Crash", what: "Dört akordeon grubu (Çarpma, Parçalar, Temaslar, Ek tanımlar) + Uzman ayarları. Eksik bilgi varsa sayaç “x eksik” der ve Çalıştır pasif olur." },
      { name: "5 · Sonuçlar", what: "Koşu durumu, skalerler, kuvvet–zaman grafiği, çıktı ayarları. Koşu çözülünce viewport'ta 3B deforme şekil animasyonu kendiliğinden açılır." },
    ],
  },
  {
    id: "ust",
    title: "Üst çubuk ve viewport düğmeleri",
    intro: "Crash ile ilgili genel düğmeler.",
    image: IMG("14-agac-bc.jpg"),
    imageCaption: "Ürün ağacı: Malzeme modeli ve Sınır koşulları (Çarpma · Parça rolleri · Temaslar · Ek tanımlar) — 4 · Crash ile birlikte güncellenir.",
    items: [
      { name: "SINIR KOŞ.", what: "Viewport'taki crash işaretlerini (duvar, hız oku, rol etiketleri) ve rol renklerini gösterir/gizler. Vurgulu = görünür." },
      { name: "Solid / Surface (KENARLAR)", what: "CAD geometrisini gösterir/gizler. Mesh sonrası CAD gizli gelir; düğme vurgulanınca görünür." },
      { name: "Rol renkleri", what: "Hareketli = altın, sabit = kırmızı, serbest = mor. Seçim vurgusu turuncu (karışmaz). 2D'de mesh parça no ↔ CAD parça no yüzey üzerinden eşlenir." },
      { name: "LS-DYNA karşılıkları (⇄ düğmesi)", what: "Crash panelinin ve 3 · Material'ın sağ üstünde. Açıkken OpenRadioss kart adının altında yaklaşık LS-DYNA keyword'ü görünür. Kişisel tercih, tarayıcıda hatırlanır. Yalnız ad — LS-DYNA kullanılmaz." },
      { name: "Ürün ağacı (sol)", what: "Geometri, bölgeler, parçalar ve mesh yanında crash kurulumunun tamamı: Malzeme modeli (ortak + parça başına LAW ve kopma) ve Sınır koşulları — Çarpma (rijit duvar / duvarsız, ilk hız, süre, yerçekimi), Parça rolleri, Temaslar, Ek tanımlar (kilit, kütle/kızak, sabit hız, ayrı ilk hız). 4 · Crash'te değişen her tanım ağaçta anında görünür; uzun satırın tamamı üzerine gelince." },
      { name: "+ Yeni crash vakası", what: "Hazır katalogdan geometri + kurulum + koşu tek seferde (bkz. Hazır senaryolar). Seçili senaryonun kendi şeması görünür." },
      { name: "Crash geçmişi (alt dock)", what: "Koşular; kapsam düğmesi \"Tüm geometriler\" (varsayılan) / \"Bu geometri\" (seçim hatırlanır): durum, tepe kuvvet, ▶ animasyon, 📈 eğri, ⊘ dışla, karşılaştır (≤ 6). Üst kenardan sürüklenerek boyutlanır (≤ pencerenin %60'ı)." },
    ],
  },
  {
    id: "malzeme",
    title: "3 · Material (crash)",
    intro:
      "Crash sekmesinde 3 · Material, BC paneli gibi üç akordeon grubudur: 1 Kütüphane malzemesi, 2 Parçalara ata, " +
      "3 Malzeme modeli (LAW) ve kopma. Sayaç eksik atamayı / kalınlığı gösterir; geometri ve mesh yokken atama grubu “bekliyor” der. " +
      "Malzeme modeli 3. grupta üç kutucuktan biri tıklanarak seçilir; seçili kutu dolu renk ve ✓ ile, altındaki “Seçili:” satırıyla gösterilir. " +
      "Seçim grup başlığında, 1. gruptaki “Malzeme modeli → 3. grupta seç” satırında ve ürün ağacındaki “Malzeme modeli” düğümünde de görünür. " +
      "Yalnız explicit'te kullanılan değerler gösterilir — çekme dayanımı (Rm), uzama ve S-N durability'nin malzeme adımındadır. " +
      "Elle kurulan koşuda varsayılan LAW2.",
    image: IMG("08b-kutuphane.png"),
    imageCaption: "1 Kütüphane malzemesi: OpenRadioss'a giden dört değer ve gittikleri kart alanı.",
    items: [
      { name: "E · elastisite modülü", what: "Malzeme kartının elastik modülü (/MAT kartı, her LAW).", dyna: "*MAT_… E" },
      { name: "ν · Poisson", what: "Malzeme kartının Poisson oranı.", dyna: "*MAT_… PR" },
      { name: "ρ · yoğunluk", what: "Kütle ve zaman adımı buradan (kg/m³ → deck'te kg/mm³).", dyna: "*MAT_… RO" },
      { name: "σy · akma (Rp0.2)", what: "LAW2'nin a parametresi — davranış kartında σy boş bırakılırsa bu değer kullanılır.", card: "/MAT/LAW2", dyna: "*MAT_024 SIGY / *MAT_015 A" },
      { name: "LAW36 eğrileri", what: "Kütüphane malzemesine kaydedilen ölçülmüş σ–ε eğrileri; LAW36 seçilince kullanılır.", card: "/MAT/LAW36" },
      { name: "+ Özel malzeme", what: "Yeni kütüphane malzemesi: ad, E, ν, ρ, akma. Crash'te Rm / S-N sorulmaz." },
      { name: "2 · Parçalara ata", what: "Parça satırı: atanan malzeme ve kabuk kalınlığı; “… ata” seçili kütüphane malzemesini o parçaya atar, “Tüm parçalara ata” hepsine. Altında bileşen (kalınlık / malzeme) düzenleme." },
      { name: "Malzeme modeli seçici", what: "3. grupta LAW1 · LAW2 · LAW36 kutucukları; tıklanan seçilir (✓). “Seçili: LAW2 elasto-plastik” satırı ve ürün ağacı seçimi doğrular. Çok parçalı modelde Global / Ayrı ile parça başına ayrı model." },
      { name: "LAW1 elastik", what: "Doğrusal elastik; kalıcı şekil değiştirmez, enerji yutmaz (kutu ezilmez, seker).", when: "Dalga yayılımı (Hopkinson), rijit gibi davranması istenen parçalar, doğrulama (V1).", card: "/MAT/LAW1" },
      { name: "LAW2 plastik (Johnson–Cook)", what: "σ = a + b·εₚⁿ; isteğe bağlı hız terimi (C, ε̇₀) ve kopma (εp,max). Kalıcı şekil değiştirir, enerji yutar.", when: "Ezilen/deforme olan her metal parça — crash'in standart seçimi.", card: "/MAT/LAW2" },
      { name: "LAW36 tablo", what: "Ölçülmüş σ–ε eğrisi (hız başına ayrı eğri olabilir).", when: "Test eğrisi elindeyse.", card: "/MAT/LAW36" },
      { name: "/FAIL/JOHNSON", what: "Johnson–Cook hasarı: kopma gerinimi gerilme durumuna, hıza, sıcaklığa bağlı (D1–D5).", when: "En gerçekçi; en çok veri isteyen.", card: "/FAIL/JOHNSON" },
      { name: "/FAIL/TENSSTRAIN", what: "Çekme gerinimi: ε_t1'de hasar başlar, ε_f1'de eleman silinir. En az bir sınır girilmeli (boşsa koşu reddedilir).", when: "Basit, az veri; ölçüm yoksa ilk yaklaşım.", card: "/FAIL/TENSSTRAIN" },
      { name: "Parça başına model", what: "Çok parçalı modelde her parçaya ayrı kart (ör. küre LAW1, plaka LAW2)." },
    ],
    gallery: [
      { src: IMG("08c-law-secici.jpg"), caption: "3 Malzeme modeli (LAW) ve kopma: üç kutucuk, seçili olan ✓ ve “Seçili:” satırı; altında aç/kapa bölümler." },
      { src: IMG("08-malzeme.png"), caption: "3 Malzeme modeli ve kopma · LAW2: aç/kapa bölümler (Akma ve pekleşme, Hız etkisi, Sıcaklık, Basit kopma, Kopma / hasar); kapalıyken değiştirilen alanlar başlıkta özetlenir." },
      { src: IMG("09-fail.png"), caption: "Kopma / hasar: Johnson–Cook ve çekme gerinimi kartları; seçili kart mavi çerçeveli, alanları altında." },
    ],
  },
  {
    id: "carpma",
    title: "4 · Crash → 1 Çarpma",
    intro: "Ne neye, hangi hızla çarpıyor. İki mod: rijit duvara çarpma ya da duvarsız (yalnız ilk hız).",
    image: IMG("02-carpma.png"),
    imageCaption: "Çarpma grubu, LS-DYNA karşılıkları açık.",
    items: [
      { name: "Rijit duvara çarpma", what: "Sonsuz rijit düzlem (/RWALL). Hareketli parçalar duvara doğru (normalin tersine) ilk hız alır.", when: "Crash box, S-kiriş, Taylor çubuğu, düşme (zemin).", card: "/RWALL" },
      { name: "Duvarsız · yalnız ilk hız", what: "Duvar yazılmaz; hız yönü doğrudan seçilir. Parça–parça çarpışma temasla çözülür.", when: "Plaka–küre, kapı, iki parçalı montajlar.", card: "/INIVEL" },
      { name: "Hız (m/s)", what: "İlk hız büyüklüğü. Çözücü kg–mm–ms biriminde: 1 m/s = 1 mm/ms.", card: "/INIVEL" },
      { name: "Açı (°)", what: "0 = duvara dik. Eğik çarpma için hız vektörü döndürülür." },
      { name: "Süre (ms)", what: "Simülasyon bitiş zamanı. Kızaklı ezilmede kızak durana kadar uzun olmalı (ezilme mesafesi ancak durunca hesaplanır).", card: "/RUN" },
      { name: "Duvarın baktığı yön (+X … −Z, Özel)", what: "Duvar normali. Parça normalin tersine ilerler (ör. +X normal → −X hız).", card: "/RWALL" },
      { name: "Duvar konumu + ⌖ Modelden seç", what: "Düzlemin geçtiği nokta (mm). “Modelden seç” ile viewport'ta tıklanan nokta yazılır.", card: "/RWALL" },
      { name: "Duvarı kaydet / Kayıtlı duvar", what: "Duvar noktası + yön (normal) bir adla kaydedilir (ad boşsa \"nokta (x, y, z) · normal ±A\"); sonraki vakada listeden seçince ikisi panele dolar. × seçili kaydı siler. Kayıtlar bu tarayıcıda tutulur." },
      { name: "Yerçekimi", what: "Sabit ivme (ör. −9.81 m/s², Z).", when: "Düşme testi, FOPS. Kısa yatay çarpışmalarda etkisi ihmal edilebilir.", card: "/GRAV" },
    ],
  },
  {
    id: "parcalar",
    title: "4 · Crash → 2 Parçalar",
    intro: "Her parçaya tek soru: bu parça ne yapıyor?",
    image: IMG("03-parcalar.png"),
    imageCaption: "Parça satırı: malzeme · kalınlık ve rol seçimi.",
    items: [
      { name: "Hareketli", what: "Parçanın tüm düğümlerine ilk hız verilir; rijit duvarla temas eder.", when: "Crash box, çarpan küre/impaktör.", card: "/INIVEL" },
      { name: "Sabit", what: "Tüm düğümler 6 serbestlikte kilitli (111111).", when: "Çarpma plakası, ankastre taban.", card: "/BCS" },
      { name: "Serbest", what: "Ne ilk hız ne kilit — yalnız temasla hareket eder.", when: "Zincirleme çarpışma; kapı kirişi (uçları ayrıca Ek tanımlar'da kilitlenir)." },
    ],
  },
  {
    id: "temaslar",
    title: "4 · Crash → 3 Temaslar",
    intro: "Temas tanımlanmazsa parçalar birbirinin içinden geçer. Aynı parça iki tarafta = öz temas (katlanan kutu).",
    image: IMG("04-temaslar.png"),
    imageCaption: "TYPE7 öz temas (#0 ↔ #0) ve bayraklar.",
    items: [
      { name: "TYPE7", what: "Düğüm → yüzey teması (slave düğümleri master yüzeye çarpar). Genel amaçlı, hızlı.", when: "Kutunun kendi katları (öz temas), küre → plaka, impaktör → kiriş.", card: "/INTER/TYPE7" },
      { name: "TYPE24", what: "Yüzey ↔ yüzey (kenar–kenar dahil). İnce kabuk katlanırken kenarların birbirine girmesini daha iyi yakalar.", card: "/INTER/TYPE24" },
      { name: "Fric", what: "Coulomb sürtünme katsayısı." },
      { name: "Stfac", what: "Temas rijitliği ölçeği." },
      { name: "GAPmin (TYPE7) / Iedge (TYPE24)", what: "En küçük temas boşluğu (mm) / kenar teması bayrağı." },
      { name: "Istf, Inacti", what: "Rijitlik hesap yöntemi; başlangıç penetrasyonunun ele alınışı. Boş = Radioss varsayılanı." },
    ],
  },
  {
    id: "ek",
    title: "4 · Crash → 4 Ek tanımlar",
    intro:
      "Parça rolü bütün parçaya uygulanır; buradaki kartlar bir bölgeye (Physical Group) ya da parçaya ek tanım ekler. " +
      "Kapalı kart tek satırla özetlenir (ör. “kutu_arka → rijit + 40 kg · rayda (yalnız x)”).",
    image: IMG("05-ek-tanimlar.png"),
    imageCaption: "Hazır kurulumlar ve dört ekleme kutusu (LS-DYNA karşılıkları açık).",
    items: [
      { name: "Hazır kurulum · Kızak testi", what: "Arka bölgeyi (adında “arka” olan) rijit + kütle yapar, hareket “rayda”. Kütle boş gelir — değer mühendisin." },
      { name: "Hazır kurulum · Ankastre kenar", what: "Kenar bölgesini (adında “kenar” olan) 6 serbestlikte kilitler." },
      { name: "Bölgeyi kilitle", what: "Seçili serbestlikleri kilitler (onay kutuları: Tx Ty Tz Rx Ry Rz; “Tamamen kilitle”, “Yalnız öteleme”).", when: "Plaka kenarı ankastre, kiriş uçları, simetri düzlemi, ROPS tabanı.", card: "/BCS" },
      { name: "Kütle / kızak", what: "Bölgeyi tek rijit cisim yapar, ana düğüme kütle ekler. Hareket: Rayda (yalnız çarpma ekseninde öteleme serbest), Serbest, Özel DOF. “İvmeyi kaydet” HIC kanalını açar.", when: "Kızak (crash box), impaktör, araç kütlesi temsili (direk testi uçları).", card: "/RBODY" },
      { name: "Sabit hızla it", what: "Hızı çözüm boyunca zorla sabit tutar (parça yavaşlamaz). Eksen, işaretli hız, başlangıç/bitiş (0 = sonuna kadar).", when: "ROPS yanal yavaş itme, kapı intrüzyonu silindiri, yarı-statik ezme.", card: "/IMPVEL" },
      { name: "Parçaya ayrı ilk hız", what: "Bir bölge/parçaya ayrı başlangıç hızı. Bu kart varsa 1 · Çarpma hızı hiçbir parçaya uygulanmaz.", when: "Parçalar farklı hızlarla geliyorsa (iki araç).", card: "/INIVEL" },
    ],
    gallery: [{ src: IMG("06-kizak-karti.png"), caption: "Kütle / kızak kartı açık: hedef çipleri, kütle, Rayda / Serbest / Özel." }],
  },
  {
    id: "uzman",
    title: "4 · Crash → Uzman ayarları",
    intro:
      "Eleman formülasyonu ve hourglass. Boş alan = OpenRadioss varsayılanı; başlık değiştirilen alanları özetler. " +
      "Son koşunun HG/IE oranı veri olarak görünür (genel ölçü: %5).",
    image: IMG("07-uzman.png"),
    imageCaption: "Kabuk mesh: /PROP/TYPE1 alanları ve hourglass katsayıları.",
    items: [
      { name: "Ishell / Ish3n", what: "Quad / üçgen kabuk formülasyonu.", card: "/PROP/TYPE1" },
      { name: "Ismstr", what: "Küçük/büyük şekil değiştirme formülasyonu." },
      { name: "N", what: "Kalınlık boyunca integrasyon noktası (0, 1 ya da 3…10)." },
      { name: "Hm / Hf / Hr", what: "Hourglass katsayıları: membran, düzlem dışı, dönme (0…0.05; varsayılan 0.01). Ishell 1–4'te etkili.", card: "/PROP/TYPE1" },
      { name: "Isolid / Ismstr / NIP / h (solid)", what: "Solid eleman formülasyonu, integrasyon noktası, hourglass viskozitesi (0…0.15; varsayılan 0.10).", card: "/PROP/TYPE14" },
      { name: "Hourglass nedir", what: "İndirgenmiş integrasyonlu elemanlarda enerji yemeyen sahte zikzak deformasyon. HG/IE yüksekse sonuç şüphelidir; katsayı ya da formülasyon değiştirilir (karar mühendisin)." },
    ],
  },
  {
    id: "hamkart",
    title: "Ham kart editörü",
    intro:
      "Formda olmayan bir sınır koşulu ya da malzeme kartını OpenRadioss sözdiziminde, mesh düğüm/eleman numaralarıyla " +
      "doğrudan yazmak için. 3 · Material ve 4 · Crash'teki “Ham kart editörü” satırından açılır (iki yer aynı metni düzenler). " +
      "Metin yorumlanmaz: starter deck'ine /END'den hemen önce aynen eklenir. Boşsa deck değişmez.",
    image: IMG("15-ham-kart.png"),
    imageCaption: "Editör ve “Kontrol et” sonucu: starter çıkışı, ID çakışmaları, üretilen deck envanteri.",
    items: [
      { name: "Sabit genişlik", what: "OpenRadioss alanları 10 karakter. Cetvel her 10 kolonda çizgi gösterir; Tab imleci bir sonraki alan başına götürür; alttaki satır imlecin satır / kolon / alan numarası." },
      { name: "Düğüm ID'lerini imlece ekle", what: "Viewport'ta Mesh → Düğüm modunda seçilen düğümler, deck'teki numaralarıyla (Gmsh düğüm no'su), sağa yaslı 10'luk alanlarda, satır başına 10 adet yazılır. 2. mertebe mesh'in ara düğümleri deck'te yoktur (solid TETRA4 köşe düğümleriyle yazılır).", dyna: "*SET_NODE_LIST satırları" },
      { name: "Eleman ID'lerini imlece ekle", what: "Mesh → Eleman modunda seçilen elemanlar, deck'teki numaralarıyla (Gmsh eleman no'su) aynı biçimde yazılır.", dyna: "*SET_SOLID / *SET_SHELL_LIST satırları" },
      { name: "Kontrol et", what: "Ham kartlı deck'i yalnız OpenRadioss starter'ı ile okutur (koşu yok, ~1 sn). Starter'ın ERROR / WARNING blokları aynen gösterilir; ham kartların deck'te başladığı satır yazılır. Yanında ID listesi: üretilen kartlarla aynı ID (çakışma), ham metinde tekrar eden ID, 900000 altındaki ID — “Satır n” tıklanınca imleç o satıra gider. Altta üretilen deck'in envanteri (düğüm/eleman sayısı ve aralığı, ad alanı başına kullanılan ID'ler). Metin sonra değişirse sonuç “eski” işaretlenir." },
      { name: "ID aralığı", what: "Ham kartlardaki kendi ID'leriniz (MAT, PROP, PART, GRNOD, BCS …) 900000 ve üstünde verilir; üretilen kartlar bu aralığı kullanmaz. /BEGIN ve /END yazılmaz (reddedilir)." },
      { name: "Kayıt", what: "Ham kart metni koşunun isteğinde saklanır; aynı koşu tekrar üretilebilir. Crash geçmişinde bu koşular “ham kart” etiketiyle görünür ve ML korpusuna varsayılan girmez (ML Stüdyo → Crash → Model'de “Ham kartlı koşuları dahil et”)." },
    ],
  },
  {
    id: "cikti",
    title: "4 · Crash → Çıktı ayarları (preprocess)",
    intro:
      "Koşudan ÖNCE deck'e yazılan kayıt ayarları: hangi eğriler ne sıklıkla kaydedilir, zaman adımı, kesitler. " +
      "Uzman ayarlarının altında, Çalıştır'dan önce; başlık varsayılandan farklı alanları özetler. " +
      "Koşudan sonra değiştirmek o koşuyu etkilemez. Filtre (CFC) post-process'tir: 5 · Sonuçlar'da uygulanır.",
    image: IMG("11-cikti.png"),
    imageCaption: "Çıktı ayarları 4 · Crash'te: kayıt aralığı, zaman adımı (kanallar ve kesitler aşağıda).",
    items: [
      { name: "TH aralığı / Animasyon", what: "Eğriler ve animasyon kareleri kaç ms'de bir (boş = süre/200, süre/20). Kısa tepe kaçıyorsa TH aralığı küçültülür.", card: "/ANIM/DT" },
      { name: "Zaman adımı (/DT, NODA/0, NODA/STOP, NODA/CST/0)", what: "Δt ölçekleme / Δt_min altına düşünce bildir, dur ya da kütle ekle (kütle ölçekleme)." },
      { name: "Rijit duvar kanalları", what: "FNX/FNY/FNZ normal, FTX… teğet kuvvet.", card: "/TH/RWALL" },
      { name: "Temas kanalları", what: "Temas çiftlerindeki kuvvet.", card: "/TH/INTER" },
      { name: "Parça kanalları", what: "IE, KE, HE, momentum, ağırlık merkezi, hız …", card: "/TH/PART" },
      { name: "Kesit kanalları + Kesitler", what: "Modelin içinden geçen sanal düzlem (M, M1, M2) — oradan geçen iç kuvvet/moment.", when: "S-kiriş, ROPS (dikmelerden kuvvet), Hopkinson giriş çubuğu.", card: "/TH/SECTIO" },
      { name: "Düğüm kanalları", what: "Seçili düğümlerin yer değiştirme / hız / ivmesi.", card: "/TH/NODE" },
    ],
  },
  {
    id: "sonuclar",
    title: "5 · Sonuçlar",
    intro: "Koşu durumu, skalerler, grafikler ve 3B animasyon. Değerler veridir; kabul eşiği mühendisin.",
    image: IMG("10-sonuclar.jpg"),
    imageCaption: "Çözülen koşu: skalerler + 3B deforme şekil (kendiliğinden açılır).",
    gallery: [{ src: IMG("10b-cfc.png"), caption: "Kuvvet grafiği altında post-process CFC: ham ve süzülmüş tepe yan yana." }],
    items: [
      { name: "Job", what: "İş kimliği · durum (pending / solved / failed / rad_only) · mesaj. “starter .rad” girdi dosyasının bağlantısı." },
      { name: "Hata #n (kırmızı bant)", what: "Koşu hatayla biterse durum failed (kırmızı) ve kodlu hata: #1 çözüm ıraksadı (enerji NaN; Radioss yine NORMAL TERMINATION yazabilir — eğri ve animasyon ıraksama anına kadar açılır), #2 starter hatası (ERROR ID'ler), #3 çözücü anormal sonlandı (çıkış kodu ≠ 0), #4 zaman aşımı, #5 OpenRadioss bulunamadı, #9 sınıflanmamış. Hatalı koşu DOE / ML korpusuna girmez." },
      { name: "Enerji · J grafiği", what: "İç enerji (deformasyonla yutulan), kinetik, hourglass, temas enerjisi, dış iş ve toplam enerji (IE + KE + dönme + HG − dış iş) zamana göre. Global TH sütunları; geçmişteki 📈 penceresinde de aynı seriler." },
      { name: "Enerji özeti", what: "İç / kinetik enerji son ve maks; hourglass son · HG/IE %; temas son · temas/IE %; dış iş son; enerji dengesi |ΔE|/E %. Değerler veridir; kabul eşiği mühendisin." },
      { name: "RWALL Fmax / impuls", what: "Rijit duvar tepe kuvveti (kN) ve toplam impuls (N·s). Kızakta impuls = m·Δv.", card: "/TH/RWALL" },
      { name: "Temas kuvveti", what: "Duvarsız modellerde kuvvet temastan okunur (contact_1_force…).", card: "/TH/INTER" },
      { name: "HIC15 / HIC36 / acc_peak_g", what: "Kafa yaralanma ölçütü ve tepe ivme — ivme kanalı (rijit gövde “İvmeyi kaydet”) varsa.", },
      { name: "Δt_min / Silinen eleman", what: "En küçük zaman adımı; /FAIL ile silinen eleman sayısı." },
      { name: "Kuvvet–zaman grafiği", what: "Rijit duvar / temas / kesit kuvveti (|F|, kN). Y ekseni adı + birim + ölçek; nokta = tepe değer ve zamanı. Kesikli çizgi = ortalama kuvvet: temas aralığında (gölgeli; |F| > tepenin %1'i, ilk–son örnek arası) impuls / süre. CFC eşi olan ham seriye tepe/ortalama işaretlenmez." },
      { name: "PNG / CSV (grafik başlığı)", what: "PNG: grafik 1400 px genişlikte resim (başlık, lejant, eksenler, tepe / ortalama, alttaki değerler; tema renkleriyle). CSV: eğri verisi, virgül ayraç + nokta ondalık; ortak zamanda t + seri sütunları, karşılaştırmada seri başına t + değer. Dosya adı başlıktan (kuvvet_kN.png). Kuvvet, ivme, enerji grafiklerinin hepsinde." },
      { name: "Filtre · CFC (post-process)", what: "Koşu bittikten sonra kayıtlı ham eğriden SAE J211 süzme (60, 180, 600, 1000): sınıfı seç, Uygula. Çözücü yeniden koşmaz; ham eğri korunur, süzülmüş eğri grafiğe ve tepe değerlerine eklenir (ör. ham 122 kN → CFC 60 65.4 kN).", when: "Kuvvet tepesi okumadan önce (60–600); kafa ivmesi / HIC için 1000." },
      { name: "3B animasyon", what: "Deforme şekil kareleri; renk alanı (ör. plastik şekil değiştirme), ▶ oynat, eksen görünümleri, ⤢ büyüt. Çözümden sonra kendiliğinden açılır; geçmişten ▶ ile tekrar açılır.", card: "/ANIM/DT" },
      { name: "Yönlü yer değiştirme uₓ / u_y / u_z", what: "Renk listesinde: düğüm konumu − ilk kare konumu (mm, işaretli, model eksenleri). Ölçek tüm karelerin min–max'ı." },
      { name: "Kare istatistiği", what: "Renk ölçeğinin altında, seçili skalerin o karedeki min / maks / ortalaması ve kaç eleman / düğüm üzerinden olduğu. Ortalama aritmetik (alan ağırlıksız); silinen eleman katılmaz." },
      { name: "Video indir (MP4 / WebM)", what: "Animasyonu baştan sona bir kez oynatıp 1280×720, 30 kare/s video dosyası indirir (crash_run<no>_<skaler>.mp4). Kayıt süresi = 3 s / hız; ekrandaki kutu boyutundan bağımsız. Görünüm, renk skaleri, deformasyon ölçeği ve hız ekrandaki gibi; üstte koşu no + t (ms) + skaler, altta renk ölçeği min–max yazılı. Biçim tarayıcıya bağlı: MP4 destekliyse MP4, değilse WebM." },
    ],
  },
  {
    id: "gecmis",
    title: "Crash geçmişi ve yeni vaka",
    intro: "Koşuların listesi ve hazır örnekten yeni vaka.",
    image: IMG("12-yeni-vaka.jpg"),
    imageCaption: "+ Yeni crash vakası: seçili senaryonun şeması ve parametreleri.",
    items: [
      { name: "▶ (animasyon)", what: "Koşunun 3B deforme şeklini viewport'ta açar." },
      { name: "Son çalışma (F5)", what: "Crash sekmesinde son açılan geometri / geçmişten yüklenen koşu tarayıcıda hatırlanır; sayfa yenilenince kendiliğinden açılır (koşuysa kurulumuyla, geometriyse sunucudaki mesh'iyle). \"Yeni Case Başlat\" sonrası kendiliğinden açılmaz; boş ekranda \"Son çalışmayı aç\" düğmesi. Panelde kaydedilmemiş düzenlemeler hatırlanmaz." },
      { name: "⤓ (yükle)", what: "Koşunun geometrisi + sunucudaki mesh'i + kurulumu (malzeme, çarpma / duvar, roller, temaslar, ek tanımlar) panellere yüklenir; düzenleyip yeniden koşulur. Mesh eleman boyutu kayıtlı değil (\"—\"); mesh yoksa yeniden mesh'lenir. Başarısız koşu da yüklenir." },
      { name: "Karşılaştır (sayfa)", what: "Geçmişte 2–6 koşu seçip \"Karşılaştır\": tam ekran tek sayfa (ESC / Kapat). Koşu kartları (geo, süre, durum, duvar Fmax); deforme şekil yan yana, ortak fiziksel zamanla (2'den fazla koşuda sol / sağ seçilir; kısa koşu kendi son karesinde \"koşu sonu\"); skaler tablosu; eğriler — seçilebilir eğri (kuvvet / ivme / enerji, t üst sınırı) + iç enerji, üst üste, PNG / CSV." },
      { name: "Ortak renk ölçeği / Kamera eşle", what: "Yan yana karşılaştırmada iki seçenek (varsayılan kapalı). Ortak renk ölçeği: iki pencere aynı skalerdeyse iki koşunun min–max birleşimi (lejantta \"(ortak)\"); farklı skalerde uygulanmaz, not yazar. Kamera eşle: birinde döndür / yakınlaştır / hazır görünüm → diğeri aynı kamerada." },
      { name: "📈 (eğri)", what: "Kuvvet–zaman eğrisini gösterir; karşılaştırmaya ekler." },
      { name: "⊘ (dışla)", what: "Koşuyu ML korpusundan dışlar (silmez)." },
      { name: "Karşılaştır", what: "En çok 6 koşunun eğrisini üst üste çizer." },
      { name: "Senaryoyu koş", what: "Geometri + mesh + malzeme + kurulum + OpenRadioss koşusu tek istekte; geometri, mesh, kurulum ve roller arayüze yüklenir, koşu 5 · Sonuçlar'da izlenir." },
    ],
    gallery: [{ src: IMG("13-gecmis.jpg"), caption: "Alt dock: crash geçmişi." }],
  },
  {
    id: "ml",
    title: "ML Stüdyo → Crash",
    intro: "Crash DOE ve vekil model (1.19). Ör. crash box 150 koşu: enerji R² 0.98, tepe kuvvet 0.95, ezilme 0.91, ortalama kuvvet 0.83 (5-katlı CV).",
    items: [
      { name: "DOE", what: "Taban senaryo + taranan alanlar (noktalı yol, ör. speed_m_s, geometry.wall, rigid_bodies.0.mass_kg) + LHS örnek sayısı. Sunucuda sırayla koşar, kaldığı yerden devam eder." },
      { name: "Model", what: "Hedef başına Random Forest; K-fold CV metrikleri (R², MAE, MAPE). Hedefler: tepe / ortalama kuvvet, yutulan enerji, ezilme." },
      { name: "Tahmin", what: "Girdi → hedef tahmini ± CV MAE; eğitim aralığı dışındaki girdiler işaretlenir." },
      { name: "Doğrulama", what: "Validasyon seti V1–V18 raporu (oranlar veri; eşik mühendisin)." },
    ],
  },
];

/** Hazır senaryolar (katalog, 15/15) — kullanılan özellikler. */
export const CRASH_SCENARIOS: DocScenario[] = [
  { id: "crash_box", title: "Crash box eksenel ezilme", template: "crash_box_shell", setup: "Kabuk kutu −x ile rijit duvara (x = 0); isteğe bağlı kızak (kutu_arka rijit + kütle).", features: ["Rijit duvar", "Hareketli rol", "Kütle / kızak (rayda)", "Öz temas TYPE7", "LAW2"], validation: "V1–V3: elastik dalga ρ·c·v·A, plastik plato σy·A, Wierzbicki–Abramowicz", reference: "RD-E 1700" },
  { id: "s_rail", title: "S-kiriş / ön kiriş", template: "s_rail_shell", setup: "Süpürülmüş kabuk tüp duvara; arka halka kızak, kılavuzlu (yalnız x).", features: ["Rijit duvar", "Kütle / kızak (rayda)", "Kesit kuvveti", "LAW2"], validation: "Momentum / enerji; ortalama kuvvet / düz tüp oranı (veri)", reference: "RD-E 0300" },
  { id: "pole_side", title: "Direk yan çarpması", template: "pole_beam_shell", setup: "Kiriş, silindirik rijit direğe (Ø254, /RWALL/CYL); uç halkaları rijit gövde + uç kütleleri.", features: ["Silindirik rijit duvar", "Kütle (uçlar)", "LAW2"], validation: "Ortalama direk kuvveti vs 4·Mp/L", reference: "Açık literatür" },
  { id: "head_impactor", title: "Kaput — kafa impaktörü (HIC)", template: "plate_ball_shell", setup: "Ø165 / 4.5 kg küre kabuk plakaya; küre rijit gövde + ivme kanalı.", features: ["Duvarsız", "Kütle (ivme kaydı)", "TYPE7", "HIC15 / CFC1000"], validation: "Kafa ivmesi ∫|a|dt = Δv", reference: "Yaya koruma (açık literatür)" },
  { id: "drop_test", title: "Düşme testi", template: "drop_box_shell", setup: "Kapalı kabuk kutu zemine (z = 0); H'den v = √(2gH); /GRAV.", features: ["Rijit duvar (zemin) ya da zemin plakası", "Yerçekimi", "TYPE7 (plaka)"], validation: "Serbest düşme temas anı, momentum / enerji", reference: "RD-E 0600" },
  { id: "door_intrusion", title: "Kapı intrüzyonu", template: "door_beam_shell", setup: "Uçları ankastre darbe kirişi; Ø305 silindir impaktör rijit gövde + sabit hızla itme. Duvar yok.", features: ["Duvarsız", "Bölgeyi kilitle (uçlar)", "Sabit hızla it", "TYPE7", "Serbest roller"], validation: "Kuvvet–intrüzyon; plato vs 8·Mp/L (veri)", reference: "FMVSS 214 mantığı" },
  { id: "plate_perforation", title: "Plaka delinme (rijit küre)", template: "plate_ball_shell", setup: "Kenarları ankastre plaka; küre rijit gövde + −z ilk hız; küre → plaka TYPE7.", features: ["Duvarsız", "Ankastre kenar", "Kütle (küre)", "TYPE7", "/FAIL"], validation: "V4 Timoshenko; V5 Recht–Ipson", reference: "RD-E 2600; Recht & Ipson (1963)" },
  { id: "taylor_bar", title: "Taylor çubuğu", template: "taylor_bar", setup: "Dolu silindir (solid, tet) rijit duvara.", features: ["Rijit duvar", "Solid /PROP/TYPE14", "LAW2"], validation: "V6: L1/L0 vs Wilkins–Guinan", reference: "Taylor (1948)" },
  { id: "hopkinson_bar", title: "Hopkinson çubuğu", template: "hopkinson_bar", setup: "Çarpıcı → giriş çubuğu; LAW1; kesit kuvveti Li/4'ten. Duvar yok.", features: ["Duvarsız", "LAW1", "TYPE7", "Kesit kuvveti"], validation: "V14: ρ·c·v0·A/2 platosu, darbe süresi 2·Ls/c", reference: "RD-E 0800" },
  { id: "blast_plate", title: "Patlama yüklü plaka", template: "blast_plate_shell", setup: "Kenarları ankastre kare plaka; Friedlander basınç darbesi.", features: ["Duvarsız", "Ankastre kenar", "Basınç yükü /PLOAD"], validation: "V15: A·∫p dt = momentum", reference: "Friedlander (açık literatür)" },
  { id: "bird_strike", title: "Kuş çarpması (SPH)", template: "blast_plate_shell", setup: "SPH kapsül kuş plaka merkezine.", features: ["SPH mermi", "Ankastre kenar"], validation: "Wilbeck: impuls m·v, süre L/v, ρ·A·v²", reference: "RD-E 4900" },
  { id: "underbody_blast", title: "Mayın / araç altı patlama", template: "blast_plate_shell", setup: "Ampirik PBLAST (zemin yansımalı) plaka altında.", features: ["Patlama /LOAD/PBLAST", "Ankastre kenar"], validation: "Hopkinson–Cranz ölçekleme", reference: "TM5-1300 / Kingery–Bulmash" },
  { id: "rops", title: "ROPS portal çerçeve", template: "rops_frame_shell", setup: "Tabanlar sabit; üst büküm rijit gövde + yanal sabit hızla itme; kuvvet dikme kesitlerinden.", features: ["Duvarsız", "Bölgeyi kilitle", "Sabit hızla it", "Kesit kuvveti"], validation: "V9: plato vs 4·Mp/H", reference: "ISO 3471 mantığı" },
  { id: "fops", title: "FOPS — tavana düşen cisim", template: "plate_ball_shell", setup: "Kabin tavanı (kenarlar sabit) üstüne rijit küre H'den düşer; /GRAV.", features: ["Duvarsız", "Ankastre kenar", "Kütle (küre)", "Yerçekimi", "TYPE7"], validation: "KE₀ = m·g·H", reference: "ISO 3449 mantığı" },
  { id: "bucket_rock", title: "Kepçe / taş darbesi", template: "bucket_rock_shell", setup: "Kavisli taban kenarları sabit; taş rijit gövde + −z ilk hız + ivme kanalı; taş → taban TYPE7.", features: ["Duvarsız", "Bölgeyi kilitle", "Kütle (ivme kaydı)", "TYPE7"], validation: "V16: ∫|a|dt = I/m", reference: "Açık literatür" },
];
