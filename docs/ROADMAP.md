# Yol haritası

Fazlar sırayla ilerler. Bir fazdan diğerine geçmeden önce agent kullanıcıdan onay ister.
Şu anki faz `CLAUDE.md` içinde "Mevcut faz" başlığında belirtilir — o dosya güncel kaynak.

## Faz 0 — Durability pilotu (CalculiX + Gmsh) — TAMAMLANDI

Hedef: Mimarinin tamamının (geometri import → mesh → backend → solver → post-process →
db) tamamen açık kaynak yığınla, hiçbir ticari CAE yazılımı/lisansı olmadan uçtan uca
çalıştığını kanıtlamak.

**Adımlar `docs/TESTING.md`'deki formatta ilerler — her biri ayrı onay noktası, kod
büyüklüğü değil, "yerelde tek bakışta görülüp test edilebilir olmak" sınırı belirler.**
Aşağıdaki liste bir kontrol listesi değil, sıralı mikro-adım planıdır; her satırın
yanındaki "→" o adımın yerel doğrulamasıdır.

### 0. Altyapı iskeleti
- [x] Boş FastAPI projesi, tek `/health` endpoint'i → `curl localhost:8000/health`
- [x] Boş React projesi, tek "merhaba" sayfası → `localhost:5173`'te sayfa açılır
- [x] PostgreSQL bağlantısı + boş bir tablo (Alembic ile) → `alembic upgrade head` çalışır,
      `psql`'de tablo görülür

### 1. Geometri import + önizleme
- [x] STEP/IGES upload endpoint'i (henüz işlemeden diske kaydeder) → dosya gönderilir,
      `/uploads` klasöründe görülür
- [x] Gmsh ile o dosyadan tessellation (glTF/STL) üretimi → aynı endpoint dosyayı işleyip
      `.glb`/`.stl` döndürür, yerel bir 3B görüntüleyicide açılıp geometri görülür
- [x] Frontend'de upload formu + three.js viewer → tarayıcıdan dosya seçilir, 3B model
      ekranda döner, tasarım o anki en sade halinde bile hizalı/temiz olmalı

### 1b. Geometri işleme operasyonları (import sonrası, mesh öncesi)
Her biri ayrı onay noktası — sırayla, birbirinin üstüne inşa edilir.
- [x] Üçgen→yüzey eşlemesi: tessellation çıktısına `triangle_to_face` bilgisi eklenir →
      backend loglarında/response'ta her üçgenin hangi Gmsh face tag'ine ait olduğu görülür
- [x] Frontend'de yüzey picking (tıklanan üçgenden face'i bulup vurgulama) → tarayıcıda bir
      yüzeye tıklanınca o yüzey renkli/vurgulu görünür
- [x] **(Roadmap dışı ek özellik)** Montaj/parça ayrımı: `triangle_to_part` eşlemesi +
      `part_count` — birden fazla ayrı katıdan (volume) oluşan STEP dosyalarında hangi
      üçgenin hangi parçaya ait olduğu ayırt edilir. Frontend panelinde parça sayısı
      gösterilir ("N yüzey, M parça bulundu"). Gerçekleşme sebebi: kullanıcı montaj
      desteğini sorguladı, altyapı zaten `getBoundary` ile kolayca çıkarılabildiği için
      aynı oturumda eklendi.
- [x] Dış yüzey (skin) listeleme endpoint'i → bir katı için tüm dış yüzeylerin
      listesi (id + alan + normal) JSON olarak döner
      (`GET /geometry/{stored_filename}/surfaces`, alan `occ.getMass`, normal
      `getNormal` ile — mesh çözünürlüğünden bağımsız kesin OCC değerleri)
- [x] **(Roadmap dışı ek özellik)** Kenar (edge/curve) listeleme endpoint'i →
      her kenarın id + uzunluk + parça bilgisi JSON olarak döner
- [x] **(Roadmap dışı ek özellik)** Nokta (vertex) listeleme endpoint'i →
      her köşe noktasının id + koordinat + parça bilgisi JSON olarak döner
- [x] Frontend'de seçim modu navbar'ı: Part / Surface / Edge / Point → aktif moda göre
      tıklama farklı seviyede seçim yapar
- [x] Yüzey kopyalama (`occ.copy`) → seçilen bir yüzey ayrı entity olarak çoğaltılır
- [x] Seçilen yüzeye isim/grup atama (Physical Group) → frontend + DB kalıcılığı
- [x] Geometry healing (`occ.healShapes` + silindirik delik doldurma)
- [x] Defeature: 2D/midsurface radyus kaldırma (seçim veya otomatik) → keskin köşe shell;
      solid fillet için AABB yolu da mevcut
- [x] Midsurface: parça bazlı otomatik (tüm ince cidarlar + fillet mid) + manuel 2 yüzey;
      kapalı köşe / C-kanal / eş-R fillet desteği

### 2. Mesh üretimi
- [x] Global mesh size + mesh üretimi: **3D tet (solid)** ve **2D shell (tri)** →
      backend `POST /geometry/{id}/mesh` (`element_size`, `dimension` 2|3); `.msh` +
      düğüm/eleman sayısı. Frontend: viewer sağında mesh paneli (boyut + 2D/3D + üret).
      2D yalnız orphan/midsurface yüzeylere; 3D solid volume. Mesh göster/gizle.
- [x] Eleman tipi seçimi: tet / quad / mix → mesh paneli droplist; shell'de quad
      varsayılan (recombine), tet→tri, mix→tri+quad; 3D'de tet / hex(quad) / mix
- [x] Frontend'de mesh'i (shaded + wireframe) önizleme → yüzey üçgenleri (2D shell /
      3D tet dış yüzeyi) yeşil dolu + siyah kenar; CAD mesh varken gizlenir; göster/gizle

- [x] Mesh kalite hesaplama: Jacobian + aspect ratio (native metriklerle) →
      `GET /geometry/{id}/mesh/quality?dimension=` minSJ + maxEdge/minEdge;
      mesh bar **Kalite** butonu
- [x] Mesh kalite hesaplama: skewness + warpage (custom) → aynı endpoint'e eklenir,
      bilinen kötü bir test mesh'inde (bilerek çarpık üretilmiş) yüksek değer çıktığı
      doğrulanır
- [x] Frontend'de kalite görselleştirme: kötü elemanları renkli vurgulama + histogram →
      viewer'da düşük kaliteli elemanlar kırmızı görünür, yanında bir histogram grafiği.
      Yazılım burada bir yorum/öneri üretmez — sayıyı ve görseli gösterir, karar mühendisin
- [x] Free edge kontrolü → shell mesh'te bilerek bir boşluk bırakılmış test parçasında,
      o boşluğun kenarları viewer'da vurgulanır
- [x] Node-to-node equivalence (tespit + birleştirme) → iki ayrı meshlenmiş parça birleşim
      yüzeyinde çakışan düğüm sayısı önce raporlanır, onaylanınca birleştirilip düğüm
      sayısındaki azalma terminalde görülür
- [x] Rigid body ataması (solver-özel, mesh'ten sonra): bir yüzey/delik + referans node
      seçilip "rigid body" olarak işaretlenir → üretilen `.inp`/`.rad` dosyasında ilgili
      kart (`*RIGID BODY` / `/RBODY`) göze görünür şekilde oluşur

### 2b. Malzeme kütüphanesi ve atama
- [x] `material` tablosu + migration, 3-5 malzemeyle seed (S235, S275, S355, 6061-T6,
      7075-T6) → `alembic upgrade head`; tipik/nominal değerler
- [x] Malzeme listeleme endpoint'i → `GET /materials` kütüphaneyi JSON olarak döner
- [x] Frontend'de malzeme seçici (kütüphaneden) → sol panelde geometri altında Malzeme
      menüsü; E / ν / ρ / Rp0.2 / Rm görünür
- [x] Volume/parça seçip malzeme atama → `POST /materials/assignments`; panelde
      **Malzeme ata** + Atamalar listesi (parça #N → malzeme)
- [x] Kullanıcı tanımlı malzeme girişi (kütüphane dışı) → form ile E/yoğunluk/akma
      girilir, `source="user_defined"` olarak kaydedilir
- [x] S-N eğrisi verisi: tahmini (Rm'den) vs kullanıcı girişi ayrımı →
      `PUT /materials/{id}/sn-curve`; frontend'de tahmini/test etiketi

### 3. Solver adaptörü (CalculiX) — BC ve yükler
- [x] Malzeme atamasının `.inp`'e yazılması: `*MATERIAL`/`*ELASTIC`/`*DENSITY` +
      `*SOLID SECTION` / `*SHELL SECTION` → `POST /geometry/{id}/solve`
- [x] Sabit/basit senaryo + ccx subprocess (kuruluysa) → `run_solver`; ccx yoksa .inp
      yine üretilir, mesajda uyarılır
- [x] BC kartları `.inp` içinde: fixed (`*BOUNDARY`), point/face CLOAD, pressure
      (2D: `*DLOAD P` / 3D: dağıtılmış CLOAD), displacement, sliding (`*TRANSFORM` +
      local normal fix), bearing (kosinüs), gravity (`*DLOAD GRAV`)
- [x] Frontend Solver paneli: tüm BC butonları (Fixed / CLOAD / Pressure /
      Displacement / Sliding / Bearing / Gravity / Rigid body) + parametre alanları + BC listesi +
      shell kalınlık + .inp üret/çöz
- [x] Parametrelerin forma bağlanması (Fx/Fy/Fz, |P|, U, normal, bearing ekseni, g)
- [x] Nokta/kenar/yüzey → node listesi ayrı rapor endpoint'i (`POST /geometry/{id}/mesh/nsets`).
      Solve içindeki NSET yazımı aynı; bu endpoint seçimi çözmeden raporlar.

### 4. Sonuçlar (deformation, von Mises, safety factor, modal)
- [x] Deformation okuma (`.frd`'den `U`) → terminalde maksimum deplasman değeri görülür
- [x] Von Mises stress hesaplama (gerilme tensöründen) → terminalde maksimum von Mises
      değeri görülür, viewer'da renk skalası ile gösterilir
- [x] Safety factor hesaplama (malzeme akma değeri girişiyle) → aynı akışa bir sayı daha
      eklenir, kritik (SF<1) bölgeler viewer'da vurgulanır
- [x] Modal analiz (`*FREQUENCY` step'i, ayrı bir analiz tipi seçeneği) → kullanıcı
      "modal" seçtiğinde farklı bir step üretilir, sonuçta doğal frekanslar listesi +
      seçilen moda ait şekil viewer'da animasyonlu/statik gösterilir

### 5. Job kuyruğu + durum takibi
- [x] Senkron çağrıyı asenkron job'a çevirme (basit runner, henüz Celery değil) →
      `POST /solve` `wait: false` ile hemen `run_id` + `pending` döner, `GET /runs/{id}`
      durumu gösterir. Testler `wait: true` (varsayılan) ile senkron kalır.
- [x] Frontend'de "çalışıyor... / bitti" durum göstergesi (polling) → sayfa job bitene
      kadar durumu günceller

### 6. Post-process (fatigue)
- [x] pyLife ile yorulma ömrü hesaplama (Adım 4'te üretilen gerilme verisinden) → akış
      bir "cycles" sayısı üretir. Statik tek yükte sentetik tam çevrim rainflow + S-N
      log-log interpolasyon (zaman serisi yok).
- [x] Frontend'de sonuç grafiği (basit bir bar/line chart) → tarayıcıda sayısal sonuç ve
      grafik görülür

### 7. Veritabanına kayıt + geçmiş
- [x] Her run'ın (girdi + sonuç) veritabanına yazılması → `psql` ile satır görülür
- [x] Frontend'de geçmiş analizler listesi → tarayıcıda önceki run'lar listelenir, birine
      tıklanınca sonucu tekrar gösterir

Çıkış kriteri: yukarıdaki tüm adımlar tek tek onaylanmış olacak ve bir kullanıcı tamamen
web üzerinden, lokal kurulum yapmadan (CAD/mesh/solver yazılımı olmadan) bir durability
analizi çalıştırıp sonucu görebiliyor olacak.

**Not:** Faz 1/2/3'ün planları da aynı mikro-adım mantığıyla, bu fazın somut kod yapısı
netleştikten sonra detaylandırılacak — şimdiden hepsini yazmıyoruz çünkü Faz 0'da
öğrenilecekler (örn. hangi adımın daha da bölünmesi gerektiği) sonraki fazların adım
boyutunu da etkileyecek.

## Faz 0.4 — Parametrik geometri kütüphanesi

Ön koşul: Faz 0 tamamlanmış olmalı.

**Bu faz neden var ve neden Faz 0.5'ten ÖNCE:** Faz 0.5'teki DOE/batch runner parametre
uzayını tararken yüzlerce geometri üretmek zorunda. Her geometri elle STEP yüklemeyi
gerektirdiği sürece parametrik tarama teknik olarak mümkün değil. Kütüphane, DOE'nin
ön koşuludur — kolaylık özelliği değil.

İkinci fayda: bu şablonların çoğu mukavemet derslerinin klasik örnekleri, yani
**kapalı form çözümleri var**. Analitik referans şablonla birlikte saklanırsa her
üretilen run otomatik olarak doğrulanır.

### Mimari kararlar

**İsimlendirilmiş bölgeler ZORUNLU.** Şablon yalnız geometri değil, yüzey/kenar/nokta
etiketlerini de üretir (`ankastre_uc`, `yuk_yuzeyi`, `delik_cidari`, `simetri_duzlemi`).

Gerekçe: gmsh yüzey etiketlerini geometriye göre numaralandırır. L=300 ile L=700
arasında "yüzey 3" farklı bir yüzeye denk gelebilir. İsimlendirme olmadan batch runner
BC'leri parametre değiştikçe YANLIŞ yere uygular ve bunu hata vermeden yapar — tüm veri
seti sessizce bozulur. (Aynı sınıftan bir hata Faz 0'da düğüm seviyesinde yaşandı:
CAD vertex id'si mesh düğüm numarası sanılıyordu.)

Bu etiketler `PhysicalGroup` tablosunda zaten var olan yapıyla saklanır.

**Geometri gmsh OCC ile üretilir, dış CAD çekirdeği eklenmez.** Kutu, silindir, boolean
işlemler ve fillet gmsh'in OpenCASCADE arayüzünde mevcut. Yeni bağımlılık gerekmez;
Faz 0'da STEP okumak için kullanılan aynı modül.

**Şablon = parametre şeması + kurucu fonksiyon + analitik referans (varsa) + etiketler.**
Veri olarak tanımlanır, koda gömülmez; böylece yeni şablon eklemek tek bir dosya
eklemekten ibaret olur ve frontend formu şemadan otomatik üretilir.

**STEP çıktısı indirilebilir olmalı.** Kullanıcı şablonu kendi CAD programında
açabilmeli — bu, üretilen geometrinin doğruluğunu bağımsız olarak kontrol etmenin
tek pratik yolu.

### Şablon listesi

Öncelik sırasına göre. İlk gruptakiler hem analitik çözümü olan hem de surrogate için
ilginç vakalar.

**Grup 1 — analitik çözümü olan temel vakalar**
- [x] Ankastre kiriş, dikdörtgen kesit (L, W, T) — Faz 0'da doğrulandı (`cantilever_beam`)
- [x] Basit mesnetli kiriş (orta noktadan ve yayılı yük) — `simply_supported_beam`
- [x] Delikli plaka (W, H, T, d) — gerilme yığılması, `Kt ≈ 3` (sonsuz plaka limiti) — `plate_with_hole`
- [x] Çekme deneyi numunesi (dogbone, ISO 6892 / ASTM E8 oranları) — `dogbone`
- [x] İçten basınçlı kalın cidarlı boru (Lamé çözümü) — `thick_walled_tube`
- [x] Burulmaya maruz mil (dairesel kesit, `τ = Tr/J`) — `torsion_shaft`

**Grup 2 — profil kesitleri**
- [x] I-kesit kiriş (h, b, tw, tf)
- [x] Kutu profil / dikdörtgen tüp
- [x] Dairesel tüp
- [x] L-köşebent

**Grup 3 — makine elemanları**
- [x] T-braket (kaburgalı ve kaburgasız) — `t_bracket`, 2026-09-25
- [x] L-braket, delikli bağlantı — `l_bracket_bolted` (ankastre delik yüzeylerinde)
- [x] Flanş (cıvata delikli) — `flange` (analitik yok)
- [x] Kademeli mil (çap geçişinde gerilme yığılması, fillet yarıçapı parametre) —
      `stepped_shaft` (omuz filleti geometride, Kt Peterson/Norton)
      Dördü OCC geometrisi + hacim testiyle doğrulandı (`test_templates_grup3.py`);
      ccx uçtan uca doğrulaması 2026-09-28'de (aşağıda 0.4.7). DOE/eğitim YOK —
      kapsam kararı: kiriş bitmeden başka şablona eğitim başlamaz.

**Grup 4 — çentikli/kritik vakalar**
- [x] Çentikli çubuk (U ve V çentik)
- [x] Kama kanallı mil

Grup 1 ve 4 surrogate için özellikle değerli: gerilme yığılması olan vakalar,
alan modelinin gerçekten öğrenip öğrenmediğini ayırt eden yerlerdir. Düzgün bir
kirişte her model iyi görünür.

### Adımlar

**0.4.1 — Şablon altyapısı** — `app/templates/` (base.py, service.py)
- [x] Şablon kayıt mekanizması (parametre şeması, kurucu, etiketler, analitik referans)
- [x] gmsh OCC ile STEP üretimi ve mevcut `Geometry` kaydına bağlama
- [x] `PhysicalGroup` ile isimlendirilmiş bölgelerin kaydı
- [x] Parametre doğrulama (negatif/dejenere değerler, `L ≥ 5T` gibi geometrik kısıtlar)

**0.4.2 — İlk şablon uçtan uca: ankastre kiriş** — `app/templates/cantilever_beam.py`
- [x] Tek şablonla tüm akış: üret → mesh → BC (isimlendirilmiş bölgeden) → çöz
- [x] Sonuç Faz 0'daki doğrulanmış değerlerle eşleşmeli (23.92 mm / 330.7 MPa) — `tests/test_templates.py`
- [x] Gerekçe: altyapının doğruluğunu bilinen bir cevapla kilitler

**0.4.3 — API**
- [x] `GET /templates` — şablon listesi ve parametre şemaları
- [x] `POST /templates/{id}/create` — parametrelerle geometri üretimi; `geometries.template_id` + `template_params` yazılır
- [x] `GET /geometry/{id}/step` — üretilen STEP'in indirilmesi

**0.4.4 — Frontend**
- [x] Şablon seçici (liste; ikon/önizleme yok)
- [x] Parametre formu — şemadan otomatik üretilir
- [x] Üretilen geometrinin mevcut 3B viewer'da gösterimi
- [x] "STEP indir" butonu

**0.4.5 — Analitik referans**
- [x] Şablona bağlı kapalı form çözüm fonksiyonu
- [x] Çözüm sonrası FEA ile analitik sonucun karşılaştırılması ve sapmanın gösterilmesi
- [x] Sapma eşiği aşılırsa uyarı — mesh yetersizliğini ya da BC hatasını erken yakalar

**0.4.6 — Grup 1'in tamamlanması**
- [x] Kalan Grup 1 şablonları, her biri analitik referansıyla
- [x] Her şablon için regresyon testi (parametre → beklenen sonuç aralığı)

**0.4.7 — Grup 3 ccx doğrulaması** — ✅ 2026-09-28 (DOE/eğitim yok, kapsam kararı)
Her şablon varsayılan parametre + varsayılan BC, S235, es = 0.8 × karakteristik
uzunluk, C3D10; delikli/filletli olanlarda `HighOrderOptimize` açık. Hepsi
yakınsadı.

| şablon | düğüm | u_max FEA / analitik | σ FEA (maskeli) / analitik | not |
|---|---|---|---|---|
| T-braket | 7 528 | 0.236 / 0.233 mm (+1.7%) | 53.9 / 58.6 MPa (−8%) | plaka konsolu referansı tutuyor |
| T-braket, kaburgalı | 8 220 | 0.076 / — | 70.9 / — | kaburga 3× sertleştiriyor; analitik yalnız kaburgasız (belgeli) |
| L-braket, delikli | 6 677 | 1.461 / **1.57** (−7%) | 93.7 / 93.8 MPa | salt konsol formülü 0.536 mm diyordu (2.7× yanlış) → dik bacak dönmesi eklendi |
| Flanş | 7 948 | 0.0066 / — | 13.3 (ham 38.9) | analitik yok; delik kenarı yığılması ham tepede |
| Kademeli mil | 103 575 | 0.0561 / 0.0520 (+8%) | 55.1 / 64.9 (Kt) (−15%) | L1/D1 = 2, kiriş kabulü zayıf; fillet es = 0.8r ile tam çözülmüyor (kök filleti dersi) — DOE öncesi yerel inceltme + yakınsama ölçümü şart |

Run'lar DB'de: "grup3 dogrulama …" (1460–1464).

### Faz 0.5 ile ilişkisi

DOE (0.5.4) doğrudan bu kütüphaneyi kullanır: parametre uzayı şablonun kendi
şemasından gelir, BC'ler isimlendirilmiş bölgelere uygulanır, analitik referans
her run'ı otomatik doğrular. Kütüphane olmadan 0.5.4 yazılamaz.

### Çıkış kriteri

Kullanıcı hiçbir dosya yüklemeden, arayüzden bir şablon seçip parametrelerini girerek
geometri üretebiliyor; üretilen geometrinin isimlendirilmiş bölgelerine BC
uygulanabiliyor; sonuç analitik referansla karşılaştırılıyor; STEP indirilebiliyor.

## Faz 0.5 — Surrogate veri altyapısı ve alan modeli (durability)

Ön koşul: Faz 0 tamamlanmış ve sayısal olarak doğrulanmış olmalı; Faz 0.4
(parametrik geometri kütüphanesi) en az Grup 1 şablonlarıyla hazır olmalı —
DOE parametre uzayını şablonlardan alır, elle STEP yüklemekle tarama yapılamaz.

**Bu faz neden var:** Faz 4 surrogate'i "birkaç yüz sonuç birikmiş olmalı" ön koşuluyla
başlıyor ama o sonuçları üretecek mekanizmayı kendi listesinin ilk maddesi olarak
tanımlıyor — liste kendi ön koşuluyla döngüye giriyor. Ayrıca Faz 4'ün orijinal hedefi
(Random Forest + skaler metrikler) bu projenin amacını karşılamıyor: amaç tam bir FEA
aracı gibi davranmak, yani **alan çıktısı** (3B kontur, deformasyon animasyonu) üretmek.
Tek bir skaler maksimum değerden kontur çizilemez.

Bu faz veri üretim altyapısını kurar ve durability için alan surrogate'ini eğitir.
Faz 1/2/3 solverları eklendikçe aynı altyapı yeniden kullanılır.

### Mimari kararlar (değiştirilmeden önce tartışılmalı)

**Eleman tipi SABİT, eleman boyutu PARAMETRE.** 3D'de tet10, 2D'de quad — ANSYS'in
varsayılanlarıyla aynı (SOLID187 / shell). Eleman boyutu bilinçli olarak taranır, çünkü
mesh etkisini çalışmak bu projenin hedeflerinden biri. Sonuç: düğüm sayısı run'dan
run'a DEĞİŞİR.

**Değişken düğüm sayısı ⇒ mesh graf olarak işlenir (GNN / neural operator).**
PCA/POD alternatifi ELENDİ: sabit boyutlu vektör gerektirir, yani sabit topoloji.
Geometri ya da eleman boyutu değiştiği anda uygulanamaz. GNN'de mesh zaten graftır;
düğüm sayısı ve BC yerleşimi serbestçe değişebilir.

  * Düğüm girdileri: koordinat (x,y,z), BC bayrakları (sabit mi — kabukta 1..6 / solidde
    1..3, üzerinde yük var mı, yük bileşenleri), malzeme (E, ν, ρ), kabuksa kalınlık
  * Düğüm çıktıları: deplasman vektörü (u,v,w) ve von Mises
  * Skaler metrikler (maks. deplasman/gerilme) alandan TÜREVDİR, ayrıca modellenmez

**Depolama üç katmanlı.** `.inp` SAKLANMAZ — veritabanındaki `bcs`, `element_size`,
`element_scheme`, `materials_snapshot` alanlarından birebir yeniden üretilebilir.
`.frd` üretilemez, o çözümün kendisidir.

| Katman | Format | Amaç |
|---|---|---|
| Görselleştirme | preview JSON | arayüz (zaten mevcut) |
| Eğitim | `.npz` float32 | hızlı yükleme, rastgele erişim |
| Arşiv | `.frd.gz` | ileride farklı çıktı gerekirse yeniden çözmemek için |

Ölçüm (7205 düğümlü tet10 referans vakası): ham `.frd` ~5.4 MB/run, gzip ~0.7 MB,
eğitim `.npz` ~0.72 MB. 20.000 run ≈ 28 GB. Ham bırakılırsa ≈ 108 GB.

**Kayıplı sıkıştırma (femzip vb.) KULLANILMAZ.** Görselleştirme için sorun değil ama
eğitim etiketi olarak tehlikeli: modelin hatasıyla sıkıştırmanın hatası birbirine karışır
ve modelin gerçek doğruluğu ölçülemez hale gelir. gzip kayıpsızdır, bu kısıtı taşımaz.

### Adımlar

Her adım tek başına doğrulanabilir ve bir sonraki adıma geçmeden önce test edilir.

**0.5.1 — Doğrulama vakasının regresyon testi olarak sabitlenmesi**
- [x] 50x10x500 / 500N / S235 vakası uçtan uca test olarak yazılır (3D solid, 2D kabuk, modal)
- [x] Beklenen değerler ve tolerans: 3D 23.92 mm, 2D kabuk 23.6 mm, modal ilk 6 frekans
- [x] Gerekçe: bu oturumda düzeltilen yedi sessiz hata (tet10, kabuk dönme DOF'u, kabuk
      kalınlığı, .frd averaging, node BC çözümlemesi, node CLOAD bölünmesi, kabuk yüzey
      gerilmesi) yalnız birim testlerle yakalanamazdı — hiçbiri hata fırlatmıyordu

**0.5.2 — Depolama katmanı**
- [x] Çözüm sonrası `.frd` → gzip
- [x] Çözüm sonrası `.npz` üretimi (düğüm girdileri + çıktıları + bağlantı)
- [x] `.inp` saklamayı bırak (DB'den yeniden üretilebilir olduğunu doğrulayan test)
- [x] Mevcut run'ları yeni formata taşıyan tek seferlik betik

**0.5.3 — Veri seti dışa/içe aktarma**
- [x] `GET /dataset/export`, `POST /dataset/import`, `GET /dataset/summary`
- [x] Arşiv `.frd.gz` + `.train.npz` + şablon kökenini taşır; UI panel mevcut

**0.5.4 — DOE / batch runner**
- [x] Parametre uzayı tanımı: geometri (L/W/T), eleman boyutu, malzeme, BC senaryosu
- [x] Latin Hypercube örnekleme (NumPy McKay LHS; tohumla yinelenebilir)
- [x] BC senaryoları da taranır — aynı geometriye farklı yerlerden farklı yükler.
      Geometri çeşitliliği tek başına yetmez, model BC'ye göre alan üretmeyi öğrenmeli
- [x] Geometri üretimi Faz 0.4 şablon kütüphanesinden (elle yükleme yok)
- [x] BC'ler isimlendirilmiş bölgelere uygulanır — parametre değişince kaymaması için
- [x] Kuyruk + ilerleme takibi, hatalı run'ın toplu işi durdurmaması
- [x] Yeniden üretilebilirlik: tohum (seed) ve parametre kaydı DB'de

**0.5.4 eki — mesh çözünürlüğü ve malzeme taraması**
- [x] `DoeSpec.element_ratio`: eleman boyutu = oran × şablonun karakteristik
      uzunluğu (`GeometryTemplate.characteristic_length`). Gerekçe ölçüldü:
      ankastre kirişte mutlak 6–14 mm ile aynı fizik %9.6–%21.8 gerilme sapması
      veriyor ve oran 1.75'e çıkan örnek mesh yüzünden uyarı tetikliyor.
- [x] 12 şablona karakteristik uzunluk + önerilen oran aralığı
- [x] Çoklu malzeme: LHS kesikli boyut dengeli dağıtıyor (200 örnek, 2 malzeme → 100/100)

**0.5.5 — Küçük veri seti ve veri kalitesi doğrulaması**
- [x] Kalite seti her şablon için kurulabilir (analitiği olan 12 şablon);
      aralıklar şablona özgü ve sabit — set bir referanstır, aynı tohum aynı
      200 örneği üretir
- [x] ~200 run üret — kiriş 200 (study 3, korpus `kiris-v2` 192), plaka 198
      (study 5, `plaka-v1`), NLGEOM kiriş 150 (study 6, `kiris-nlgeom-v1`)
- [x] Analitik kontrol: kiriş ailesinde kapalı form çözüm bilindiği için her run'ın
      sapması ölçülür — bu, veri üretiminin kendisinde hata olup olmadığını gösterir
- [x] Aykırı değer taraması (yakınsamamış çözüm, mekanizma, dejenere mesh)

**0.5.6 — Skaler baseline (model hedefi DEĞİL, boru hattı testi)**
- [x] Random Forest ile maks. deplasman/gerilme tahmini
- [x] Amaç: veri boru hattının sağlamlığını ucuza doğrulamak. Skaler surrogate bu
      projenin hedefi değildir — alan çıktısı olmadan FEA aracı yerine geçmez

**0.5.7 — Alan modeli (GNN)**
- [x] Mesh-graf veri yükleyici (`.train.npz`; PyG yok — Codespace disk sınırı, NumPy GNN)
- [x] Baseline mimari (MeshGraphNet benzeri encode-process-decode)
- [x] Eğitim: düğüm başına deplasman + von Mises
- [x] Değerlendirme: alan bazlı hata (düğüm başına RMSE) VE skaler hata (maks. değerler)
- [x] Mesh yakınsama davranışı: model farklı eleman boyutlarında ne yapıyor

**0.5.8 — Ekstrapolasyon koruması**
- [x] Girdi eğitim uzayının dışındaysa tahmin "uzay dışı" olarak işaretlenir
- [x] Gerekçe: ağaç tabanlı modeller uzay dışında SABİT bir değer döndürür ve bunu
      hata vermeden yapar. Ölçülen örnek: eğitim aralığı dışındaki bir kiriş için
      gerçek 2976 mm iken model 109 mm verdi (%96 hata, hiçbir uyarı yok). Bir
      mühendislik aracında sessiz ve güvenli görünen yanlış cevap kabul edilemez

**0.5.9 — Tahmin endpoint'i ve arayüz**
- [x] `POST /surrogate/predict` — alan çıktısı döner
- [x] Mevcut viewer ile aynı kontur/animasyon yolu kullanılır (preview JSON şeması)
- [x] Arayüzde "hızlı tahmin" ile "tam çözüm" görsel olarak AYIRT EDİLİR; tahmin
      olduğu ve hata payı ekranda görünür

### Bilinen riskler

* **GNN araştırma sınırında.** Ticari örnekleri var (Neural Concept, PhysicsX,
  Nvidia PhysicsNeMo) ama kapalı form garanti yok. 0.5.6'daki skaler baseline, alan
  modeli beklendiği gibi çalışmazsa elde kalan sonuç olur.
* **Veri hacmi.** Alan modeli için birkaç yüz değil binlerce run gerekir.
* **Donanım.** GPU gerekir; Codespace ücretsiz katmanı eğitim için yetmez.
* **Genelleme sınırı.** Eğitim hangi geometri ailesinde yapıldıysa model orada
  güvenilirdir. Tamamen farklı bir parça tipi yeni veri ve yeniden eğitim ister.

### Çıkış kriteri

Doğrulanmış bir geometri ailesinde, eğitim uzayı içindeki bir tasarım için surrogate
alan tahmini üretebiliyor; tahmin arayüzde kontur ve animasyon olarak görüntülenebiliyor;
hata payı ölçülmüş ve ekranda gösteriliyor; eğitim uzayı dışındaki sorgular tahmin
üretmek yerine işaretleniyor.

## Faz 0.6 — Doğrusal olmayan davranış ve sonuç güvenilirliği

**Neden bu faz:** Faz 0–0.5 boyunca her çözüm doğrusal elastik, küçük deformasyon
ve `*STATIC` ile yapıldı. Bu varsayımların sınırına birkaç yerde zaten değiyoruz
(aşağıda) ve surrogate'in öğrendiği hedeflerin bir kısmı mesh'ten bağımsız değil.
Faz 1'e (crash) geçmeden önce bu tarafın sağlama alınması gerekiyor; crash zaten
doğrusal olmayan bir problem ve buradaki altyapıyı kullanacak.

### Mimari kararlar

- **Yakınsama denetimi diğer her şeyden önce gelir.** Doğrusal statikte çözüm
  daima "yakınsar", bu yüzden bugün risk düşük. NLGEOM veya plastisite açılır
  açılmaz yarı yakınsamış çözümler üretilir ve mevcut hat bunları geçerli
  eğitim verisi sayar — kimse kontrol etmiyor. Sessiz veri zehirlenmesinin
  en olası yolu bu.
- **Tekil gerilme hedefi surrogate'i bozar.** Ankastre köşedeki von Mises
  yakınsamaz; mesh sıklaştıkça artar. Düğüm başına von Mises ile eğitilen bir
  GNN, tekillik çevresinde fiziği değil MESH'i öğrenir. Hedefin kendisi
  mesh'ten bağımsız olmalı.
- **CalculiX'te arc-length (Riks) yok.** Limit yük civarında yük kontrollü
  çözüm yakınsamaz; çare deplasman kontrolü. Bu bir solver kısıtıdır,
  çözüm ayarıyla aşılamaz.
- **Doğrusal olmayan koşuda analitik referans geçersizleşir.** Kapalı form
  çözümler küçük deformasyon + elastik varsayar. Karşılaştırma bu koşularda
  ATLANMALI (uyarı vermek yerine "geçerli değil" demeli), yoksa kalite raporu
  yanlış alarm üretir.

### Bilinen sınır durumları (ölçüldü)

- Doğrulama vakası: 500 mm kiriş, 24 mm uç deplasmanı = açıklığın %4.8'i.
  Küçük deformasyon varsayımının sınırında; NLGEOM ile sonuç birkaç yüzde
  daha rijit çıkar. Kalite setinde yük −800 N'a kadar taranıyor, yani bu
  sınırı aşan örnekler ÜRETİLİYOR ve analitik referans sessizce geçersiz hale
  geliyor.
- Ankastre köşede VM sapması, mesh oranı sabitken bile geometriyle %6.7–%12.8
  arasında geziyor (ölçüm: PR "oranlı mesh"). Kalanı tekillikten; mesh
  ayarıyla kapatılamaz.

### Adımlar

**0.6.1 — Yakınsama denetimi (önce bu)** — ✅ 2026-09-19
- [x] CalculiX `.sta` / `.cvg` dosyalarının okunması: artım sayısı, cutback,
      son yakınsamış artım, iterasyon sayısı (`parse_ccx_sta`)
- [x] `AnalysisRun`'a yakınsama özeti (`_solver_converged`, `_n_increments`, `_n_cutbacks`)
- [x] Yakınsamamış / kısmi çözüm `solved` sayılmaz; korpus kapısı `not_converged`
- [x] Regresyon testi: gerçek ccx ile bilerek yakınsamayan tek-eleman vaka

**0.6.2 — Tekillik ve mesh'ten bağımsız gerilme hedefi** — ✅ 2026-09-24/25 (sonuç plandan farklı)
- [x] Şablonlara fillet parametresi: kiriş kök filleti (`root_fillet` + duvar bloğu),
      kademeli mil omuz filleti. Ölçüm: filletli kirişte tepe gerilme global
      mesh'le yakınsamıyor, yerel inceltme ister → DOE'de kullanılmadı
- [x] Hot-spot ekstrapolasyonu: uygulandı ve **ölçümle elendi** (en gürültülü hedef)
- [x] `scalars`'a tepe (`max_von_mises`), kısıt maskeli (`max_von_mises_away`) ve
      tepe merkezli (`max_von_mises_near_peak`) yazılır; mesh duyarlılığı ölçüldü
- [x] Mesh yakınsama çalışması (kiriş 8 basamak, plaka 5): tepe yakınsamıyor
      (%5.6 gürültü, +%10 sapma), maskeli yakınsıyor (%1.2, −%0.8)
- [x] Surrogate hedefi `max_von_mises_away` (kirişte en iyi, hibrit MAPE %0.6);
      plakada ham tepe zaten yakınsıyor (delik kenarı tekil değil); tepe kayıtta

**0.6.3 — Büyük deformasyon (NLGEOM)** — ✅ 2026-09-25/27
- [x] `*STEP, NLGEOM` + artım kontrolü (`nlgeom`, `n_increments`)
- [x] Seçim: çözüm panelinde NLGEOM anahtarı; ön kontrol u/L > 0.10 ise "NLGEOM ile
      çözülsün mü?" sorusu (karar kullanıcının); `POST /surrogate/screen`
- [x] Doğrulama: α = FL²/EI = 1 kirişte Bisshopp–Drucker kesin çözümüyle %0.2
      (`test_nlgeom.py`)
- [x] Korpus NLGEOM'da lineer analitik kapısını kapatır, u/L kapısı 0.5
- [x] DOE ön elemesi u/L alt/üst sınırı; korpus `wrong_kinematics` ayrımı

**0.6.4 — Plastisite**
- [x] Malzeme modeline pekleşme eğrisi — `*PLASTIC` izotropik (2026-09-28).
      Kütüphanede eğri yok; Re/Rm/A%'den iki noktalı gerçek gerilme/şekil
      değiştirme (`materials/plasticity.py`; KABUL: A% tekdüze uzama yerine,
      belgeli). `SolveRequest.plasticity` (varsayılan kapalı, .inp eskisiyle
      birebir); açıkken artımlı yükleme (NLGEOM'suz da). Korpus `_plastic`
      bayrağıyla ayırır. Ölçüm (kiriş 500×10×50 S235, es=8): 450 N fark yok,
      650 N sehim +31%, 800 N çökme (535 mm), 1500 N çözücü 0.888 yükte durdu
      (limit yük — yük kontrolü bulamaz, sıradaki madde). Testler:
      `test_plasticity.py` (7, biri gerçek ccx)
- [x] Deplasman kontrollü yükleme — 2026-09-30. `displacement` BC zaten vardı;
      eksik olan tepki kuvvetiydi: artımlı çözümlerde `*NODE FILE U, RF`,
      `.frd` FORC bloğu okunur, sabit düğümlerin RF toplamı = uygulanan yük.
      Doğrulama: lineer kirişe −20 mm → tepki 418 N (3EIu/L³ = 420).
      Plastik kirişe −120 mm → tepki platoya oturur: **limit yük 704 N**
      (rijit-plastik 587, pekleşmeyle üstü); yük kontrolünde 1500 N'da
      ıraksayan vaka deplasman kontrolünde çözülüyor. Geçmiş
      `curves.reaction_history` (artım zamanı, tepki, u_max, PEEQ).
- [x] Yeni hedef skalerler — `max_peeq` (`*EL FILE PEEQ`, düğüme ortalanmış),
      `reaction_force_n/fx/fy/fz`, `limit_load_n`, `limit_load_time`,
      `limit_load_factor` (= limit / ilk akma anındaki tepki; kiriş 1.68).
      Surrogate hedefi olarak eklenmedi — plastik korpus yok (kapsam kararı).
- [x] Doğrulama: dogbone +0.3 mm çekme, plastik: ölçü kesiti nominal gerilmesi
      238.5 MPa (akma 235 + hafif pekleşme; elastik çözüm 538 MPa derdi).
      **Bu doğrulama gerçek bir hata buldu:** şablon kurulumundaki OCC yüzey
      etiketleri STEP yeniden okununca kutu dışı geometrilerde değişiyordu —
      dogbone'da sabitleme yan yüzeye, çekme fillet'e gidiyor, σ 39 GPa
      çıkıyordu (kirişte numaralar tesadüfen aynıydı). `build_template` artık
      bölgeleri yazılan STEP'i yeniden okuyarak bulur; 16 şablonluk regresyon
      testi (`test_region_tags_match_reimported_step`). Testler:
      `test_plasticity.py` (13, dördü gerçek ccx)
- [x] İsteğe bağlı açık pekleşme tablosu: `SolveRequest.plastic_curve`
      ([[σ_true, ε_p], …]) kütüphane türetmesini geçersiz kılar; panelde giriş

**0.6.5 — Surrogate tarafının uyarlanması** — ✅ 2026-09-27 (kiriş)
- [x] Eğitim verisinde `_solver_converged`, `_analysis_type`, `_nlgeom` bayrakları;
      lineer ve NLGEOM AYRI modeller (`uploads/models/<şablon>/[nlgeom/]`),
      NLGEOM istenip yoksa lineere düşmez. Kiriş NLGEOM hibrit holdout u_max MAPE %0.49
- [x] Ekstrapolasyon: reddedilmez, `domain_violations` ile hangi girdinin dışarıda
      olduğu döner (karar kullanıcının); tek malzemeli korpusta sabit sütun
      katsayı patlaması düzeltildi

**0.6.6 — Roadmap dışı eklenenler (2026-09-25 … 28)**
- [x] ML Stüdyo paneli: 1 · Model / 2 · Tahmin / 3 · Eğitim; toplu tarama
      (`/surrogate/predict/sweep`); Tahmin vs FEA doğrulama tablosu (`/surrogate/validate`)
- [x] Akma kontrolünde gerilme kaynağı seçimi (otomatik / maskeli / ham tepe)
- [x] WeWeb bağlantısı: Bearer API anahtarı, `users` + `geometries.owner_id`,
      `AUTH_REQUIRED`, CORS; `scripts/create_api_key.py`
- [x] Testler ayrı `cae_test` veritabanında; model yedeği `scripts/backup_models.py`
- [x] GNN alan modeli: mimari taraması yapıldı, ölçüt tutmadı → "prototip" etiketi,
      ürün dışı (bkz. TODO 1.3c)
- [x] gmsh `HighOrderOptimize` anahtarı (varsayılan kapalı)

### Çıkış kriteri

Yakınsamamış hiçbir çözüm eğitim verisine giremiyor; tekil olmayan (hot-spot)
gerilme hedefi mesh yakınsaması gösteriyor; NLGEOM ve plastik koşular
doğrulanmış referanslarla eşleşiyor.

## Faz 1 — Crash analizi (OpenRadioss + Gmsh)

Ön koşul: Faz 0 tamamlanmış olmalı ve kullanıcı onayı alınmalı.

**İzolasyon (zorunlu):** Faz 1, Faz 0 durability / modal / surrogate kodunu
kırmadan paralel yürür. Yeni `OpenRadiossAdapter` + crash'e özgü mesh export /
post-process; mevcut CalculiX `SolverAdapter`, `/solve` statik-modal akışı,
DOE kalite seti ve `/surrogate/*` bu fazda refaktör edilmez. Geometri
import (STEP/IGES, Gmsh tessellation) ortak kalabilir. Crash UI ayrı bir
bölüm/sekmedir, mevcut Results/surrogate görünümünün üzerine yazılmaz.
Regresyon: mevcut `test_reference_validation`, `test_templates*`,
`test_doe`, `test_surrogate` yeşil kalmak zorundadır.

**Solver kaynağı (2026-10-02):** OpenRadioss'un resmi GitHub deposu ve sürüm
paketleri 29 Eyl – 1 Eki 2026 arasında yayından kalktı; Siemens projeyi
başvuruyla girilen "Simcenter Radioss R&D Program" (shared source) altına aldı.
Elimizdeki çözücü, Docker Hub'daki `dheiny/openradioss-solver:1.0.37` imajındaki
son AGPL ikilileri (Copyright 1986-2026 Altair, AGPL v3; `latest-20260728`
derlemesi). AGPL geri alınamaz → kullanım meşru; yama/yeni sürüm GELMEYECEK.
Yerel geliştirme: Docker Desktop (WSL2) imajı `simsurrogate-openradioss:1.0.37`,
`OPENRADIOSS_DOCKER_IMAGE` ile çağrılır (bkz. `backend/docker/openradioss/`).
Codespace kurulum betiği artık çalışmaz; imaj Docker Hub'dan kalkarsa diye
`docker save` yedeği alınmalı (vendor/, git dışı). Ayrıntı: `LICENSING.md`.

**1.1–1.9 (2026-09-14, tek PR):** adaptör, mesh export, bariyer, post-process
(enerji, duvar kuvveti, HIC), websocket ilerleme, Crash sekmesi — hepsi
solver'sız (mock) yazıldı.
- [x] `OpenRadiossAdapter` (Radioss block format `.rad` starter + engine)
- [x] Gmsh mesh export → `/NODE`, `/TETRA4`
- [x] Bariyer parametreleri (hız, açı, rijit duvar) → `/INIVEL`, `/RWALL/PLANE`
- [x] OpenRadioss kurulumu — Docker imajı (yukarıdaki not)
- [x] Post-process: time-history → enerji, duvar kuvveti, ivme/HIC
- [x] Websocket ilerleme takibi
- [x] Frontend/backend ortak; crash ayrı sekme, ayrı iş klasörü (`uploads/crash/<uuid>`)

**1.10 — İlk gerçek çözüm: kutu profil + rijit duvar** — ✅ 2026-10-02
Kutu profil 300×50×40, t = 3 mm, S235 (LAW2, Isolid 1), 3 mm tet (80 686
düğüm), 10 m/s, 4 ms. Starter 0 hata / 0 uyarı; engine normal bitiş,
79 825 çevrim, 333 s (4 iş parçacığı). Enerji dengesi hatası %0.4;
KE_max 59.3 J = ½·1.187 kg·(10 m/s)²; IE_son 55.4 J; duvar tepe kuvveti
14.5 kN. İş: `uploads/crash/d4980c0e…`. İlk starter listing'i 10 hata
veriyordu — deck 2022 kart düzenine çekildi (birimler /BEGIN'de, LAW2 beş
satır, TYPE14 üç satır, INIVEL tek satır, RWALL M/M1, TH alanları 10 kar.);
birim sistemi kg–mm–ms (GPa, kN, J, mm/ms). `th_to_csv` engine sonrası
çağrılıyor; TH/RWALL sütunları adsız ("var 25…") geldiği için grup
başlığından sırayla eşleniyor.
- [ ] Crash sekmesinden aynı koşu (UI doğrulaması), çıktı dosyası temizliği
      (A001…A021 + .rst ≈ 95 MB/iş; anim sayısı/rst saklama ayarı)
- [ ] Zaman adımı / kütle ölçekleme kartı (`/DT/NODA/CST`) — 80k düğüm
      tet'te 5e-5 ms adım, 4 ms için 5.5 dk; kabukla (1.13) düşer

**Sonraki mikro-adımlar (her biri ayrı onay):**
- 1.11 Çok parçalı deck: parça başına `/PART` + `/PROP` + `/MAT`; mesh
  export'un parça kimliğini taşıması
- 1.12 Temas: `/SURF` + `/INTER/TYPE7` (master yüzey – slave düğüm) ve
  TYPE24; UI'da kontakt kartı (parçalar, sürtünme, gap, rijitlik)
- 1.13 Kabuk prop (`/PROP/TYPE1`) + kalınlık; ince plaka/kutu crash'i
  solid yerine kabukla
- 1.14 Malzeme kartları: LAW36 tablo, Johnson-Cook hız/sıcaklık terimleri,
  `/FAIL`; parça başına kart editörü
- 1.15 Çıktı kartları (`/SECT`, `/TH` seçimi), zaman adımı kontrolü
- 1.16 Crash run'larının kendi tablosuna kaydı, geçmiş ve karşılaştırma
- 1.17 Crash şablonu + DOE + korpus + vekil model (`ml/crash/`, durability
  kodundan bağımsız)

## Faz 2 — Kompozit modelleme (CalculiX + OpenRadioss üzerine katman)

Ön koşul: Faz 0 ve Faz 1 tamamlanmış olmalı. **Bu faz yeni bir solver eklemez** —
mevcut iki adaptörü genişletir.

- [ ] CLT (klasik laminasyon teorisi) modülü: katman dizilimi → ABD matrisi (saf Python/numpy)
- [ ] CalculiX için kompozit shell section export (`*SHELL SECTION, COMPOSITE`)
- [ ] OpenRadioss için kompozit özellik kartı export (katman malzemesi/açısı/kalınlığı)
- [ ] Katman bazlı gerilme okuma (solver sonuç dosyasından)
- [ ] Hasar kriterleri: Tsai-Wu, Hashin, Puck — Python'da hesaplanıp `ResultSet.scalars`'a eklenir
- [ ] Frontend: katman dizilimi girişi (açı/kalınlık/malzeme tablosu) + katman bazlı
      güvenlik faktörü görselleştirmesi
- [ ] Hem durability (statik/yorulma) hem crash senaryosunda kompozit parça testi

## Faz 3 — CFD (OpenFOAM)

Ön koşul: Faz 0 tamamlanmış olmalı (Faz 1/2'den bağımsız paralel geliştirilebilir çünkü
farklı solver ailesi). Kullanıcı onayı ile başlanır.

- [ ] `OpenFoamAdapter` implementasyonu — `InputArtifact` olarak case klasörü üretimi
- [ ] Mesh: Gmsh ile STL yüzey mesh'i → OpenFOAM `snappyHexMesh` ile sınır tabakalı hacim
      mesh'i (basit geometrilerde `blockMesh` alternatifi)
- [ ] Dictionary parametrizasyonu: giriş hızı, basınç, türbülans modeli, sınır koşulları
- [ ] Solver çalıştırma (subprocess, uzun sürebilir — websocket ile residual/iterasyon takibi)
- [ ] Post-process: PyVista ile VTK/alan verisi okuma → kuvvet katsayıları (Cd/Cl), basınç
      dağılımı, akış görselleştirmesi → `ResultSet` şemasına dönüştürme
- [ ] Frontend: akış alanı görselleştirmesi (kontur/streamline — statik görsel ya da
      three.js ile renklendirilmiş yüzey mesh'i olarak)

## Faz 4 — Surrogate modelin diğer analiz tiplerine yayılması

Ön koşul: Faz 0.5 tamamlanmış (durability için alan surrogate'i çalışıyor) ve
yayılacak analiz tipinin fazı (1/2/3) bitmiş olmalı.

**Faz 0.5 ile ilişkisi:** Veri üretim altyapısı (DOE, depolama, dışa/içe aktarma),
model mimarisi (mesh-graf / GNN) ve ekstrapolasyon koruması Faz 0.5'te kurulur ve
DURABILITY üzerinde doğrulanır. Bu faz aynı altyapıyı crash/kompozit/CFD'ye taşır —
sıfırdan kurmaz. Her analiz tipinin girdi/çıktı uzayı farklı olduğu için ayrı model
eğitilir, ama boru hattı ortaktır.

Aşağıdaki maddelerden DOE, özellik çıkarımı ve değerlendirme Faz 0.5'te zaten
yapılmış olacak; burada analiz tipine özgü uyarlamaları kapsar.

- [ ] DOE parametre uzayının analiz tipine uyarlanması (crash: hız/açı/bariyer;
      CFD: giriş hızı/türbülans; kompozit: katman dizilimi)
- [ ] Analiz tipine özgü düğüm/eleman özellikleri (Faz 0.5'teki graf şemasına eklenir)
- [ ] Zamana bağlı çıktılar (crash/CFD): Faz 0.5'teki statik alan modeli zaman
      boyutunu kapsamaz — ayrı bir mimari kararı gerektirir
- [ ] Değerlendirme: k-fold cross-validation, hata metrikleri (MAE/RMSE), güven aralığı
- [ ] Model versiyonlama (MLflow ya da basit dosya tabanlı versiyonlama)
- [ ] Backend'e "hızlı tahmin" endpoint'i eklenmesi
- [ ] Frontend'de "hızlı tahmin (saniyeler)" vs "tam çözüm (saatler)" seçeneği
- [ ] Periyodik yeniden eğitim pipeline'ı (yeni veri geldikçe)

## Faz sırasını değiştirme

Kullanıcı isterse fazlar atlanabilir ya da paralel ilerletilebilir, ama agent bunu kendi
başına yapmaz — her faz geçişinde veya sırası değiştiğinde bu dosyayı güncelleyip
kullanıcıya bildirir.
