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

**Eleman tipi SABİT, eleman boyutu PARAMETRE.** 3D'de tet10, 2D'de quad — yapısal
analizde yaygın varsayılan. Eleman boyutu bilinçli olarak taranır, çünkü
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
KE_max 59.3 J = ½·1.187 kg·(10 m/s)²; IE_son 55.4 J; duvar impulsu
14.5 N·s, tepe kuvvet 125.6 kN (ilk TH aralığı, kutu duvara değerek
başlıyor; 2026-10-02 düzeltmesi — önce impuls "14.5 kN" diye raporlanmıştı,
bkz. 1.12 fix). İş: `uploads/crash/d4980c0e…`. İlk starter listing'i 10 hata
veriyordu — deck 2022 kart düzenine çekildi (birimler /BEGIN'de, LAW2 beş
satır, TYPE14 üç satır, INIVEL tek satır, RWALL M/M1, TH alanları 10 kar.);
birim sistemi kg–mm–ms (GPa, kN, J, mm/ms). `th_to_csv` engine sonrası
çağrılıyor; TH/RWALL sütunları adsız ("var 25…") geldiği için grup
başlığından sırayla eşleniyor.
- [ ] Crash sekmesinden aynı koşu (UI doğrulaması), çıktı dosyası temizliği
      (A001…A021 + .rst ≈ 95 MB/iş; anim sayısı/rst saklama ayarı)
- [x] Zaman adımı / kütle ölçekleme kartı (`/DT/NODA/CST`) — 80k düğüm
      tet'te 5e-5 ms adım, 4 ms için 5.5 dk; kabukla (1.13) düşer → 1.15a

**1.11a — Crash box + çarpma plakası şablonu** — ✅ 2026-10-02
`crash_box_plate`: iki ayrı katı (part 0 kutu, part 1 plaka), dört isimli
bölge (`plaka_arka`, `plaka_on`, `kutu_on`, `kutu_arka`), aralık g > 0.
Analitik yok. 4 test + yeniden-okuma regresyonu.

**1.11b — Çok parçalı deck** — ✅ 2026-10-02
Export eleman → parça (hacim sırası); deck parça başına `/TETRA4`, `/MAT`,
`/PROP/TYPE14`, `/PART`; `/GRNOD/PART/1` hareketli (ilk hız, duvar),
`/GRNOD/PART/2` + `/BCS` sabit; `/TH/PART` tüm parçalar. API `parts`
[{part_id, role}], Crash sekmesinde Parçalar tablosu (malzeme + rol).
Gerçek koşu: kutu (hareketli, S235 LAW2) + plaka (sabit), duvar x = −1,
10 m/s, 3 ms, 4 mm tet: starter 0 hata / 0 uyarı, 28 226 çevrim, 71 s;
KE_max 27.0 J (= ½·0.54 kg·10²), IE_son 24.8 J, denge %0.9, duvar tepe
kuvvet 82.9 kN @ 0.135 ms, impuls 6.70 N·s (düzeltilmiş; önce "6.7 kN"). İş `uploads/crash/81921bfe…`. Temas henüz yok: kutu plakayı değil
duvarı görüyor; plaka /BCS ile duruyor (1.12'de duvar yerine temas).

**1.12a — Temas: deck + API + post-process** — ✅ 2026-10-02
API `contacts` [{type 7|24, master_part, slave_part, fric, stfac, gapmin,
istf, inacti, iedge}] + `use_rigid_wall` (varsayılan true). Yüzey
`/SURF/PART/EXT` (solid dış deri; düz `/SURF/PART` yalnız kabuk alır), set
kimliği 1000 + part_ID. TYPE7: slave `/GRNOD/PART` → master yüzey (hm_cfg
radioss2020 düzeni); TYPE24: iki yüzey, self-contact'ta surf_ID2 = 0
(radioss2021 düzeni). İzinli Istf/Inacti/Iedge değerleri hm_cfg'den.
`/TH/INTER` FNX…FTZ → `contact_k_force` + `_max` skaleri; duvar
FN okuyucusu `contact_th` sütunlarını dışlar. 9 deck/post-process + 2 API
testi. Gerçek koşu (1.11b geometrisi, duvar kapalı, TYPE7 kutu düğümleri →
plaka derisi, bayraklar varsayılan): starter 0 hata / 0 uyarı, 28 225
çevrim, 100 s; KE_max 27.0 J, IE_son 25.0 J, denge %0.13, temas tepe kuvvet
86.4 kN @ 0.090 ms, impuls 6.74 N·s (1.11b duvar 82.9 kN / 6.70 N·s;
düzeltilmiş — önce impuls "6.74 kN" diye raporlanmıştı). Radioss GAPmin 0.263 mm → ilk temas 0.075 ms
(= (1 − 0.263) mm / 10 mm/ms), temas enerjisi tepe 0.235 J. İş
`uploads/crash/a7bbb6c3…`.
- [x] Çok arayüzde th_to_csv sütun sırası (arayüz-majör varsayıldı) gerçek
      koşuyla doğrulanacak — tek arayüzde 6 sütun beklenen sırada → 1.17g-6

**1.12b — Crash sekmesi: temas kartları + kuvvet grafiği** — ✅ 2026-10-02
"Temas — /INTER" bölümü: "+ Temas ekle" ile temas başına kart (TYPE7 |
TYPE24, slave → / ↔ master parça seçimi, Fric, Stfac, GAPmin yalnız TYPE7,
Iedge yalnız TYPE24, Istf, Inacti, sil). Varsayılan temas yok; master =
slave → "self" etiketi. "Rijit duvar (/RWALL)" kutusu; kapalıyken nokta/normal
"yalnız ilk hız yönü" başlığıyla görünür kalır. Job sonucunda
`CrashForceChart` (SVG, yeni bağımlılık yok): contact_k_force + rwall_force,
kN–ms, seri başına tepe ve zamanı; skaler listesinde "Temas k Fmax". İlk
tablo denemesi 340 px panelde 712 px'e taşıyordu → kart düzeni (taşma yok,
kart 208 px). 6 yeni vitest (panel 3, grafik 3); frontend 130/130, tsc temiz.
- [x] UI'dan uçtan uca koşu ve ekran görüntüsü (headless Chrome, geçici
      sayfada gerçek CrashPanel + backend, 340 px): form düzgün; grafik
      aşağıdaki impuls hatasını ortaya çıkardı

**1.12 fix — TH kuvvetleri impulstu** — ✅ 2026-10-02
Radioss `/TH/RWALL` ve `/TH/INTER` FN* sütunları birikimli impuls
(kN·ms = N·s); post-process 1.10'dan beri bunları kuvvet diye raporluyordu
(UI grafiğinde temas bitince düz plato). Kanıt: son impuls = m·(v₀+v_son)
(%1.6–2.2 içinde), düz değeri kuvvet saymak toplam momentumdan büyük impuls
gerektirir. Düzeltme: kuvvet = bileşen bileşen dI/dt, sonra bileşke
(`impulse_components_to_force`); `rwall_impulse` / `contact_k_impulse`
eğrileri + `_impulse_final` skalerleri eklendi. Düzeltilmiş tepe kuvvetler:
1.10 125.6 kN, 1.11b 82.9 kN, 1.12a 86.4 kN. Filtre yok (ham türev; CFC
mühendis kararı).
- [x] Tepe kuvvet TH örnekleme aralığına duyarlı: `/TFILE` = t_end/200
      (3 ms → 0.015 ms) ~0.1 ms'lik darbeyi kaba çözüyor — 1.15a'da
      `engine.th_dt_ms` parametresi

**1.13a — Kabuk: export + /SHELL·/SH3N + /PROP/TYPE1** — ✅ 2026-10-02
Hacimsiz (2D) mesh kabuk okunur: tri3/tri6 → `/SH3N`, quad4/8/9 → `/SHELL`
(köşe düğümleri); parça = kenar paylaşan kabuk bileşeni (CalculiX 2D ile
aynı). Kabuk parçaya `/PROP/TYPE1` (hm_cfg radioss2020: Ishell Ismstr Ish3n
Idrill Ipinch · Hm…Dn · N Istrain Thick Ashear Ithick Iplas); izinli
değerler kart tanımından (N ∈ {0,1,3…10}). `model.shell` bayrakları (0 =
/DEF_SHELL); kalınlık `parts[].thickness_mm` > `model.shell.thickness_mm`,
yoksa açık hata. Aynı parçada solid + kabuk hata. Temas yüzeyi kabukta
`/SURF/PART`, solidde `/SURF/PART/EXT`. API `dimension` 2 | 3 (`_d2.msh`).
12 deck/export + 2 API testi; crash testleri 95/95. Gerçek koşu (1.10'un
kabuk eşleniği): orta yüzey tüp 300 × (47×37), t = 3, ~5 mm quad (1 996
düğüm, 1 960 /SHELL), S235 LAW2, Ishell 24, N 5 (bu koşu için seçildi,
varsayılan değil), 10 m/s, duvar x = 0, 4 ms. Starter 0 hata / 0 uyarı;
7 577 çevrim, Δt 5.3e-4 ms (solid 5.1e-5), 7.7 s (1.10 solid 333 s). Kütle
1.187 kg (aynı); IE_son 55.9 J (solid 55.4), KE_son 2.93 J, denge %0.93;
duvar impulsu 14.41 N·s (solid 14.50; m·(v₀+v_son) = 14.51), tepe 123.1 kN
(solid 125.6). İş `uploads/crash/20b1e7b5…` (betikle, API dışı).
- [x] Katlanma modu görsel olarak karşılaştırılmadı (animasyon görüntüleyici
      yok); 4 ms / 10 m/s'de ezilme kısa → 1.17d görüntüleyici

**1.13b — Kabuk crash box şablonu + yüzey-only dikiş** — ✅ 2026-10-02
`crash_box_shell` (`surface_only=True`): `crash_box_plate` kutusuyla aynı L,
h, b, t; geometri orta yüzey — kesit (h−t)×(b−t) çevresi x boyunca ekstrüde,
4 yüz, açık uçlar (ilk sürümde OCC sınır kutusu toleransı yüzünden uç
kapakları silinmiyordu → kapalı kutu; test yakaladı). Kütle solid kutuyla
birebir: L·t·2(h+b−2t). Bölgeler kenar halkası `kutu_on` / `kutu_arka`
(4'er kenar). `GeometryTemplate.surface_only` bayrağı (varsayılan False).
**Bulgu:** Gmsh STEP yazıcısı serbest yüzeylerin ortak kenarlarını ikizliyor
(12 → 16); geri okununca kabuk duvarları bağlantısızdı (2D mesh'te köşe
boyunca 124 çakışık ayrı düğüm) ama parça gruplaması (çakışan düğüm) yine
tek parça sayıyordu — solver sessizce serbest levhalar ezerdi. Düzeltme:
`import_geometry` hacimsiz dosyayı `Geometry.OCCSewFaces=1` ile açar
(önizleme/BC/mesh hep oradan → etiketler tutarlı); `build_template` yüzey-only
şablonu aynı şekilde yeniden okur. Hacimli dosyaya dokunulmaz (kayıtlı BC
etiketleri kaymasın): midsurface akışı (solid dosyada kalıyor) değişmedi,
orada birleştirme hâlâ elle. Veri sayacı: export aynı koordinatta ayrı
düğüm sayısını ölçer → deck başlığı `# coincident_nodes: N`, /crash/solve
`cards.n_coincident_nodes`. 8 şablon + 1 sayaç testi; tüm backend 931/931
(1 atlandı). Gerçek koşu tam API yolu (şablon → 2D quad 5 mm → S235 →
/crash/solve dim 2, t 3, Ishell 24, N 5, 10 m/s, 4 ms): 1 961 quad,
çakışık düğüm 0, starter 0 hata / 0 uyarı, 7 397 çevrim, 9.2 s; IE_son
55.8 J, denge %0.96, impuls 14.41 N·s, tepe 123.1 kN — 1.13a betik koşusuyla
aynı. İş `uploads/crash/9f96356c…`, geometri 3931.
- [ ] Midsurface akışındaki (hacimli dosya) kenar ikizlenmesi hâlâ elle
      birleştiriliyor; otomatik dikiş için etiket kayması analizi gerekir

**1.13c — Crash sekmesi: kabuk kartı** — ✅ 2026-10-02
2D mesh'te panel kabuk moduna geçer: "Kabuk — /PROP/TYPE1" (ortak t, Ishell,
Ish3n, Ismstr, N; 0 = /DEF_SHELL) solid TYPE14 kartının yerine; Parçalar
tablosuna parça başına t sütunu (boş → ortak t); `dimension` mesh'ten (2|3).
App 2D mesh'te panele yüzey parça kimliklerini verir (`surfacePartIds`).
3 yeni vitest; frontend 132/132, tsc temiz. Uçtan uca GERÇEK uygulamada
(headless Chrome, CDP): Crash → şablondan kabuk kutu (12 kenar — dikişli
import) → 2D quad 5 mm (1 997 düğüm / 1 961 quad) → S235 → kabuk kartı
(t 3, Ishell 24, N 5, LAW2, duvar x = 0, 4 ms) → çözüm: IE_son 55.81 J,
KE_son 2.97 J, duvar tepe 123.1 kN, impuls 14.409 N·s (API koşusuyla aynı);
kuvvet–zaman grafiği çizildi. Geometri 3932, iş `uploads/crash/c9cfdef3…`.
Gözlemler (mevcut davranış, bu adımda değiştirilmedi):
- [x] Kalınlık iki yerde → aşağıda "1.13 — kabuk kalınlığı tek kaynak"
      (bileşen otomatik t = 3 ve seçili malzemeyle oluşmaya devam ediyor —
      durability davranışı, dokunulmadı)
- [x] Ağaçta kenar bölgeleri (kutu_on/kutu_arka) "yüzey" etiketiyle görünüyor → 1.17g-1
- [x] Crash şeması altyazısı "yüklenen 3D mesh" diyor (2D'de de) → 1.17g-1
- [x] İş bitince ilerleme satırı "cycle 1" gösteriyor (hub değeri) → 1.17g-1
- [x] Hacimli (midsurface) dosyada 2D parça numarası → aşağıda "1.13 düzeltme
      — Crash paneli 2D parça listesi"

**1.13 düzeltme — Crash paneli 2D parça listesi mesh numarasıyla** — ✅ 2026-10-02
Uygulama 2D'de mesh sonrası her şeyi MESH parça numarasıyla (0'dan, kenar
paylaşan kabuk) kaydeder: malzeme "ATA" (mesh seçimi), ürün ağacı bileşeni
(kalınlık + malzeme), CalculiX 2D `PART_n`, crash 2D export. 1.13c'de Crash
paneli 2D parça listesini CAD yüzey numarasıyla (`surfacePartIds`) alıyordu;
solid + orta yüzey dosyasında panel #1 gösterirken malzeme/bileşen #0'daydı.
Düzeltme: 2D'de liste `uniquePartIdsFromPreview(meshPreview)`. Arada denenen
"crash'i CAD numarasına çevir" düzeltmesi (f9321b2) yanlış varsayıma
dayanıyordu (ölçümde malzeme elle CAD numarasıyla atanmıştı) ve revert
edildi (7c7e3ca).
- [ ] Midsurface dosyasında CAD ağacındaki "Parça #0" (solid) ile ürün ağacı
      COMP_PART_0 (orta yüzey) aynı numarayı farklı şey için kullanıyor —
      durability genel parça kimliği konusu

**1.13 — kabuk kalınlığı tek kaynak: ürün ağacı bileşeni** — ✅ 2026-10-02
/crash/solve dim 2 kalınlığı `components` tablosundan okur (aynı mesh parça
numarası); öncelik: istekte açık `parts[].thickness_mm` > bileşen >
`model.shell.thickness_mm`; eksikse hata mesajı Malzeme adımını gösterir.
DB şeması değişmedi. Crash kartındaki t girişleri kaldırıldı; Parçalar
tablosu bileşen kalınlığını salt-okunur gösterir ("yok" ise uyarı rengi).
Testler: deck öncelik + API (bileşen 1.8 mm, S355 → deck Thick 1.8, S355);
frontend 132/132. Gerçek uygulamada uçtan uca (hatanın çıktığı akış):
thin_plate yükle → 3B'de parça seç → MİD (solid + orta yüzey, 7 yüz) → 2D
quad 5 mm (231 düğüm / 200 quad) → ürün ağacında COMP_PART_0 t 2, S355 →
Crash: #0 S355 t 2 → deck `/SHELL/1`, `/MAT/LAW2/1` S355, `/PROP/TYPE1/1`
Thick 2, Ishell 24, N 5, çakışık düğüm 0 (yalnız deck; çözüm koşulmadı).
İş `uploads/crash/c3f70c6f…`.

**1.14a — LAW2 Johnson-Cook: hız / sıcaklık terimleri ve sınırlar** — ✅ 2026-10-02
`model`: `eps_p_max`, `sig_max0_mpa`, `jc_c`, `jc_eps_dot0_per_s`, `jc_icc`,
`jc_fsmooth`, `jc_fcut_hz`, `jc_chard`, `jc_m`, `jc_t_melt_k`, `jc_rho_cp`
(J/(m³K)), `jc_t_r_k`; 0 = terim kapalı / Radioss varsayılanı. Kart düzeni hm_cfg
radioss140 `matl2_plas_johns` (ρ · E ν Iflag · a b n EPS_p_max SIG_max0 · c ε̇₀
ICC Fsmooth F_cut Chard · m T_melt ρCp T_r); `E ν Iflag` satırındaki fazladan
alan ve son satırın 5. alanı kaldırıldı. Birim: ε̇₀, F_cut ×1e-3 (1/ms),
SIG_max0 MPa→GPa, ρCp ×1e-9. Tutarlılık kontrolü: c > 0 ⇒ ε̇₀ > 0; m > 0 ⇒
T_melt > T_r; ICC ∈ {0,1,2}, Fsmooth ∈ {0,1}. 10 test. DB/UI yok (UI 1.14e).
Gerçek koşu (kabuk crash box 3931, t 3, LAW2 a = 235 MPa, 10 m/s, duvar, 4 ms;
yalnız c farklı): c = 0 → tepe 123.1 kN, IE_son 55.81 J, KE_son 2.97 J, impuls
14.41 N·s; c = 0.014, ε̇₀ = 1/s (test için seçildi) → tepe 131.2 kN (+%6.6),
IE_son 54.01 J, KE_son 4.76 J (daha çok geri sekme), impuls 15.15 N·s
(m·(v₀+v_son) = 15.23); denge %0.96 / %0.97. Starter CC ve ε̇₀'ı doğru yankıladı.
Radioss starter uyarısı 1220: hız etkisi açık ama filtre (Fsmooth) kapalı —
çözücünün kendi notu; seçim mühendisin. İşler `0f78a91d…`, `083db7cd…`.
- [x] Starter uyarı/hata ID'leri iş sonucunda veri olarak gösterilmiyor (1.14f)

**1.14b — Parça başına malzeme kartı** — ✅ 2026-10-02
API `parts[].model` (CrashModelParams: kanun, LAW2/JC, Isolid/NIP, kabuk
bayrakları + kabuk kalınlık yedeği); verilmeyen parça global `model`'e düşer
(eski davranış). Deck `/MAT` + `/PROP` parça parça; geçersiz parça modeli 422.
4 deck + 1 API testi; crash testleri 122/122. Gerçek koşular (crash box +
plaka, TYPE7, duvar kapalı, 10 m/s, 3 ms; taban 1.12a: ikisi de LAW2):
(1) plaka LAW1 elastik → sonuç 1.12a ile basamak basamak aynı (IE_son
25.016 J, temas tepe 86.35 kN, impuls 6.743 N·s) — beklenen: plakanın tüm
düğümleri /BCS'te, deforme olamıyor; E iki kanunda da 210 GPa → temas
rijitliği aynı. (2) yalnız kutuya JC c = 0.014, ε̇₀ = 1/s → temas tepe
92.11 kN (+%6.7, 1.14a kabukta +%6.6), IE_son 24.17 J, KE_son 2.80 J, impuls
7.05 N·s (m·(v₀+v_son) = 7.14); deck'te c yalnız `/MAT/LAW2/1`'de; Radioss
uyarısı 1220 yalnız malzeme 1 için. İşler `43eade78…`, `baa65293…`.

**1.14c — LAW36 tablo plastisite + /FUNCT** — ✅ 2026-10-03
`model.law = "tabulated"`, `tab_curves` [{`eps_dot_per_s`, `points` [(ε_p, σ
MPa)…]}] (hız artan; ε_p kesin artan; σ ≥ 0), `tab_eps_t` / `tab_eps_m` /
`tab_eps_f`, `tab_vp` (0/1); `eps_p_max`, `jc_fsmooth`, `jc_fcut_hz`,
`jc_chard` LAW36'da aynı anlamla. Eğriler istekte gelir, job.json'da kalır —
DB şeması değişmedi. Kart düzeni hm_cfg radioss2017 `matl36_plas_tab` (ρ · E ν
Eps_p_max Eps_t Eps_m · N_funct F_smooth C_hard F_cut Eps_f · VP · fct_IDp
Fscale Fct_IDE EInf CE · eğri id / ölçek / hız beşer); `/FUNCT` radioss90 (X Y).
Eğri kimliği = card_id·100 + k (parça başına ayrık). σ MPa → GPa, ε̇ 1/s → 1/ms.
Parça başına LAW36 / LAW2 karışık çalışır (1.14b). 9 test; crash 131/131.
Gerçek koşu — eşdeğerlik: kabuk crash box, LAW36 tek düz eğri σ = 235 MPa ≡
1.14a LAW2 (a = 235, b = 0, c = 0): IE_son 55.818 / 55.806 J (%0.02), tepe
123.05 / 123.14 kN (%0.07), impuls 14.409 / 14.409 N·s; starter 0 hata / 0
uyarı, "TABULATED ELASTIC PLASTIC LAW 36", fonksiyon 101. İş `d21ab83f…`.

**1.14d — `/FAIL/JOHNSON` + `/FAIL/TENSSTRAIN`, eleman silme** — ✅ 2026-10-03
`model.fail` = {`johnson`?, `tensstrain`?}; ikisi aynı malzemede birlikte
olabilir, boş = kopma yok (eski davranış). Parça başına (`parts[].model.fail`,
1.14b). Kartlar `/MAT` hemen ardından, başlıkta malzeme kimliği, title satırı
yok. JOHNSON hm_cfg radioss2017: D1…D5 · ε̇₀ (1/s → 1/ms) Ifail_sh Ifail_so ·
Dadv · Ixfem = 0. TENSSTRAIN radioss2021: ε_t1 ε_t2 fct_ID = 0 ε_f1 ε_f2 S_Flag
(yalnız ek kart istemeyen 0/1/11/21; ölçek fonksiyonu yok). Tutarlılık:
Ifail ∈ {0,1,2}; d4 ≠ 0 ⇒ ε̇₀ > 0; ε_t2 > ε_t1; TENSSTRAIN'de en az bir sınır.
API `cards.n_fail`. 9 test; tüm backend 968/968 (+1 skip).
Gerçek koşular (kabuk crash box 3931, t 3, LAW2 σ_y 235 MPa, 10 m/s, duvar,
4 ms): starter iki kriteri de yankıladı ("FAILURE MODEL TYPE = TENSSTRAIN /
JOHNSON", D1…D5, ε_t1/ε_t2), 0 hata, tek uyarı 1912 (kabuk ek kütle; FAIL'den
bağımsız). (1) TENSSTRAIN 0.05/0.10 ve JOHNSON D1-D3 = 0.05/3.44/−2.12 →
hiç eleman silinmedi, iki koşu birebir aynı (IE_son 55.41 J, tepe 122.3 kN,
impuls 14.39 N·s) — bu darbede gerinim eşiklere ulaşmıyor. (2) Silme kanıtı
(eşikler bilerek düşük): TENSSTRAIN 0.002/0.004 → 133 kabuk "RUPTURE
(TENS_STRAIN)", IE_son 50.31 J, impuls 9.05 N·s, denge %6.5; JOHNSON D1 =
0.003 (D2…D5 = 0), Ifail_sh 1 → 259 kabuk "RUPTURE (JOHNSON-COOK)", IE_son
15.19 J, KE_son 34.94 J, tepe 27.0 kN, denge %15.5. Denge sapması silmeyle
birlikte artıyor (silmesiz %1.1); bileşenlerine ayrıştırılmadı. İşler `7fd1cb11…`, `4b64725c…`, `21f7c6a2…`, `c3d79087…`.
- [x] Silinen eleman sayısı / zamanı iş sonucunda veri olarak (1.14f)

**1.14f — Kopma listesi + starter mesaj ID'leri iş sonucunda** — ✅ 2026-10-03
`ResultSet.diagnostics` (yeni alan, varsayılan boş; diğer adaptörler etkilenmez)
→ job.json / `/crash/jobs/{id}` `diagnostics`: `starter_errors`,
`starter_warnings` ({ID: adet}; özet tablo satırları sayılmaz),
`deleted_elements` [{criterion, kind, element, time}]. Skalerler:
`starter_error_count`, `starter_warning_count`, `elements_deleted` (tekil
eleman), `deletion_time_first` / `_last`. Listing kopma anını yazmaz; `time` =
kopmadan sonra basılan ilk cycle satırı (üst sınır, çözünürlük = basma aralığı,
bu kutuda ~0.054 ms). 4 test; backend 972/972. Gerçek işlerde: `21f7c6a2…` 133
silme, ilk 0.054 / son 3.78 ms; `c3d79087…` 259, 0.054 / 3.996 ms; `7fd1cb11…`
0 silme, uyarı {1912: 1}; eski hatalı iş `f3d5116a…` 10 hata (573, 574, 668,
53, 260, 1109) / 5 uyarı.

**1.14e — Crash sekmesinde malzeme kartı editörü (parça başına)** — ✅ 2026-10-03
`CrashMaterialCard` (frontend): LAW1 / LAW2 / LAW36 seçimi; LAW2'de σy, b, n,
EPS_p_max, SIG_max0 + açılır "Johnson-Cook hız / sıcaklık" (c, ε̇₀, ICC,
Fsmooth, F_cut, Chard, m, T_melt, ρCp, T_r); LAW36'da eğri kartları (ε̇ +
"ε_p σ" satırları — Excel'den iki sütun yapıştırılır; sekmeyle gelen ondalık
virgül nokta olur), Eps_t/m/f, VP, EPS_p_max, Fsmooth, F_cut, Chard; açılır
"Kopma — /FAIL" (JOHNSON ve/veya TENSSTRAIN onay kutusuyla). Parçalar
tablosunda "kart" sütunu: Global | Ayrı — Ayrı, global kartın o anki
kopyasıyla parçaya kendi kartını açar (`parts[].model`); eleman bayrakları
(TYPE14 / kabuk TYPE1) globalden gelir. Geçersiz sayı / eğri satırı gönderimi
durdurur, hata alan adıyla gösterilir ("Parça #1 c: …"). Öneri yok, 0 =
Radioss varsayılanı. 1.14f sonuçları panelde: "Silinen eleman N · ilk ≤ … ms
· son ≤ … ms" ve "Starter · hata ID … · uyarı ID …". Testler: kart 5, panel
+3; frontend 140/140, tsc temiz. 340 px panelde DOM ölçümü: taşma yok, alanlar
108 px (3 sütun), eğri alanı tam genişlik. Ekran görüntüsünde (geometrisiz)
LAW36 eğri kartı ve /FAIL bölümü kontrol edildi; parça "Ayrı" kartı yalnız
testlerle (geometri yüklü değildi).

**1.14c2 — LAW36 eğrileri malzeme kütüphanesinde** — ✅ 2026-10-03 (şema onayı 2026-10-03)
DB: `materials.crash_curves` JSON nullable; migration `e2f3a4b5c6d7` yalnız
kolon ekler (downgrade siler; dev DB'de yukarı/aşağı/yukarı denendi). İçerik
tab_curves formatı, doğrulama crash ile ortak (`parse_tab_curves`: ε_p kesin
artan, σ ≥ 0, ε̇ kesin artan). API: `POST /materials` `crash_curves` alır,
`PUT /materials/{id}/crash-curves` {curves | null} — kütüphane malzemesi
(is_editable = false) 403, geçersiz eğri 422; listeleme alanı döndürür.
Crash: law = tabulated ve istekte eğri varsa istek; yoksa parçaya atanan
malzemenin eğrileri; ikisi de yoksa 422 ("akma eğrisi yok"). Boş `tab_curves`
artık parametre hatası değil, kontrol deck kurulurken. job.json + yanıt
`law36_curve_source` {part_id: {source: "istek" | "malzeme #id", curves}} —
malzeme sonradan değişse de işin kopyası kalır. Dataset arşivi kolonu taşır
(eski arşivde None). 4 adaptör + 1 malzeme API + 1 crash API testi; backend
977/977 (+1 skip). Çözücü koşusu yok: deck aynı /MAT/LAW36 + /FUNCT kartları
(LAW36 ≡ LAW2 eşdeğerliği 1.14c'de koşuldu).

**1.15a — Engine çıktı aralıkları + zaman adımı kontrolü** — ✅ 2026-10-03
API `engine`: `th_dt_ms` (/TFILE; boş = t_end/200), `anim_dt_ms` (/ANIM/DT;
boş = max(t_end/20, 0.1)), `dt_kind` ∈ {"" (kart yok), DT, NODA/0, NODA/STOP,
NODA/CST/0} + `dt_scale` (Δt_sca, 0 = Radioss 0.9) + `dt_min_ms`. Kart
düzenleri hm_cfg eng_tfile / eng_anim_dt r51, eng_dt r110, eng_dt_noda r2017.
Grup gerektiren /DT/NODA/…/1 ve CST1/CST2 yok. Tutarlılık: STOP ve CST/0
Δt_min > 0 ister; tür seçilmeden Δt_sca/Δt_min verilemez. Boş `engine` = eski
deck (birebir). Listing'den (basılan cycle'lar): `timestep_min`,
`timestep_final`, `mass_model` (TOTAL MASS − ilk MASS ADDED),
`mass_added_final`, `mass_added_rel`. 14 test; backend 991/991 (+1 skip).
Gerçek koşular (kabuk crash box 3931, t 3, LAW2 σ_y 235 MPa, 10 m/s, duvar,
4 ms): (1) TH 0.002 ms (2000 örnek; eski 0.02 ms, 200 örnek): duvar tepe
kuvveti 130.9 kN (eski örneklemede 122.3, +%7), impuls 14.387 N·s aynı —
tepe değer örneklemeye duyarlı, impuls değil. (2) /DT/NODA/CST/0 Δt_sca 0.9,
Δt_min 0.001 ms (doğal Δt 0.00054 ms): Δt 0.001'e sabitlendi, eklenen kütle
0.671 kg = modelin %56.5'i; ilk KE 91.9 J (eklenen kütle de ilk hızı alıyor;
kütle eklemesiz 59.3), IE_son 90.2 J, impuls 20.78 N·s. Starter "NODAL MINIMUM TIME
STEP 0.1E-02" yankıladı. (3) /DT 0 0 → starter "TIME STEP SCALE FACTOR 0.9",
/ANIM/DT 1 ms → 5 animasyon dosyası. İşler `3565bff7…`, `35ad798a…`,
`06c5e223…`.

**1.15b — `/TH` seçimi (gruplar, değişkenler, düğümler)** — ✅ 2026-10-03
API `th`: `rwall` / `inter` / `part` {enabled, vars}, `node_ids` + `node_vars`.
Değişkenler hm_cfg OUTPUTBLOCK listelerinden (th_node r110, th_part r2025,
th_rwall / th_inter r110), yalnız tekil olanlar (DEF ve D/V/A/XYZ kısa yolları
sütun sayısını belirsiz bırakır). Radioss sütunları kendi (hm_cfg liste)
sırasıyla yazar → istek o sıraya dizilir. Boş `th` = eski grup seti.
Düzeltmeler (gerçek koşu kanıtlı): (1) TH grup kimlikleri tekil olmalı —
/TH/RWALL/1 + /TH/PART/1 + /TH/NODE/1 starter hata 79 "DUPLICATE ID IN TH
GROUP"; yeni kimlikler RWALL 1, INTER 2, PART 3, NODE 4. (2) /TH/NODE hm_cfg'ye
göre satır başına bir düğüm (`node_ID skew_ID ad`) ve ivme AX/AY/AZ — eski
`th_nodes` yolu on düğümü tek satıra ve ACCX yazıyordu (hiç gerçek koşuda
kullanılmamıştı); `th_nodes` artık düğüm grubuna AX AY AZ ile eklenir.
(3) RWALL FN / FT bileşkeleri bu ikilide sütun yazmıyor (FNX FNY FNZ FN → 3
sütun) → RWALL/INTER yalnız FN*/FT* bileşenleri. Post-process: deck yanına
`th_spec.json`; th_to_csv adsız "var N" sütunları spec sırasıyla
`th_rwall_<V>`, `th_inter_<k>_<V>`, `th_node_<id>_<V>`, `th_part_<mesh id>_<V>`
eğrileri olur (PART adlı sütundan). Sütun sayısı tutmazsa grup adlandırılmaz,
`diagnostics.th_unmapped_groups`'a yazılır. Duvar / temas kuvveti ve HIC
ivmesi spec varken adla seçilir. 13 test; backend 1004/1004 (+1 skip).
Gerçek koşular (kabuk crash box 3931, 10 m/s, TH 0.002 ms): varsayılan `th`
→ sonuç 1.15a ile aynı (IE_son 55.614 J, tepe 130.943 kN, impuls 14.387 N·s);
RWALL 6 bileşen + PART IE KE XMOM MASS HE + düğüm 1, 2 (DX, AX AY AZ / DX DY
DZ VX AX) → hepsi adlandı; arka düğüm 2: VX₀ = −10 mm/ms, geri sekme, DX_son
7.70 mm. HIC ilk düğümden (eski davranış): düğüm 1 duvardaki ön kenarda, ham
ivme (filtre yok) → acc_peak 120 464 g — veri; düğüm/filtre seçimi mühendisin.
İşler `ddc643c5…`, `b1b05ef6…`, `819c80a1…`.

**1.15c — `/SECT/PARAL` kesit kuvveti** — ✅ 2026-10-03
API `sections`: [{name, origin M, corner1 M1, corner2 M2 (mm), parts (boş =
tümü), iframe ∈ {10 global C0, 11 kesit geometrik merkezi, 12 kesit ağırlık
merkezi, 13 (0,0,0)}}]. Kart hm_cfg radioss110 sect_paral (N1–N3 = 0, ISAVE 0,
dosya yok); eleman grupları /GRBRIC|GRSHEL|GRSH3N/PART (kimlik 8000 + 10·k +
tür). TH: `th.sect` (FNX…FTZ, MX MY MZ) → /TH/SECTIO/5; varsayılan FN* + FT*.
Bulgu (tek değişkenli koşularla doğrulandı): x = sabit kesitte x yönlü kuvvet
FTX'te, FN* sıfır — Radioss'un FN/FT ayrımındaki normal (M1−M)×(M2−M) değil
(N1–N3 = 0 iken; kural belirlenmedi). Global bileşen ayrımdan bağımsız:
F = FN + FT → `section_<k>_force` (bileşen dI/dt, bileşke) ve
`section_<k>_impulse`; skaler `section_<k>_force_max`, `_impulse_final`.
Kesit TH'si RWALL gibi birikimli impuls. 8 test; backend 1012/1012 (+1 skip).
Gerçek koşular (kabuk crash box 3931, 10 m/s, TH 0.002 ms; kesitler x = 20 ve
x = 150): starter 0 hata, kesit 1'de 38 düğüm / 40 kabuk; impuls x = 20: 13.42
N·s (kesit arkasındaki kütle 280/300 · duvar impulsu 14.39 = 13.43), x = 150:
7.48 N·s (150/300 · 14.39 = 7.19, %4); tepe kesit kuvveti 123.9 / 117.5 kN
(duvar 130.9). Varsayılan TH (FN*+FT*) ile 9 değişkenli koşu aynı sonuç.
İşler `ffeda999…`, `3a08ae25…` (yalnız FTX), `9bae2dbe…` (yalnız FNX),
`905f7376…`.
- [ ] Kesit normali / yerel eksen (N1–N3 düğümleri) — FN/FT ayrımı gerekiyorsa

**1.15d — Crash sekmesinde çıktı ve kontrol UI'ı** — ✅ 2026-10-03
`CrashOutputCard` (frontend), "Çıktı ve kontrol" başlığı altında üç açılır
bölüm: (1) Çıktı ve zaman adımı — TH / animasyon aralığı (boş = varsayılan,
placeholder t_end/200, t_end/20), zaman adımı kartı (Yok | /DT | NODA/0 |
NODA/STOP | NODA/CST/0), Δt_sca / Δt_min (tür seçilmeden kapalı); (2) Zaman
geçmişi — RWALL / INTER / PART / SECTIO aç-kapa + değişken çipleri (backend
TH_VARS ile aynı liste), düğüm kimlikleri + değişken çipleri; (3) Kesitler —
kart başına ad, M / M1 / M2 (x y z), parça çipleri (seçim yok = tümü), Iframe
seçimi. Varsayılan durum backend varsayılanını gönderir (eski deck). Sonuç
panelinde kesit Fmax + impuls, Δt_min + eklenen kütle %; kuvvet grafiğinde
"Kesit k" serileri. Geçersiz sayı / düğüm kimliği gönderimi durdurur, hata alan
adıyla. Testler: kart 4, panel +1; frontend 145/145, tsc temiz. Ekran
görüntüsü geometrisiz (UI'da mevcut geometriyi açma yolu yok): üç bölüm 340 px
panelde.

**1.16a — `crash_runs` tablosu, geçmiş ve karşılaştırma API'si** — ✅ 2026-10-03 (şema + içe aktarma onayı 2026-10-03)
DB: yeni `crash_runs` (job_id tekil, geometry_id FK, name, created_at,
dimension, t_end_ms, status, message, solver_ran, request JSON — bariyer /
model / parçalar / temas / engine / th / kesitler / law36 eğri kaynağı,
materials_snapshot JSON, scalars JSON, diagnostics JSON, excluded +
exclude_reason); migration `f3a4b5c6d7e8` yalnız tablo ekler (dev DB'de
yukarı / aşağı / yukarı denendi); analysis_runs değişmedi. Eğriler DB'de yok,
job.json'da. `/crash/solve` kayıt açar (`run_id` yanıtta), arka plan işi
bitince kendi oturumuyla günceller (başarısız da). API: `GET /crash/runs`
(?geometry_id, include_excluded), `GET /crash/runs/{id}` (girdi + skaler +
eğriler), `PATCH /crash/runs/{id}` (ad, excluded, exclude_reason — girdi /
sonuç değişmez), `GET /crash/runs/compare?ids=…&curves=…` (boş = *_force
eğrileri + time; her koşu kendi zaman ekseniyle). İçe aktarma
`scripts/import_crash_jobs.py` (job_id ile tekrarsız; created_at = job.json
zamanı): dev'de 37 iş aktarıldı (29 solved, 4 rad_only, 4 failed; 23'ü crash
box 3931), 293 iş atlandı — geometrisi dev DB'de yok (test koşularının
uploads'a bıraktığı işler, test geometri kimlikleri); ikinci çalıştırma 37
güncelleme, çoğaltma yok. Eski işlerde materials_snapshot boş. 4 test;
backend 1016/1016 (+1 skip). Gerçek koşu `wait=false`: kayıt pending →
solved, section_1_impulse_final 13.42 N·s; compare 38 ↔ 17 iki koşunun duvar
+ kesit kuvvetlerini döndürdü.

**1.16b — Crash sekmesinde koşu geçmişi + karşılaştırma** — ✅ 2026-10-03
`CrashHistory` (frontend), Crash panelinin altında: koşu listesi (seç | ad +
#id · tarih · durum | duvar Fmax | dışla/geri al), geometri yoksa tüm
geometriler (satırda geo id); dışlananlar varsayılan gizli, "Dışlananları
göster" ile görünür; liste yeni iş / iş bitince yenilenir. En çok 6 koşu
seçilip "Karşılaştır": eğri seçimi (*_force), "t üst (ms)" yalnız görünüm
kırpma (boş = tümü), kuvvet grafiği her koşunun kendi zaman ekseniyle
(`CrashForceChart` seri başına `time`), skaler tablosu (duvar Fmax / impuls,
IE / KE son, enerji dengesi, Δt_min, eklenen kütle oranı, silinen eleman,
kesit / temas Fmax; sütun başlığı #id). Dar panel (340 px): ilk tablo
denemesi yatay taştı → satır listesi (grid) + 300 px dikey kaydırma.
Dışlama gerekçesi UI'dan girilmiyor (API alanı var). Testler: geçmiş 3, panel
mock'u güncellendi; frontend 148/148, tsc temiz. Ekran görüntüleri gerçek
veriyle (38 koşu): #14 TH 0.02, #6 TH 0.002, #7 NODA/CST/0, #4 TENSSTRAIN
silme; t ≤ 0.3 ms. Bulgu: #7'nin eklenen kütle oranı DB'de 0.362 idi —
1.15a'daki oran hatası düzeltilmeden önce job.json'a yazılmış; o iş ham
çıktılardan yeniden işlendi → 0.565. 1.14f / 1.15a öncesi çözülen işlerde
yeni skalerler (silinen eleman, Δt_min) yok, tabloda "—".
- [x] Eski işleri ham çıktılardan yeniden işleme (yeni skalerler için) —
  istenirse ayrı adım → 1.17g-5

**1.17a — Crash senaryo şablonu `POST /crash/scenario`** — ✅ 2026-10-03
Tek çağrıda: geometri şablonu (`crash_box_shell`; liste `CRASH_TEMPLATES`) →
2D mesh (varsayılan quad 5 mm) → malzeme ataması (material_id ya da adı,
varsayılan S235) → /crash/solve (parça 0 hareketli, kabuk kalınlığı = istek ya
da şablonun wall'u; bariyer hız / açı; duvar istek ya da şablondan: ön uç x = 0
kesit merkezi, normal +x; model varsayılan LAW2 σy malzemeden; engine / th /
kesit / temas olduğu gibi). Yeni çözücü mantığı yok — mevcut uç fonksiyonları
sırayla (DOE runner deseni); kayıt crash_runs'a /crash/solve'dan. Yanıtta
çözülmüş senaryo (şablon parametreleri varsayılanlarla birleşik). Hangi
parametrenin değişeceği DOE'de (1.17b) mühendisin. 3 test; backend 1019/1019
(+1 skip). Gerçek koşular: (1) varsayılan senaryo + TH 0.002 + kesit x=20 /
x=150 → yeni geometri 3934, sonuç elle kurulan 3931 koşusuyla (905f7376)
BİREBİR aynı: IE_son 55.61423 J, duvar tepe 130.9434 kN, impuls 14.38706 N·s,
kesit impulsu 13.4208 / 7.4786 N·s. (2) L 250, t 2, 15 m/s, eleman 4 mm →
kütle 0.675 kg (elle: çevre 172 × 250 × 2 mm × 7.85e-6 = 0.675), KE 75.95 J
(½·0.675·15²), deck Thick 2, /INIVEL −15; Δt_min 0.00061 ms (3931'in 5 mm
mesh'i 0.00054 — o mesh'te x = 4.828 / 4.829 gibi kısa kenarlar var).
Bariyer modelleri (Ansys/LSTC IIHS MDB) araştırıldı: ftp.lstc.com 401 (kimlik
ister), lisans belirtilmemiş, proje kuralı (Ansys/LS-DYNA yok) → kullanılmadı.

**1.17b — Ek kütle `/ADMAS` + rijit gövde `/RBODY`** — ✅ 2026-10-03
API (`/crash/solve` ve `/crash/scenario`): `added_masses` [{name, region |
part_id, mass_kg, distribution total (type 1) | per_node (type 0)}],
`rigid_bodies` [{name, region | part_id, mass_kg (ana düğüme), ikrem, icog}].
Bölge = PhysicalGroup (şablon bölgesi, ör. `kutu_arka`, ya da kullanıcı yüzey
grubu) → CAD varlıkları → mesh düğümleri (`region_node_ids`; crash deck düğüm
kimliği = gmsh etiketi, sınır düğümleri dahil). Kartlar hm_cfg: admas r110
(MASS grnd_ID), rbody r2021; düğüm grupları /GRNOD/NODE (8500+k kütle,
8700+k rijit gövde). Rijit gövde ana düğümü seçimin ağırlık merkezinde yeni
düğüm; seçim hareketli parçadaysa ana düğüm `/INIVEL/TRA/2` ile ilk hızı alır
(yoksa ek kütle momentuma girmez). Enerji düzeltmesi: post-process global
enerji sütunlarını (INTERNAL / KINETIC / HOURGLASS / ROTATION ENERGY, EXTERNAL
WORK) tercih eder — parça TH'si rijit gövde ana düğümünü içermiyordu (kızaklı
koşuda KE 71 J okunuyordu, global 2559 J); `energy_balance_rel` artık IE + KE
+ dönme + hourglass − dış iş; yeni `hourglass_energy_final`, `hourglass_ratio`
(HE / IE_son). 12 test; backend 1031/1031 (+1 skip). Gerçek koşular (crash
box senaryosu, 10 m/s; kütleler TEST değeri, mühendis seçimi değil):
(1) `/RBODY` kutu_arka + 50 kg, 20 ms: starter 36 bağımlı düğüm, ana düğüm
(300, 25, 20), kütle 50.0097 (bağımlılar 0.0097); KE₀ 2558.9 J (½·51.187·10²
= 2559.4), IE_son 2441.3 + KE 4.7 + hourglass 112.8 = 2558.8 J → denge %0.04,
hourglass / IE %4.6; duvar impulsu 533.6 N·s = 51.19 · (10 + 0.42) — küçük
geri sekme; Δt_min 0.0002 ms (katlanma eleman bozulması). Uyarı 446: rijit
gövde bağımlı 36 düğüm duvardan çıkarıldı (Ikrem 0; arka uç duvara değmez).
48 s. (2) `/ADMAS` kutu_arka toplam 1 kg, 4 ms: starter "TOTAL ADDED MASS =
1.0", KE₀ 108.86 J (beklenen 109.35), denge %0.13. Gözlem: global KE ilk
örnekte ½mv²'den 0.49 J düşük — ön halka (36 düğüm, 0.0097 kg) duvara t = 0'da
değiyor, ½·0.0097·10² = 0.486 J hemen duruyor. Eski işlerin job.json
skalerleri değişmedi (yeniden işlenirse yeni tanım). İşler `eb971f21…`,
`bb3fe909…`.

**1.17c — Bölge / parça sınır koşulu `/BCS` + zorlanmış hız `/IMPVEL`** — ✅ 2026-10-03
API (`/crash/solve`, `/crash/scenario`): `boundary_conditions` [{name, region
| part_id, dofs "Tx Ty Tz Rx Ry Rz" 6 hane}], `imposed_velocities` [{name,
region | part_id | rigid_body, direction X Y Z XX YY ZZ, velocity_m_s,
t_start_ms, t_stop_ms (0 = sonsuz)}]. Kartlar hm_cfg: bcs r51 (`/BCS/10+k`;
/BCS/1 sabit parçalar), impvel r120 + /FUNCT 9900+k; düğüm grupları
8800+k (BC), 8900+k (hız); rijit gövde hedefi = ana düğüm. Hata (gerçek
koşuda bulundu): sıfır hız Scale_y = 0 olarak yazılınca Radioss varsayılan
1'i kullandı — Y, Z ve dönmelere 1 mm/ms · 1 rad/ms uygulandı, model patladı
(IE −18 kJ, 3.68 ms'de durdu). Düzeltme: hız fonksiyon değerinde, Scale_y = 1.
10 test; backend 1041/1041 (+1 skip). Gerçek koşular (crash box senaryosu):
(1) BCS kutu_arka 011000, 4 ms: arka düğüm 2 DY = DZ = 0, DX serbest
(7.68 mm geri sekme) ✓. (2) Rijit gövde kutu_arka + IMPVEL X −10 m/s, yalnız
X: arka köşe VX −10.2 → −12.2 mm/ms — rijit uç katlanma sırasında dönüyor
(kılavuzsuz itici; köşe hızı = V + ω×r). (3) Aynı + Y, Z, XX, YY, ZZ = 0
(kılavuzlu itici), 10 ms: arka düğüm VX −10.000, DX −25.00 / −50.00 /
−99.90 mm (= −10·t), DY = DZ = 0 ✓; enerji dengesi %2.6, hourglass / IE %7.4;
ortalama duvar kuvveti (1–10 ms) 53.7 kN, IE / ezilme 5094 J / 100 mm =
50.9 kN — 1.17f ortalama ezilme kuvveti için ilk veri. İşler `cdc5aa61…`,
`2d5d4ed6…`, `cded46ab…` (patlayan `9169dc48…`).

**1.17d — Deforme şekil görüntüleme (zaman kaydırıcılı 3B)** — ✅ 2026-10-03
Backend: `convert_animation` — imajdaki `anim_to_vtk` ile A001… → ASCII VTK
(Docker'da tek `sh -c` döngüsü, kare başına konteyner yok; ara .vtk silinir);
`openradioss_anim.build_animation` — yüzey (kabuk tri/quad; solid tet/hex dış
yüzleri), kare başına deforme koordinat, düğüm |u|, eleman skalerleri
(plastik şekil değiştirme, özgül enerji), EROSION_STATUS (silinen yüz); hep
sıfır skaler atlanır; >60 kare seyreltilir (son kare korunur). Rijit duvar
(NODE_ID 0 sentetik noktalar) ve rijit gövde ana düğümündeki dejenere dörtgen
atlanır (ilk görüntüde duvar kutuyu örtüyordu). `GET /crash/runs/{id}/animation`
ilk istekte üretir, `anim.json` önbelleği. Engine deck'e `/ANIM/ELEM/EPSP`
eklendi (VTK adı `2DELEM_Plastic_Strain`). Frontend `CrashAnimationViewer`
(three.js, OrbitControls): kare kaydırıcı, oynat, renk skaleri seçimi, jet
renk ölçeği (proje görüntüleyicileriyle aynı formül; çubuk birebir duraklar),
silinen eleman sayısı; geçmiş listesinde çözülmüş koşuya ▶. Testler: backend
4, frontend 3 (WebGL jsdom'da yok — yardımcılar + açılma bağlantısı); backend
1045/1045 (+1 skip), frontend 151/151. Gerçek koşu: kızak 50 kg (test değeri),
20 ms, anim 0.5 ms → 41 kare, 1961 kabuk, 4.7 MB, ilk açılış 20 s; |u|max
41.4 mm, plastik şekil değiştirme max 1.294 ön uçta (katlanma), son karede
silinen yok. İş `b6374029…` (koşu #47).
- [x] Görüntüleyicide hazır görünüm (yan / üst / ön) → 1.17g-2 (impact
  bölgesine otomatik yakınlaştırma yok — fare ile)

**1.17e — SAE J211 CFC kanal filtresi** — ✅ 2026-10-03
`app/postprocess/cfc.py`: 4 kutuplu fazsız Butterworth (2 kutuplu ileri +
geri, J211-1 Ek C), sınıflar 60 / 180 / 600 / 1000; TH tam eşit aralıklı
olmadığından eşit ızgarada süzülür, özgün zamanlara aradeğerle döner;
başlangıç koşulu y₀ = x₀. Frekans yanıtı (test): CFC'de −0.45 dB (geçiş
bandı +0.5 / −1 dB), 1.65·CFC'de −2.9 dB, 10·CFC'de < −50 dB. API `filters`
{force_cfc, acc_cfc} → deck yanına `postprocess.json`; ham eğriler korunur,
süzülmüşler `*_force_cfcN`, `th_node_*_A*_cfcN`, `acc_g_cfcN` eğrileri ve
`*_max_cfcN`, `acc_peak_g_cfcN`, `hic15/36_cfcN`, `sample_ratio_cfcN` (fs/CFC,
veri; eşik mühendisin) skalerleri. İvme bileşen bazında süzülür, bileşke
sonra. Kuvvet: yalnız bileşke kaydedildiği için bileşke süzülüyor (not).
UI: Çıktı kartında "Kuvvet CFC" / "İvme CFC" seçimi, sonuçta süzülmüş tepe
değerler, grafikte "… CFCn" serileri. Hata (gerçek koşuda bulundu): HIC
O(n³) idi (her pencere çiftinde integral yeniden) — 2000 TH örneğinde
dakikalar, sunucu kilitlendi (iş #48 dışlandı); önek toplamı + numpy ile
O(n²), eski tanımla birebir (test), 2000 örnek 0.05 s. Testler: backend 7,
frontend 2; backend 1052/1052 (+1 skip), frontend 153/153. Gerçek koşular:
(1) kızaksız kutu 4 ms, TH 0.002: ön düğüm ivmesi ham 120 464 g → CFC1000
8 037 g, HIC15 1.43e9 → 2.57e6; duvar tepe 130.9 → CFC600 101.2 kN — AMA bu
olay ~0.12 ms (≈ dikdörtgen darbe), CFC600 bunu tümüyle yayıyor; süzülmüş
"tepe" filtre yanıtı, anlamlı değil (sınıf olay süresine uygun seçilmeli;
öneri değil, veri). (2) kızak 50 kg (test) 20 ms, TH 0.01: duvar tepe 126.7
→ 125.5 kN, 1–10 ms ortalama ham 52.0 / CFC 51.9 kN — klasik ezilme eğrisi
(ilk tepe, katlanma salınımları 25–90 kN, ~50 kN plato, kızak ~9.5 ms'de
duruyor). İşler `262d471a…` (#49), `3530b829…` (#50).

**1.17e2 — Koşu detay grafikleri (kuvvet, ivme, enerji; ham + CFC)** — ✅ 2026-10-04
Kullanıcı isteği ("grafikler frontendde mutlaka olmalı"): 1.17e'de ham–CFC
karşılaştırma görüntüleri uygulama dışında çizilmişti. `CrashRunCharts`:
geçmişte çözülmüş koşuya 📈 → o koşunun job.json eğrilerinden kuvvet (duvar,
temas, kesit; ham + CFC), ivme bileşkesi (ham + CFC, g), enerji (IE, KE, J)
grafikleri + IE / enerji dengesi / hourglass / impuls / HIC (ham + CFC);
"t üst (ms)" görünüm kırpma. `CrashForceChart`: birim / aria parametresi;
CFC serisi ham eşiyle aynı renk ve kalın, eşi olan ham ince ve soluk (renk
sırası taban anahtara göre — ilk denemede 4 renk döngüsü eşleri ayırıyordu;
yamada `\d` kaçışı düşmüştü, testle yakalanacak hale getirildi).
Karşılaştırma: varsayılan eğriler kuvvetler + CFC + acc_g (+ CFC); eğri
listesi tüm eğriler, ivmede eksen "İvme · g". Testler: frontend +3, backend
+1; frontend 156/156. Ekran: koşu #50 (kızak 50 kg test, CFC600) kuvvet —
kesit x=150 kuvveti duvar kuvvetini izliyor (kızak yavaşlama kuvveti); #49
ivme ham 120 464 g / CFC1000 1 931 g (ilk 0.3 ms).

**1.17f — Validasyon seti (veri; kabul kriteri yok)** — ✅ 2026-10-04
Rapor `docs/validation/crash_validation.md` (+ `.json`), üretici
`backend/scripts/crash_validation.py` (çalışan backend'e senaryo koşuları),
saf hesaplar `app/postprocess/crash_validation.py` (dalga hızı, ρcvA, 2L/c,
kare tüp Pm formülleri, temas penceresi, plato, kızak ezilmesi δ = ∫(v0 −
I/M) dt — mesh'ten bağımsız). `GET /crash/validation` + Crash panelinde
"Validasyon (1.17f)" kartı (oranlar 3 hane; geçti/kaldı yok). Sonuçlar
(crash_box_shell 300×50×40, t 3, S235, 10 m/s): V1 elastik — plato 204.54
/ ρ·c₀·v·A 204.63 kN (0.9995; levha hızıyla 0.954), temas 0.1182 / 2L/c₀
0.1160 ms (1.019), impuls / 2Mv0 0.966. V2 elasto-plastik — plato 118.89 /
σy·A 118.44 kN (1.004), impuls 0.974. V3 kızak 50 kg (test) — Pm = IE/δ
5 / 4 / 3 / 2.5 mm: 59.53 / 59.01 / 56.36 / 55.97 kN (3→2.5 mm %0.7), W&A
1983 48.73 kN (oran 1.15–1.22), A&J 1984 66.57 kN (0.84–0.89); enerji dengesi
≤ %0.51 (V1), ≤ %0.18 (V3); 2.5 mm koşusu 228 s. Testler: backend +5,
frontend +1. Koşular #51–#56.
- [ ] Kabul kriterleri (oran bantları, enerji / hourglass eşikleri) — mühendis
- [ ] Dikdörtgen kesitte C = (b+d)/2 ve formül geçerliliği — mühendis değerlendirmesi

**1.17g — Temizlik + frontend eksikleri** — ✅ 2026-10-04 (kullanıcı gece
"1.17'yi tamamen bitir, frontend eksiklerini tamamla" — alt adımlar ayrı commit)
- g1 UI küçükleri: ağaçta bölge türü boyuttan (kenar / yüzey / nokta + adet),
  iş bitince hub'ın eski "cycle 1" satırı gösterilmez, şema altyazısı 2D / 3D.
- g2 Deforme şekil görüntüleyicide hazır görünümler +X −X +Y +Z İzo.
- g3 Material adımında crash LAW36 eğri düzenleyici (kullanıcı malzemesi;
  kütüphane salt okunur; PUT /materials/{id}/crash-curves) + Crash kartında
  "eğriler malzemeden" (tab_curves boş → 1.14c2 malzeme eğrisi).
- g4 Çözüm sonrası Radioss restart (*.rst) silinir — crash klasörünün ~%49'u
  (847 MB'ın 414 MB'ı), restart desteği yok; `CRASH_KEEP_RST=1` korur. Eski
  işler için kuru-koşulu `scripts/cleanup_crash_rst.py` (çalıştırılmadı: 97
  dosya / 433 MB — karar kullanıcının).
- g5 `scripts/reprocess_crash_jobs.py`: eski işler ham çıktıdan güncel
  post-process ile; ilk seferde `scalars_prev` saklanır; dev'de 48 kaydın 33'ü
  güncellendi (226 yeni skaler), ikinci koşu 0 değişiklik.
- g6 Çok arayüzde TH sütun sırası doğrulandı (geometri 3928, kutu + plaka,
  solid, 3 ms): A [kutu→plaka TYPE7, kutu self] → contact_1 86.349 kN /
  6.743 N·s (1.12a tek temasla birebir), contact_2 0; B sıra ters → contact_2
  86.349 / 6.743, contact_1 0. Başlıklar arayüz numarası + adıyla
  ("contact_1_p0_on_p1"), arayüz-majör. İşler `7d9bd501…`, `d38d5df6…`.
- g7 Crash panelinde "Hızlı senaryo" kartı: 1.17a `/crash/scenario` arayüzü
  (L h b t, eleman, v0, süre, kızak kg → rijit gövde kutu_arka, CFC, malzeme)
  — geometri yüklemeden koşu, ilerleme, bitince geçmiş yenilenir. Tarayıcıda
  uçtan uca: koşu #60 (kızak 50 kg, 12 ms, CFC600) solved → geçmiş üstte →
  grafikler. Gözlem: bu koşuda CFC600 tepe (122 kN) ham tepeden (120 kN)
  büyük — varsayılan TH aralığı t_end/200 = 0.06 ms ham tepeyi kaba
  örnekliyor (#50'de 0.01 ms ile 126.7) + Butterworth basamak aşımı; veri.
Testler: backend 1059/1059 (+1 skip), frontend 164/164.

**1.17h — Hourglass kontrolü** — ✅ 2026-10-04 (kullanıcı: "hourglass kart
kontrolü olsun, grafikte de görelim")
- Kabuk /PROP/TYPE1 Hm Hf Hr, solid /PROP/TYPE14 h; 0 = Radioss varsayılanı.
  Aralıklar hm_cfg'den (prop_p1_shell 0…0.05, varsayılan 0.01;
  prop_p14_solid h 0…0.15, varsayılan 0.10) — dışı 422. Dm Dn qa qb sıfır.
- Global HOURGLASS ENERGY eğri olarak (`hourglass_energy`) saklanır; Enerji
  grafiğinde İç / Kinetik yanında; panelde HG_final · HG/IE.
- Gerçek koşu (kutu kabuk, Ishell 1, kızak 50 kg, 8 ms): Hm=Hf=Hr 0.001 →
  HG 41 J, HG/IE 0.017 (#61); 0.05 → 191 J, 0.081 (#62). Duvar tepe 120.7 /
  120.8 kN. Veri; seçim mühendisin.

**Sonraki mikro-adımlar (her biri ayrı onay)** — sıralama 2026-10-03, kullanıcı
kararı: **önce standart explicit ortam tamamlanır ve valide edilir, ML (DOE +
öğrenme + tahmin) en sonda ve ML tezgahında** (durability'deki gibi; değişken
parametreler ve aralıklar tezgahta mühendisin seçimi). 1.17 bitmeden ML'ye
geçilmez.

*1.17 — Standart explicit ortam* — ✅ tamam 2026-10-04 (b–g)
*1.18 — Plaka–küre delinme örneği* (kullanıcı isteği 2026-10-03; 1.17b/c
üzerine): iki parçalı plaka + küre şablonu, rijit küre, plaka köşe / kenar
sabit, küreye sabit hız; cam ≈ LAW1 + /FAIL. Hız ve boşluk mühendisin
(explicit süre maliyeti).
- 1.18a ✅ 2026-10-04 `plate_ball_shell` şablonu: kare plaka orta yüzeyi
  (z = 0, a × a) + üstünde g boşlukla küre yüzeyi; iki parça (0 plaka, 1
  küre); bölgeler plaka_kenar (4 kenar), plaka, kure (6 yüz). Tek parça OCC
  küresi mesh katmanının dikişli açılışında meshlenmiyor ("Impossible to mesh
  periodic surface"; dilimli küre kutup kenarı yüzünden kapalı döngü
  kuramıyor) → küre 6 yamalı küp-küre: kenarlar büyük çember yayı, yama iç
  yüzeyi küre üstündeki 7×7 eş-açılı noktaya oturtulmuş dolgu. Ölçülen:
  düğüm yarıçap sapması < %0.2, alan %99.9. Tarayıcıda: 2 parça, 7 yüzey,
  4263 düğüm / 4140 quad (5 mm). Ek: seçili bölge çipinde hover yazıyı
  görünmez yapıyordu (CSS).
- 1.18b ✅ 2026-10-04 `/crash/scenario` plate_ball_shell: yeni parça rolü
  `free` (ilk hız yok, /BCS yok; grup 1 dışında → rijit duvar ikincili
  değil); plaka free + kalınlık t, küre moving + `ball_thickness_mm`;
  `template_defaults` açıkken boş listeler: /RBODY kure (`ball_mass_kg` ana
  düğüme), /BCS plaka_kenar 111111, TYPE7 master küre / slave plaka; duvar
  yok, ilk hız −z. Küre malzemesi `ball_material_id` (boş = plaka). Gerçek
  koşu #63 (S235 300×300×5, D50 + 1 kg, 10 m/s, 4 ms, 5 mm): KE₀ 53.06 J =
  ½·1.062·10²; temas Fmax 12.9 kN (t 1.66 ms); impuls 15.01 N·s ≈ küre Δp
  1.062·(10 + 4.16) = 15.03 (geri sekme); plaka IE 42.1 J; denge %0.91;
  HG/IE 0.006. Düzeltmeler: rijit gövde elemanları anim'de ilk karede
  EROSION_STATUS 0 → "silinmiş" sayılıp küre çizilmiyordu (t = 0'da kapalı =
  silinme değil); görüntüleyici +Y görünümünde yukarı −Z idi → +Z.
- 1.18c ✅ 2026-10-04 Hızlı senaryo kartında şablon seçimi: crash box (rijit
  duvar) | plaka–küre (a, t, D, g, küre kabuk t, küre ek kütle; kızak alanı
  yok; kurulum backend `template_defaults`). Malzeme plaka ve küreye aynı.
  API tipi: rol `free`, `ball_*` alanları.
- 1.18d ✅ 2026-10-04 Hız taraması `scripts/plate_ball_sweep.py` →
  `docs/validation/plate_ball_sweep.{json,md}`; küre kütlesi 2·KE₀/v0², son hız
  impulstan (işaretli) ve enerjiden (kontrol) — `app/postprocess/plate_ball.py`.
  TEST değerleri (mühendis değer vermeden "devam"): S235 LAW2, plaka 300×300×2,
  TENSSTRAIN ε_t1 0.15 ε_t2 0.25, küre D50 + 1 kg, 5 mm, 2 ms. Sonuç (veri):
  25 m/s geri sekme +2.26 m/s, silinen 0 (#66); 50 → −37.5 m/s, 25 silinen
  (#67); 100 → −95.3, 28 (#68); 150 → −146.4, 56 (#69); 200 → −195.1, 82
  (#70). İki yöntem ≤ 0.03 m/s örtüşüyor. HG/IE 150–200 m/s'de 0.13–0.17
  (5 mm eleman, kaba). Delinme eşiği hükmü yok; deneme koşusu #65 (100 m/s).
- 1.18e ✅ 2026-10-04 Doğrulama (kullanıcı: "doğruluğu nasıl ispatlayacağım"):
  validasyon setine V4 elastik yarı-statik plaka–küre (ankastre kare plaka
  k = D/(0.0056·a²), kütle–yay) ve V5 Recht–Ipson uydurması; `--only` ile
  tek vaka; arayüzde formül + uydurma satırı. V4 #72: CFC60 tepe 0.977,
  ilerleme 1.006, süre 1.009, impuls 0.989 (ham tepe 1.346 — plaka modları);
  HG/IE 0.222 (Ishell 0; #73 Ishell 24 → 0). V5: v_bl 28.75 m/s (25–50
  aralığında), a 0.988, R² 0.9998. Ayrıntı `docs/validation/crash_validation.md`.
- Açık (mühendis): gerçek malzeme / FAIL değerleri, eleman boyu, kabul

*Explicit şablon kataloğu — 1.18 sonrası, 1.19'dan (ML) ÖNCE* (kullanıcı
kararı 2026-10-03: "durability ile aynı mantık"). Her örnek durability
şablonları gibi: parametrik `GeometryTemplate` (parametreler, bölgeler,
karakteristik uzunluk) + crash senaryo varsayılanları (duvar / impaktör,
kütle, bölge BC, hız, çıktılar — 1.17a deseni) + kendi doğrulama referansı
(analitik ya da literatür; durability'deki `analytic` karşılığı) + daha sonra
ML tezgahında şablon başına DOE / model. Problem tanımları açık literatür ve
Altair Radioss Example Guide'dan (RD-E; Radioss ailesi) referans alınır, dosya
kopyalanmaz. Durum: ✓ hazır · ◐ küçük ek altyapı · ✗ büyük yeni kabiliyet.
- Otomotiv: (1) crash box eksenel ezilme ✓ [RD-E 1700]; (2) S-kiriş / ön kiriş
  eğilmeli çarpma ◐ [RD-E 0300]; (3) direk (pole) yan çarpması ◐
  (`/RWALL/CYL`); (4) tampon / kaput impaktörü (HIC) ◐ (rijit küre + CFC);
  (5) düşme testi ◐ (`/GRAV` + zemin) [RD-E 0600]; (6) kapı intrüzyonu ◐
  (zorlanmış hız, 1.17c)
- Savunma: (7) plaka delinme ◐ (= 1.18) [RD-E 2600]; (8) Taylor çubuğu ◐;
  (9) Hopkinson çubuğu ◐ [RD-E 0800]; (10) patlama yüklü plaka ◐ (zamana bağlı
  basınç yükü); (11) kuş / yumuşak cisim ✗ (SPH) [RD-E 4900]; (12) mayın /
  araç altı patlama ✗ (ALE, Faz 1 dışı)
- İş makineleri: (13) ROPS (ISO 3471) ◐ kabin çerçevesi + yavaş itme + enerji;
  (14) FOPS (ISO 3449) ◐ rijit cisim düşürme; (15) kepçe / bıçak taş darbesi ◐
- Verifikasyon tabanı (1.17f ile ortak): dalga yayılımı [RD-E 1900], çekme
  testi [RD-E 1100], kare plaka [RD-E 1800]
- Ortak altyapı (katalogdan önce): silindirik / küresel rijit duvar, yerçekimi,
  zamana bağlı basınç yükü, zorlanmış hız (1.17c), CFC (1.17e). Önerilen ilk
  set (en az yeni altyapı): crash box, direk, düşme testi, plaka delinme,
  Taylor çubuğu, ROPS. Öncelik ve sıra kullanıcının; ✗ olanlar ayrı faz.

**Katalog adımları (kullanıcı 2026-10-04: "senaryolar hazır olsun, DOE'ler
sonra")**
- K0 ✅ 2026-10-04 Katalog altyapısı: `app/api/crash_catalog.py` 15 madde
  (sektör, durum ready / planned / major, şablon, referans, doğrulama, eksik
  altyapı, adım); GET /crash/catalog; `/crash/scenario` şablon listesi
  katalogdan (ready). Arayüz: Crash panelinde katalog listesi (2/15 hazır),
  Hızlı senaryo kartı genel — örnek listesi katalogdan, geometri alanları
  şablon şemasından (sembol, birim, varsayılan), şablona özgü ek alanlar tek
  kayıt (EXTRAS).
- K0 ek: ana sayfa "Şablondan üret" listesi sekmeye göre (crash → `crash`
  etiketli, durability / modal → diğerleri) + crash şablon şemaları; eski
  "Senaryo: Rigid wall / Plaka–küre" ön ayarı kaldırıldı (yalnız duvar yönünü
  z'ye çeviriyordu, 1.18 şablonuyla karışıyordu).
- K1 ✅ 2026-10-04 Taylor çubuğu: `taylor_bar` (dolu silindir, solid), katalog
  ready, `/crash/scenario` 3D yolu (tet; kabuk kalınlığı yok; duvar x = 0 +x).
  V6: L1/L0 100 m/s 0.8675 / WG 0.8462 (1.025), 150 m/s 0.7356 / 0.6867
  (1.071); 1.0 mm mesh 0.8678 (yakınsamış); impuls 0.996–0.999. Görüntüleyici
  hatası düzeltildi: sınır küresi sıfır konumdan kalıyordu → orijin görünmeyen
  bakışlarda (+Y / +Z) model kırpılıyordu.
- K2 ✅ 2026-10-04 Düşme testi: /GRAV kartı (`CrashGravityParams`, hm_cfg r51;
  tüm parça düğümleri + rijit gövde ana düğümleri; 0 ivme yasak — Radioss 0'ı
  1 sayar); `drop_box_shell` (kapalı kabuk kutu, rx / ry ile yüzey / kenar /
  köşe, en alt nokta g'de); senaryo: zemin z = 0, H → v0 = √(2·g·H),
  varsayılan /GRAV −9.81 Z. V7: KE₀/mgH 1.001, temas anı 1.000, zemin
  impulsu (yerçekimi dahil) 0.9997 / 1.0003; yüzey düşmesinde denge %7.1
  (HG 0.17), köşede %0.5. Kartta H ve g alanları, ana sayfada şema.
- K3 ✅ 2026-10-04 Direk yan çarpması: rijit duvar türü `cyl` (/RWALL/CYL,
  hm_cfg r51; eksen noktası + yön + çap; `normal` yalnız ilk hız yönü);
  `pole_beam_shell` (kabuk dikdörtgen tüp, y ekseni; uç halkaları rijit gövde +
  `end_mass_kg`); direk Ø `pole_diameter_mm` (varsayılan 254), kiriş ortasında.
  V8: impuls 0.999; Pm / (4·Mp/L) 0.805 (10 mm), 0.755 (7.5 mm) — kesit
  yerel çökmesi, mesh'le düşüyor (yakınsamadı). Kartta direk Ø ve uç kütlesi.
- K4 ✅ 2026-10-04 ROPS: `rops_frame_shell` tek parça bükülmüş dikdörtgen tüp
  portal (T-birleşimli tüpler dikişli STEP'te ikiz düğüm bırakıyordu → süpürme);
  senaryo: hareketli parçasız koşu (yük zorlanmış hızdan; grup 1 / ilk hız
  yazılmaz), tabanlar /BCS, yük köşesi RBODY + IMPVEL +y (`push_speed_m_s`),
  /SECT z = H/2. V9: plato / 4·Mp/(H − R) 0.996 (15 mm), 0.980 (10 mm);
  ∫F dδ / IE 1.005. Enerji dengesi paydası düzeltildi (sürülen koşuda hep 1
  çıkıyordu). Katalog 6/15 hazır; planlı 7, ayrı faz 2.
- K5 ✅ 2026-10-04 Kafa impaktörü (HIC): katalog örneği `head_impactor` →
  `plate_ball_shell` (aynı şablon, örnek başına kart başlangıç değerleri
  `defaults`); rijit gövde `th_accel` (ana düğüm ivmesi /TH/NODE ilk sırada →
  acc_g / HIC / CFC); `ball_total_mass_kg` (ek = toplam − kabuk). V10: ∫|a|dt /
  (I/m) 0.9995; HIC15 CFC1000 4782 (düz sac, veri). Katalog 7/15.
- K6 ✅ 2026-10-04 FOPS: katalog örneği `fops` → `plate_ball_shell` + düşme
  (H → v0, /GRAV) + toplam kütle; kartta örneğe özgü ek alan kaydı (EXTRAS
  örnek id'si > şablon). V11: KE₀ / mgH 1.0003; ilerleme 97 mm (veri); temas
  kabuk orta yüzeyi + TYPE7 boşluğuyla başlıyor (geometrik g değil). Katalog 8/15.
- K7 ✅ 2026-10-04 S-kiriş: `s_rail_shell` (süpürülmüş S tüp, tek parça);
  /BCS rijit gövde ana düğümüne (`rigid_body`), S-kiriş senaryosunda kızak
  kılavuzu 011111 (yönlendirmesiz koşu dönerek duvardan ayrıldı). V12: impuls
  1.001; ortalama kuvvet / düz tüp W&A 0.234 (eğilmeli çökme, veri). Katalog 9/15.
- K8 ✅ 2026-10-04 Kapı intrüzyonu: `door_beam_shell` (kiriş + yarım silindir
  impaktör, iki parça); senaryo: impaktör rijit gövde + IMPVEL +x + kılavuz
  011111, uçlar /BCS, TYPE7. V13: plato / 8·Mp/L 1.054; ∫F dδ / IE 0.998;
  120 mm'de 25 kN (membran). Kılavuzsuz impaktör kayıp ayrılıyordu. Katalog 10/15.
- K9 ✅ 2026-10-05 Hopkinson çubuğu: `hopkinson_bar` (iki solid silindir);
  senaryo: giriş free + çarpıcı moving, TYPE7, x = Li/4 kesiti. V14: plato /
  ρcvA/2 0.983, süre / 2Ls/c 0.972, dalga yolu 1.051. Katalog 11/15.
- K10 ✅ 2026-10-05 Patlama yüklü plaka: zamana bağlı basınç /PLOAD
  (`CrashPressureLoadParams`, Friedlander, hm_cfg r2021; parça kabuk yüzeyi,
  normal yönü); `blast_plate_shell`; hareketli parçasız koşu basınçla da. V15:
  serbest plaka momentumu / impuls 1.0003; ankastrede 0.65 (mesnet, veri).
  Katalog 12/15.
- K11 ✅ 2026-10-05 Kepçe / taş: `bucket_rock_shell` (kavisli taban + küp-küre
  taş; `add_cube_sphere` ortak); senaryo plaka–küre kurulumu (bölge adları
  parametreli). V16: ∫|a|dt / (I/m) 1.013; denge %3.7 (sert temas, veri).
  Katalog 13/15 — planlı madde kalmadı; kuş (SPH) ve mayın (ALE) ayrı faz kararı.
- K12 ✅ 2026-10-05 Kuş çarpması (kullanıcı: "diğer şablonlara devam et"): SPH
  mermi (`CrashSphProjectileParams`; kapsül kübik kafes, /SPHCEL + /PROP/SPH +
  /MAT/HYDRO, TYPE7 → hedef), katalog `bird_strike` → `blast_plate_shell` +
  kuş kütlesi. V17 rijit hedef: ρAv² 0.945, L/v 0.924, impuls 1.047; ankastre
  plaka veri. SPH parçacıkları animasyonda görünmez (yüzey yok). Katalog 14/15.
- K13 ✅ 2026-10-05 Mayın / araç altı patlama: /LOAD/PBLAST
  (`CrashBlastLoadParams`, zemin yansımalı), yük yüzeyi /SURF/SEG patlamaya
  yönlü; katalog `underbody_blast` → `blast_plate_shell` + TNT / mesafe. V18:
  Hopkinson–Cranz impuls 8.000 / varış 2.000; ankastre taban çökme 183 mm.
  Tam ALE kapsam dışı (ayrı faz). **Katalog 15/15.**

*1.19 — ML tezgahı entegrasyonu* (1.17 + 1.18 bittikten sonra): crash
senaryosu (1.17a) DOE kaynağı, korpus (crash_runs + geometri template_params →
girdi × hedef), vekil model (`ml/crash/`, durability kodundan bağımsız), CV
metrikleri, tahmin; DOE şeması ayrı onay; hedef tanımları (ezilme mesafesi,
ortalama kuvvet …) mühendisten.
- 1.19a ✅ Hedef tanımları: crash_runs sonuçlarından skaler hedef çıkarımı
  (liste mühendisten — örn. ezilme mesafesi, ortalama / tepe kuvvet, yutulan
  enerji); yalnız postprocess fonksiyonları + test.
- 1.19b ✅ Korpus okuyucu `ml/crash/corpus.py`: crash_runs + geometri
  template_params → girdi × hedef tablosu; durability `ml/corpus.py`'den
  bağımsız; test.
- 1.19c ✅ DOE şeması (ayrı onay): senaryo, parametre adları + aralıklar,
  örnekleme; sunucu tarafında toplu koşu → crash_runs.
- 1.19d ✅ Vekil model `ml/crash/`: eğitim + K-fold CV metrikleri (R², MAE
  hedef başına); model kaydı; test.
- 1.19e ✅ Tahmin endpoint'i: parametre → hedef tahmini + CV metrikleri
  (yeni crash yolu, `/solve`'a dokunmadan); test.
- 1.19f ✅ ML tezgahında crash sekmesi: korpus özeti, CV metrikleri, tahmin
  formu (UI, işlevle birlikte sunulabilir kalitede).
- 1.19 notu (2026-10-07): hedefler peak/mean force, yutulan enerji, ezilme;
  RF + K-fold CV; DOE LHS + noktalı yol aralıkları (`/crash/doe/studies`).
  200 koşuluk crash DOE sunucuda (Codespace) koşulacak — operasyonel borç.

*1.20 — Crash arayüz düzeni (2026-10-07) ✅* (Claude Design "Crash BC Sidebar"
+ tasarım adım 3, kullanıcı geri bildirimiyle):
- Crash paneli akordeon: Çarpma / Parçalar / Temaslar; parça başına tek rol
  (hareketli / sabit / serbest); eksik bilgi listesi, eksikte koşu pasif.
- Viewport: rijit duvar düzlemi, hız oku, parça rol etiketleri + rol renkleri
  (hareketli altın, sabit kırmızı, serbest mor), "Modelden seç" duvar noktası,
  üst barda SINIR KOŞ. göster/gizle.
- Adım 5 · Sonuçlar (iş sonucu + çıktı ayarları); crash geçmişi alt dock'ta
  (boyutlanır, yükseklik hatırlanır); "+ Yeni crash vakası" penceresi
  (katalog + hızlı senaryo) — senaryonun sunucu mesh'i, kurulumu ve rolleri
  arayüze yüklenir, koşu 5 · Sonuçlar'da izlenir.
- Malzeme kanunu ve /FAIL açıklamaları 3 · Malzeme adımında.
- Mesh: eğri yüzeylerde quad kalitesi (yüzey başına Algorithm 6), yerel
  remesh (mesh üzerinden yüzey seçimi), "Mesh'i sil"; mesh sonrası CAD gizli.
- 2D mesh parça no ↔ CAD parça no yüzey üzerinden eşlenir (solid + orta yüzey).

*1.21 — LS-DYNA keyword (.k / .dyn) içe aktarma (kullanıcı kararı 2026-10-11)*
Kendi çeviricimiz; yalnız okuma → OpenRadioss kartları, keyword yazma yok,
arayüzde kaynak keyword "≈" ile gösterilir (`docs/LICENSING.md`).
- 1.21a ✅ Parser `app/importers/dyna_k.py`: .k/.dyn → ara model (*NODE,
  *ELEMENT_SHELL/SOLID, *PART, *SECTION_SHELL/SOLID; sabit genişlik, virgüllü,
  uzun format, *INCLUDE); bilinmeyen keyword'ler sayılıp raporlanır.
- 1.21b ✅ Ara model → adaptör mesh parametreleri (`importers/dyna_mesh.py`;
  kartları mevcut starter yazıcısı üretir, /PART/<PID> korunur, uzunluk
  çarpanı dosya → mm mühendisten).
- 1.21c ✅ *MAT_024 (+ *DEFINE_CURVE) → LAW36 (eğri / EPS-ES) ya da LAW2
  (SIGY + ETAN birebir); FAIL → EPS_p_max; birim çarpanları (uzunluk, kütle,
  zaman) mühendisten (`importers/dyna_material.py`). C/P, LCSR, tablo uyarıyla
  çevrilmez.
- 1.21c-2 ✅ *MAT_001 → LAW1; *MAT_020 → /RBODY (part) + LAW1, CMO=1
  CON1/CON2 → ana düğüm /BCS (CMO=-1 yerel çevrilmez). Diğer kanunlar ayrı.
- 1.21c-3 ✅ Hız etkisi: mühendis ε̇ listesi (1/s) verirse *MAT_024 C/P ya da
  LCSR → LAW36 çok eğri (ε̇ = 0 statik + her hız); VP 0/1 → LAW36 VP. Liste
  yoksa uyarı (hız etkisi yok).
- 1.21d ✅ Temas (N2S → TYPE7, S2S → TYPE24, tek yüzey → TYPE7 öz; part /
  part kümesi), *BOUNDARY_SPC_NODE/SET → /BCS, *INITIAL_VELOCITY(_NODE/
  _GENERATION) → /INIVEL, *RIGIDWALL_PLANAR → /RWALL/PLANE, *LOAD_BODY → /GRAV,
  *CONTROL_TERMINATION → t_end (`importers/dyna_setup.py`). Adaptör
  varsayılanları (bariyer hızı, orijin duvarı) kapatılır; yalnız dosyadaki
  uygulanır. Çevrilmeyen her satır raporda nedeniyle.
- 1.21e-1 ✅ `POST /crash/import/dyna` (ana dosya + *INCLUDE dosyaları, birim
  çarpanları, ε̇ listesi) → çeviri raporu; parametreler
  `uploads/crash_import/{id}/import.json`. Koşu başlatmaz.
- 1.21e-2 Kullanıcı kararı (2026-10-12): crash panelinin üstünde ayrı
  "İçe aktar" düğmesi; içe aktarılan model koşulabilir (şema değişikliği).
  - 2a ✅ `GET /crash/import/dyna/{id}/preview`: dış yüzey (kabuk + katı dış
    yüzleri, mm) + yüz başına PID — three.js önizlemesi için.
  - 2b `crash_runs.geometry_id` nullable + `import_id` kolonu (Alembic migration).
  - 2c Koşu: import.json parametreleriyle adaptör → OpenRadioss.
  - 2d Arayüz: "İçe aktar" düğmesi + çeviri raporu (uyarı / atlananlar üstte,
    okundu onayı koşuyu açar) + viewport önizlemesi; `crashDoc.ts`.

*1.22 — Crash ham kart editörü (kullanıcı kararı 2026-10-12; plan onayı 2026-10-13)*
Kullanıcı BC / malzeme kartını popup metin editöründe, düğüm/eleman ID'leriyle
OpenRadioss sözdiziminde yazar. Yalnız crash; kompozitten paralel; dal
(`feature/crash-raw-cards`). Mod A (ek kart) önce; Mod B (üretilen kartı önizle +
düzenle, yerine geçer) A bittikten sonra ayrı onayla. Çift yönlü (kart → form) yok.
- Dayanak: starter deck'teki düğüm/eleman ID'leri gmsh mesh ID'leriyle aynı
  (`th_nodes` bugün de mesh düğüm kümesine karşı denetleniyor).
- Mimari: metin üst katmanlarda opak string (`raw_cards`); yalnız
  `solvers/openradioss.py` deck'e yazar. DB şeması değişmez (crash_runs params JSON).
- Araç öneri yapmaz: doğrulama = starter'ın kendi hata satırları + ID çakışma
  listesi, olduğu gibi gösterilir.
- 1.22a ✅ Backend: `raw_cards` parametresi → `_write_starter` metni `/END`'den
  önce aynen ekler (yorum işaretiyle; `/BEGIN`, `/END` reddedilir; ≤ 200 kB);
  boşsa deck bayt bayt aynı; `crash_runs.request` içinde saklanır.
  Test: `test_crash_raw_cards.py`.
- 1.22b ✅ Backend: ID envanteri — `POST /crash/raw-cards/inventory` (gövde =
  /crash/solve isteği; deck ham kartsız, geçici klasörde üretilir, iş kaydı yok).
  Döner: düğüm/eleman sayı + aralık, ad alanı başına ID'ler (MAT, PROP, PART,
  FUNCT, INTER, BCS, …; /GR*·/SURF·/LINE tek `GRUP` ad alanı — temkinli),
  kullanıcı aralığı (≥ 900000, kullanıcı onayı); ham kart için `collisions`
  (üretilenle), `duplicates` (kendi içinde), `below_user_range`. /solve ile aynı
  parametreler `_starter_params` yardımcısında (davranış aynı).
  Modül `solvers/openradioss_ids.py`. Test: `test_crash_raw_card_ids.py`.
- 1.22c ✅ Backend: "Kontrol et" — `POST /crash/raw-cards/check` (gövde =
  /crash/solve isteği): ham kartlı deck geçici klasörde, `check_starter` yalnız
  starter koşar (engine yok); starter .out ERROR/WARNING blokları aynen
  (`starter_message_blocks`), çıkış kodu, ham kartın deck'teki ilk satırı;
  starter yoksa 503. Gerçek koşu (Docker imajı): üretilenle aynı MAT ID →
  ERROR 79 "DUPLICATE ID", ~1 s. Test: `test_crash_raw_card_check.py`.
- 1.22d ✅ Frontend: popup editör `CrashRawCardsEditor` (monospace, satır no,
  10 karakterlik kolon cetveli + alan çizgileri, Tab = sonraki 10'luk alan, imleç
  satır/kolon/alan); 3 · Malzeme ve 4 · Crash'teki "Ham kart editörü" satırından
  açılır, içerik App'te ortak; viewport "Mesh düğüm" seçimi imlece 10'luk
  alanlarla eklenir; koşu isteğine `raw_cards` (boşsa alan yok).
  Ölçüldü: düğüm seçimi gmsh düğüm no'su = deck düğüm no'su (köşe düğümler);
  Tet10'un ara düğümleri deck'te yok (TETRA4) — seçilirse starter "UNDEFINED
  NODE" verir (1.22c). Eleman ID ekleme YOK: export elemanları 1'den yeniden
  numaralıyor, viewport eleman no'su ile eşlenmedi (ayrı karar).
  Test: `rawCards.test.ts`, `CrashRawCardsEditor.test.tsx`, `CrashPanel.test.tsx`.
- 1.22d-2 ✅ (kullanıcı kararı 2026-10-13, seçenek a) Deck eleman no'su = Gmsh
  eleman tag'i (`openradioss_export`, 1'den yeniden numaralama kalktı; anim
  hücre sırasıyla eşlendiği için etkilenmez). Önizlemeye `element_tags`
  (önizleme eleman id → Gmsh tag) ve `node_tags` (Gmsh düğüm tag'i; `node_ids`
  CalculiX no'su) eklendi; editörde "Eleman ID'lerini imlece ekle", düğümler
  de `node_tags` üzerinden çevrilir (`deckIdsFromPicks`). Viewport düzeltmesi:
  ara düğümler gizliyken (NaN konum) düğüm bulutunun sınır küresi NaN oluyor,
  hiçbir düğüm seçilemiyordu — küre bozulmamış kopyadan kurulur
  (`lib/nodeCloud.ts`). Belgeler: `crashDoc.ts` "Ham kart editörü" bölümü.
  Test: `test_openradioss_export.py` (tag + önizleme eşleşmesi),
  `nodeCloud.test.ts`, `rawCards.test.ts`, `CrashRawCardsEditor.test.tsx`.
- 1.22e ✅ Frontend: editörde "Kontrol et" — `postRawCardsCheck` + `postRawCardsInventory`
  paralel (gövde = CrashPanel'in `buildSolveBody`'si, App üzerinden; koşu ile aynı).
  Sonuç paneli: starter çıkış kodu, ERROR/WARNING blokları aynen, ham kartın deck
  satırı; çakışma / tekrar / 900000 altı listesi (satıra atlar); üretilen deck
  envanteri. Metin değişince "eski"; starter yoksa (503) mesaj, envanter yine.
  Ölçüldü (kiriş, tet): /MAT/LAW1/1 → ERROR 79 DUPLICATE ID + çakışma; 900001 →
  çıkış 0, çakışma yok. Test: `CrashRawCardsCheck.test.tsx`.
- 1.22f ✅ Ham kartlı koşu crash geçmişinde "ham kart" etiketli (`has_raw_cards`
  liste özetinde, `request.raw_cards`'tan; şema değişmez); ML korpusu bunları
  varsayılan dışarıda bırakır (`build_corpus(include_raw_cards=False)`, özet
  `dropped.raw_cards`; ham kart parametre değil, taranamaz); ML Stüdyo → Crash →
  Model'de "Ham kartlı koşuları dahil et" (korpus + eğitim isteğinde
  `include_raw_cards`). Belgeler: crashDoc + mlDoc. Test: `test_crash_ml_corpus.py`,
  `test_crash_runs.py`, `CrashModelPanel.test.tsx`, `CrashHistory.test.tsx`.

*1.23 — Crash kullanıcı geri bildirimi (kullanıcı listesi + plan onayı 2026-10-13)*
Her madde ayrı küçük adım; sıra: A1 → A6 → A7 → A2 → A4+A5 → C2/C3 → C6 → C8 →
C7 → C1 → C5 → B1 → B3 → B2 → D2/D3 → D1 → C4 → E → A3.
- A1 ✅ Şablon "Modeli üret" pop-up'ı: alan içinde sürükleyerek seçip dışarıda
  bırakınca pop-up kapanıyor → yalnız arka plana basılıp orada bırakılınca kapanır.
  `lib/useBackdropClose.ts`; aynı düzeltme Yeni crash vakası, Ham kart editörü ve
  Belgeler pencerelerinde. Test: `useBackdropClose.test.tsx`.
- A2 ✅ Crash malzemesi parça bazında: 3 · Material → 3. grupta parça tablosu (parça,
  kütüphane malzemesi, model listesi Ortak / LAW1 / LAW2 / LAW36 + kopma özeti); LAW
  seçilen parçanın kendi kartı açılır (ortak karttan kopya, /FAIL ayarları dahil).
  Kullanıcı düzeltmesi (2026-10-13): tabloda yalnız LAW adları (her parçanın geçerli
  modeli seçili; "Varsayılan/Ortak" kavramı yok). Alttaki kartta model seçilince (2+
  parça) "Hepsi LAWx olsun mu?" Evet = tüm parçalar / Hayır = uygulanmaz. Ürün ağacı:
  ayrı model yoksa "Tüm parçalar", varsa her parça satırı. Test:
  `CrashMaterialSection.test.tsx`, `CrashPanel.test.tsx`.
- A3 ✅ (2026-10-14) Belgeler örnekleri: LAW1, LAW2 basit kopma, /FAIL denemeleri (belge + test).
  Belgeler → Crash → "Malzeme örnekleri": 4 örnek (kurulum, 3 · Material seçimi, ölçülen sonuç)
  tek kaynaktan `frontend/src/docs/crashMaterialExamples.json`; `test_crash_material_examples.py`
  aynı veriden deck kartlarını denetler. Ölçüldü (crash box, 10 m/s, 4 ms): LAW1 #333 tepe 205.1 kN,
  KE_son 55.49 J (geri sekme); LAW2 εp,max 0.01 #334 183 kabuk silindi. Yolda bulunan hata:
  LAW2 εp,max kopması listing'de parantezsiz ("RUPTURE OF SHELL ELEMENT") yazılıyor, sayılmıyordu
  ("silinen eleman 0") — `parse_ruptures` düzeltildi, kriter "MAT".
  **1.23 TAMAM (2026-10-14).** Beklemede: A5 (akıcı animasyon, kullanıcı "sonra"), C8b (ayrı onay).
- A4 ✅ Animasyonda "ölçek ×1 (gerçek) / ×2 / ×5 / ×10" (yer değiştirme ilk kareye göre
  çarpılır) + veri satırı "son karede en büyük |u| … mm · model boyutuna oranı %…".
  Ölçüldü: Belgeler 1. örnek (crash box, LAW2, 10 m/s, 4 ms; #316) |u|max 8.2 mm = 300 mm
  boyun %2.7'si — gerçek ölçekte katlanma görünmüyordu (koşu kısa; çizim doğru); ×10'da
  ön uçtaki ilk katlanma görünür.
- A5 ❓ (kullanıcı 2026-10-13: istediği gibi değil, sonra bakılacak) Animasyon akıcı: requestAnimationFrame + kareler arası doğrusal ara-değer (konum ve
  renk), hız 0.25× / 0.5× / 1× / 2× (1× = koşu ~3 sn). Test: `CrashAnimationViewer.test.tsx`.
- A6 ✅ Crash sekmesinde durability şablon BC'si (ör. Taylor basıncı) görünmez:
  crash / akış sekmesinde "Modeli üret" pop-up'ı yük/kısıt yerine not gösterir,
  şablon BC'leri yüklenmez (`TemplatePanel` `templateBcs`). Test: `TemplatePanel.test.tsx`.
- A7 ✅ ".rad indir" belirgin düğme: starter (model) ve engine (çözüm kontrolü) ayrı.
  `downloadCrashFile` (blob; farklı kökende `<a download>` yok sayılıyor). Eski "starter .rad"
  bağlantısı göreli yoldu (frontend köküne gidiyordu), düzeldi. Test: `CrashPanel.test.tsx`.
- B1 ✅ (alt adımlar a/b/c; kullanıcı 2026-10-14 kapattı) Şablondan üret: büyük görsel + yalnız şablon alanları + "Model üret" +
  "STEP indir"; Model üret → "Yeni crash vakası" pop-up'ı.
  - B1a ✅ Crash'te hazır senaryolu şablonda Model üret → Yeni crash vakası (o şablonun
    örneği seçili, geometri alanları paneldeki değerlerle; ilk hız, süre, eleman,
    malzeme, CFC, Ishell senaryo kartından). Senaryosu olmayan şablon (crash_box_plate)
    eski pencere + not. Test: `TemplatePanel.test.tsx`, `CrashScenarioCard.test.tsx`.
  - B1a düzeltme (kullanıcı 2026-10-13, acil): Model üret yeniden yalnız geometri üretir
    (ölçüler pop-up'ta; LAW / BC mühendis kurar). Hazır senaryo ayrı "Hızlı senaryo koş"
    düğmesiyle (Yeni crash vakası).
  - B1c ✅ (kullanıcı seçimi B, 2026-10-13) Yeni crash vakası penceresinde "Kurulumu yükle
    (düzenle)": `POST /crash/scenario` `setup_only` — geometri + mesh + kurulum, koşu/deck/kayıt
    yok; yanıtta `solve_request`. Arayüz panellere doldurur (`lib/crashSetupImport.ts`):
    3 · Material LAW/kopma (parça başına dahil), 4 · Crash çarpma/duvar/yön/hız/açı, yerçekimi,
    süre, roller, temaslar, ek tanımlar (ilk hız, kilit, sabit hız, kütle/kızak + rayda),
    eleman bayrakları. Çıktı ayarları (kesit, TH, CFC) içe aktarılmaz — panel varsayılanı.
    Test: `test_crash_scenario.py`, `crashSetupImport.test.ts`, `CrashPanel.test.tsx`.
  - B1b ✅ Crash'te hazır senaryolu şablonda panel sade: büyük görsel + şablon +
    Model üret + STEP indir (alanlar pencerede). STEP indir tüm sekmelerde, geometri
    kaydı açmadan: `POST /templates/{id}/step` (geçici dosya). Test:
    `test_templates_api.py`, `TemplatePanel.test.tsx`.
    Kullanıcı düzeltmesi: senaryosuz şablonda da (crash_box_plate) panel sade; ölçüler
    Model üret pop-up'ında düzenlenir (onayda yeniden okunur).
- B2 ✅ (2026-10-14) Duvar konumunu kaydet (opsiyonel, düğmeyle) → sonraki vakada listeden seç.
  "Duvarı kaydet" (ad isteğe bağlı; yoksa "nokta (x, y, z) · normal ±A") + "Kayıtlı duvar" listesi
  (seçince nokta + yön dolar) + sil. Tarayıcıda (`crashWallPresets`; DB değişmedi — sunucuda
  ortak liste istenirse yeni tablo, ayrı onay).
- B3 F5 / yeni case sonrası son çalışmayı aç; geçmişten geometri/koşu yükle.
  - B3a ✅ (2026-10-14) Geçmişte satır başına ⤓ "yükle": koşunun geometrisi + sunucudaki mesh
    (`/files/meshes/{id}_d{2|3}.preview.json`; boyut kaydı yok → "—", şema/sayılar önizlemeden) +
    kurulumu (`request`, B1c ile aynı içe aktarma) panellere. Koşu yok.
  - B3b ✅ (2026-10-14) Son crash çalışması (geometri + geçmişten yüklenen koşu + mesh boyutu)
    tarayıcıda (`crashLastWork`); F5'te kendiliğinden açılır (koşuysa kurulumuyla). "Yeni Case
    Başlat" kendiliğinden açmayı kapatır; boş ekranda "Son çalışmayı aç". Kaydedilmemiş panel
    düzenlemeleri dahil değil. B3 ✅.
- C1 Dışa aktar: grafik (PNG/CSV) + animasyon video. Sıra kullanıcı kararı (2026-10-14): C1 → C7.
  - C1a ✅ (2026-10-14) Animasyon video: "Video indir (MP4 / WebM)" — MediaRecorder, ek bağımlılık yok; 1280×720, 30 kare/s, üstte koşu + t + skaler, altta renk ölçeği.
  - C1b ✅ (2026-10-14) Grafik PNG / CSV: her crash grafiğinin başlığında PNG (veriden 1400 px yeniden çizim) + CSV (virgül / nokta ondalık). C1 ✅.
- C2 ✅ Animasyonda "Mesh" düğmesi (yüz kenarları, her karede deforme konumla) + elemana
  tıklayınca değer satırı: yüz no, parça, seçili skaler (eleman skalerinde o elemanın,
  düğüm skalerinde en yakın düğümün değeri), t. Döndürme sürüklemesi seçim sayılmaz.
- C3 ✅ Animasyonda "Rijit duvar" düğmesi: koşu isteğinden (`barrier.wall`) düzlem (model
  boyutunun 1,2 katı kare) ya da silindir (çap, eksen); duvarsız koşuda düğme yok.
  Test (C2/C3): `CrashAnimationViewer.test.tsx` (`faceEdges`, `wallFromRequest`).
- C4 ✅ (2026-10-14) Nokta kütle + parça "Rijit" (flexible/rigid) seçeneği. Ek tanımlar'da
  "Ek kütle" kartı (/ADMAS, toplam / düğüm başına; tek noktalık bölge = nokta kütle); parça
  satırında "Rijit gövde" (ek kütlesiz /RBODY, kullanıcı kararı A: Ikrem 1 — Radioss varsayılanı 0
  düğümleri rijit duvardan çıkarıyordu, WARNING 446); /RBODY kartında "rijit duvarla temas" seçeneği.
  Ölçüldü: #154 (plaka + küre) küre parça kartıyla rijit → Fmax 10.263 kN, IE 1.951 J (bölgeyle aynı).
- C5 Karşılaştır: iki pencerede animasyon, grafik + skaler karşılaştırma.
  - Grafik + skaler karşılaştırma 1.16b'den beri var (≤ 6 koşu, eğri seçimi, skaler tablosu).
  - C5a ✅ (2026-10-14) "Animasyon yan yana": 2 koşu viewport'ta yan yana, ortak fiziksel zaman (oynat / kaydırıcı / hız); kısa koşu son karede ("koşu sonu").
  - C5c ✅ (2026-10-14, kullanıcı: "geçmişin altında değil, yeni sayfada one pager") Karşılaştırma
    tam ekran tek sayfa: koşu kartları + deforme şekil yan yana (3+ koşuda çift seçimi) + skaler
    tablosu + eğriler (seçilebilir + iç enerji). Viewport'taki "Animasyon yan yana" düğmesi kalktı.
  - C5b ✅ (2026-10-14) Ortak renk ölçeği (aynı skalerde iki koşunun min–max birleşimi) + kamera eşleme; ikisi de açılıp kapanır, varsayılan kapalı. C5 ✅.
- C6 ✅ Enerji grafiği (kinetik, iç, hourglass, temas) + enerji özeti. TH global sütunları:
  temas enerjisi, dış iş, toplam (IE + KE + dönme + HG − dış iş) eğrisi; 5 · Sonuçlar'da
  "Enerji · J" grafiği + özet (son/maks, HG/IE %, temas/IE %, |ΔE|/E %). Geçmiş 📈 aynı
  seriler. Test: `test_crash_energy_c6.py`, `CrashPanel.test.tsx`.
- C7 Post-process alanları: yönlü deformasyon, eşdeğer plastik şekil değiştirme
  (min/maks/ort), gerçek ölçek eleman.
  - C7a ✅ (2026-10-14) Yönlü yer değiştirme uₓ/u_y/u_z (istemcide, konum − ilk kare) +
    seçili skalerin karedeki min/maks/ort (aritmetik, silinen hariç). Gerçek ölçek ×1
    zaten A4'te (kullanıcı: "aynı şey", 2026-10-14). C7 ✅.
- C8 ✅ (2026-10-14) Kuvvet grafiği açıklaması: y ekseni adı + birim + 1·2·2.5·5 ölçek, kılavuz çizgi, tepe noktası, ortalama kuvvet (kullanıcı kararı B: temas aralığında impuls / süre; aralık |F| > tepenin %1'i, gölgeli), kısa veri kaynağı açıklaması.
- C8b Ortalama ezilme kuvveti (yer değiştirme tabanlı): emilen enerji / ezilme mesafesi; hareketli parçanın arka düğümü için düğüm TH çıktısı gerekir (çıktı kartı + backend + UI). Ayrı onay.
- D1 ✅ (2026-10-14) Ham kart editörü: üretilen modelin kartlarını export / görüntüle (Mod B ilk yarı).
  4 · Crash "Deck'i görüntüle": `POST /crash/deck/preview` (gövde = /crash/solve isteği, ham
  kartlar dahil; geçici klasör, solver koşmaz) → starter + engine metni + kart listesi
  (`deck_outline`). Pencere: kart listesi (aranır) + seçili kart bloğu satır no'lu, salt
  okunur; starter / engine .rad indir. Test: `test_crash_deck_preview.py`, `CrashDeckViewer.test.tsx`.
- D2 ✅ (2026-10-14) Çözüm kontrolü kartı: bitiş süresi, Δt ölçeği (güvenlik katsayısı), kütle
  ölçekleme tek yerde + açıklama. 4 · Crash'te "Çözüm kontrolü" akordeonu (süre çarpma grubundan,
  zaman adımı çıktı ayarlarından taşındı; payload aynı); son koşunun Δt_min / eklenen kütle oranı.
- D3 ✅ (2026-10-14) Koşu sırasında adım sayısı / anlık adım / Δt canlı. Engine stdout'u
  ("NC= … T= … DT= … ERR= … DM/M= …", "ELAPSED / REMAINING TIME") okunur — eski ayrıştırıcı
  bu biçimi tanımıyordu, bitişteki CPU tablosunu "cycle 1" sanıyordu (düzeltildi). Panelde:
  adım, t / t_end, Δt, en küçük Δt, DM/M, %, geçen, kalan (Radioss tahmini).
- E ✅ (2026-10-14) Mesh: eğriliğe göre adaptif boyut (Gmsh curvature sizing). 2 · Mesh'te
  "Eğriliğe göre incelt": 2π başına eleman n + en küçük boyut (mühendis girer; ikisi zorunlu,
  en küçük ≤ eleman boyutu). Backend `curvature_elements` / `curvature_min_size` →
  `Mesh.MeshSizeFromCurvature`, alt sınır yerel yüzey boyutlarıyla birlikte. Ölçüldü (door_beam,
  30 mm, n 100, min 1): eğri yüzler 38 → ~380 eleman, düzlemler aynı. Test:
  `test_mesh_curved_quad.py`, `meshCurvature.test.ts`.

*1.24 — Crash: can crush şablonu, genel temas, yay, malzeme kütüphanesi (kullanıcı listesi 2026-10-14)*
Her madde ayrı küçük adım ve ayrı PR; sıra: a1 → a2 → b1 → b2 → c1 → c2 → c3 → d → e → f → g.
Not (2026-10-14): b1/b2 "yay" kullanıcı isteğinin yanlış okunmasıyla yazıldı (istenen
**springback** = geri sekme idi); kullanıcı kararıyla kaldı, geri sekme c1–c3'te.
- a1 ✅ (2026-10-14) Genel temas (backend): `CrashContactParams.all_parts` (yalnız TYPE24;
  master/slave verilmez). Tüm kabuk parçalar `/SURF/PART/7901`, tüm solid parçalar
  `/SURF/PART/EXT/7902`; yalnız biri varsa tek öz TYPE24 (surf_ID2 = 0), ikisi de varsa üç
  TYPE24 (kabuk öz, solid öz, kabuk ↔ solid), aynı bayraklarla. Çift temaslarla birlikte
  kullanılabilir; /INTER kimlikleri sırayla, `/TH/INTER` hepsini içerir. ≈ LS-DYNA
  AUTOMATIC_SINGLE_SURFACE / Ansys Body Interaction. Test: `test_crash_contact.py`.
- a2 ✅ (2026-10-14) Genel temas (UI): 3 · Temaslar kartında "Parça çifti / Tüm model"
  kapsam seçimi. Tüm model: parça seçimi gizlenir, TYPE24 sabit (TYPE7 kapalı), bayraklar
  aynı; istekte `{type: 24, all_parts: true}` (master/slave yok). Özet ve ürün ağacında
  "tüm model (genel)". Geçmişten / içe aktarmadan yükleme `all_parts`'ı korur. Test:
  `CrashPanel.test.tsx`.
- b1 ✅ (2026-10-14) Yay elemanı (backend): `springs[]` → `/PROP/TYPE4` (hm_cfg radioss140:
  Mass; K C; fonksiyon yok) + `/PART` (mat_ID 0) + `/SPRING` (hm_cfg radioss110) + `/TH/SPRING/6`
  (FX FY FZ → `th_spring_<k>_<var>`). Uçlar: rijit gövde ana düğümü ya da nokta (mm; yeni düğüm,
  `fixed=True` → `/GRNOD/NODE/994k` + `/BCS/4k` 111 111). Birim: K N/mm → kN/mm (÷1000), C N·s/mm →
  kN·ms/mm (aynı sayı), kütle kg. Parça kimliği SPH parçalarından sonra, eleman kimliği mesh en
  büyüğü + k. Varsayım (resim yok): tek eksenli doğrusal yay yeterli; eğri (fct_ID), kopma
  (DeltaMin/Max), skew sonraya. Test: `test_crash_spring.py`.
- b2 ✅ (2026-10-14) Yay kartı (UI): 4 · Ek tanımlar → "Yay" kartı. A/B ucu: Kütle / kızak kartı
  (listeden; istekte `rbody_<sıra>`) ya da nokta (x y z mm, "Sabit" kutusu). K N/mm, C N·s/mm,
  yay kütlesi kg. Hedef çipi yok. Özet "Kütle / kızak #1 ↔ nokta (…) sabit · K … N/mm".
  İçe aktarma `springs[]`'i karta çevirir (kızak adı → kart). Test: `CrashLoadCards.test.tsx`,
  `crashSetupImport.test.ts`.
- c1 ✅ (2026-10-15) Geri sekme (springback) metrikleri (backend): animasyon karelerinden tepe |u| (t), son |u|,
  geri sekme = tepe − son ve oranı; model + parça bazında `scalars`. Explicit devam yaklaşımı
  (çarpıcı geri sekip temas kesilene kadar koşu). `/IMPL/SPRBACK` (implicit) ayrı faz.
  Gerçek koşuda görüldü: Radioss `Displacement` rijit ötelemeyi içerir → serbest parçada |u| ezilmeyi
  değil yolu ölçer (#370 LAW1 seken kutu: |u| 181.7 mm son karede, geri sekme 0). Kullanıcı kararı D
  (2026-10-15): iki tanım yan yana — mutlak (`model_disp_*`, `springback_mm/_ratio`, `part_<id>_disp_*`,
  `part_<id>_springback_*`; sabit parçada deformasyon) + öteleme çıkarılmış |u − ū(parça)|
  (`model_def_*`, `springback_def_mm/_ratio`, `part_<id>_def_*`, `part_<id>_springback_def_*`; rijit
  dönme kalır). `postprocess/crash_springback.py`; `OpenRadiossAdapter.parse_results` kareleri bir kez
  çevirir, `anim.json` önbelleğini de yazar; hata koşuyu düşürmez. Ölçüldü (aynı kareler): #370 LAW1
  def tepe 4.73 mm @ 1.0 ms → son 1.34 mm, geri sekme 3.39 mm (%72); #371 LAW2 def 122.6 mm 20 ms'de
  hâlâ artıyor (ezilme sürüyor) → geri sekme 0 — sekme için koşu uzatılmalı (mühendis). Eski koşular
  için değer yok (yeniden işleme ayrı). Test: `test_crash_springback.py`.
- c2 `/DAMP` (Rayleigh) kartı: salınımı söndürmek için; backend + Çözüm kontrolü UI (iki PR).
  Kullanmak mühendisin kararı; varsayılan yok.
  - c2-1 ✅ (2026-10-15) Backend: `CrashDampingParams` (α 1/s, β s, `part_ids` boş = tüm parçalar,
    Tstart / Tstop ms; α = β = 0 reddedilir) → istekte `damping`. Deck: `/GRNOD/PART/9930` +
    `/DAMP/1` satır düzeni resmi hm_cfg radioss110 `Damp.cfg`'den (Alpha Beta grnod skew Tstart Tstop;
    α/1000 → 1/ms, β·1000 → ms). Starter echo'su doğrulandı (BETA 1e-3 / 1e-2 ms, STOP 1e30,
    "MAX TIME STEP FACTOR 1.0"). Ölçüldü (#370 LAW1 seken kutu kurulumu): sönümsüz Δt_min 5.4e-4 ms,
    IE_son 102 J, def geri sekme 3.39 mm → β 1e-6 s (#372): Δt_min 3.1e-4 ms, IE_son 3.9 J, def son
    0.58 mm, geri sekme 4.15 mm (%88). β 1e-5 s (#373) sonuçları #372 ile birebir aynı; listing'de
    uyarı yok — Radioss β'yı kendi içinde sınırlıyor olabilir (gözlem, doğrulanmadı). Test:
    `test_crash_damp.py`.
  - c2-2 ✅ (2026-10-15) UI: 4 · Crash → Çözüm kontrolü kartında "Sönüm (Rayleigh)" — "Sönüm ekle"
    kutusu, α (1/s), β (s), başlangıç / bitiş (ms), çok parçalı modelde parça çipleri (seçim yok = tümü),
    açıklama (öneri yok). Özet satırı "/DAMP β … s · #p", başlık "değiştirildi". `OutputState.damp*`,
    `outputPayload().damping` (kapalı = null), istemcide backend kuralı (α = β = 0, ters pencere
    gönderilmez). Geçmişten / senaryodan yükleme `dampingFromRequest`. Belgeler: crashDoc "Sönüm
    (Rayleigh)". c2 ✅. Test: `CrashSolverControlCard.test.tsx` (+4), `CrashOutputCard.test.tsx`.
- c3 ✅ (2026-10-15) Sonuçlar'da "Geri sekme" kartı + |u|max–zaman eğrisi (UI). `CrashSpringbackCard`:
  tablo (kapsam × tanım: tepe, t tepe, son, geri sekme, oran %) c1 skalerlerinden; eğri istemcide
  `lib/crashSpringback.ts` (animasyon `positions` − ilk kare; iki tanım; yüzey düğümleri — katıda iç düğüm
  yok, öteleme çıkarılmış eğri skalerden biraz farklı olabilir). Kapsam çipleri. Skaler yoksa kart ve
  animasyon isteği yok. Parça adı deck kartı kimliği (`/PART/n`; mesh #p → /PART/p+1) — animasyon
  `PART_ID`'si böyle geliyor (deforme şekildeki "parça #" de aynı). Ölçüldü: #374 crash box 4 ms — mutlak
  8.203 mm (t 4.0 = son, geri sekme 0), öteleme çıkarılmış tepe 0.491 @ 3.4 ms → son 0.483 (%1.7);
  eğrinin son değeri tabloyla aynı. crashDoc "Geri sekme · mm". c1–c3 ✅.
  Düzeltme (kullanıcı onayı 2026-10-15): parça adları mesh no'suyla — deck yazıcı `part_map.json`
  (kart → mesh) yazar, c1 skalerleri `part_<mesh>_…` (haritada olmayan yay / SPH kartı parça satırına
  girmez); eğri `cardToMeshPart` (= kart − 1, `_rid` kuralı). Gerçek koşuda "Parça #0" ve "#0" eğrisi.
  Bu düzeltmeden önceki koşularda (#370–#374) parça anahtarları kart kimliğiyle kaldı.
  Test: `test_crash_springback.py` (+2), UI testleri.
  Test: `crashSpringback.test.ts`, `CrashSpringbackCard.test.tsx`.
- d Alüminyum can crush şablonu (Ansys Explicit örneği, 2026-10-14 resmi): ince cidarlı
  silindir kabuk (alt/üst kapak, bir uçta delik) + açıyla gelen C-kesit çarpıcı (rijit, ilk hız)
  + sabit taban bloğu. Genel temas (a1/a2), parça rolleri. Çıktı: deformasyon, von Mises,
  eşdeğer plastik şekil değiştirme, geri sekme (c1–c3).
- e Malzeme araştırması: `docs/CRASH_MATERIALS.md` — literatürden Johnson-Cook + σ–ε
  eğrileri (Al 5xxx/6xxx/7xxx, DP/HSLA çelikler, PP/ABS/PC), kaynak listeli. Yalnız doküman.
  Ticari/lisanslı kart (vendor, GRANTA) kopyalanmaz.
- f Kütüphaneye crash verisi (seed migration). Şema kararı bekleniyor (JC için yeni JSON
  kolon önerildi).
- g Malzeme kartında kütüphane eğrisi seçimi + σ–ε grafiği.
*1.25 — Crash kullanıcı geri bildirimi 2 (2026-10-14; karşılaştırma + canlı ilerleme + skaler tablo)*
Sıra: c1 → c2 → d → b → a → e; sonra 1.24 c1–c3, d, e–g (birleşik sıra kullanıcı dokümanında).
- c1 ✅ (2026-10-14) Karşılaştırma eğrileri (backend): `GET /crash/runs/compare` varsayılanı kayıtlı
  **tüm** eğriler (enerji IE/KE/HG, temas, kesit, düğüm, CFC); 1.17e2'deki yalnız `_force` / `acc_g`
  süzgeci kaldırıldı, `curves=` ile daraltma aynı. Test: `test_crash_runs.py`.
- c2 ✅ (2026-10-14) Karşılaştırma eğri seçici (UI): `<optgroup>` Kuvvet / Enerji / Temas / Kesit / İvme /
  İmpuls / TH kanalları; okunur ad + birim ("Duvar kuvveti · CFC 600 (kN)", "Temas 2 kuvveti (kN)"); impuls
  eğrisi artık kuvvet sayılmıyor (birim N·s, ortalama çizgisi yok). `crashRunFormat.ts`
  `curveGroup` / `curveLabel`. Test: `crashRunFormat.test.ts`.
- d ✅ (2026-10-15) Skaler tablo yeniden tasarım: okunur satır adı ("Duvar kuvveti, tepe", "İç enerji, son",
  "Kesit 1 kuvveti, tepe"), birim ayrı sütun, koşu başlığı #no + ad + geo · t_end, 14–15 px font, ad sütunu
  yatay kaydırmada sabit. Oranlar (enerji dengesi, eklenen kütle) % olarak; |v| < 1 üslü yerine ondalık
  (0.8660); silinen eleman tam sayı. Yalnız görünüm; veri / skaler kümesi aynı. Test:
  `CrashComparePage.test.tsx`, `CrashHistory.test.tsx`.
- b ✅ (2026-10-15) Karşılaştırmada N koşu yan yana: Sol/Sağ seçimi kalktı, çözülmüş koşuların hepsi
  ızgarada (2 → 2 sütun, 3 → 3, 4 → 2×2, 5–6 → 3); 3+ koşuda çiplerle çıkar / ekle (en az 2). Ortak
  zaman, ortak renk ölçeği (tüm pencereler aynı skalerdeyse min–max birleşimi) ve kamera eşleme N
  pencereye. "Büyük pencere": ızgara tam ekran; ESC yalnız büyük pencereyi kapatır (yakalama evresi),
  sayfa açık kalır. Hücre ≥ 540 px (tuval ≥ 240 px + denetimler). Test: `CrashCompareAnim.test.tsx`,
  `CrashHistory.test.tsx`.
- a Canlı ilerleme paneli her koşuda: başlar başlamaz görünür, bitince/donunca son değerle kalır; DOE'de de.
  İki adıma bölündü (2026-10-15): DOE örnekleri sunucuda `wait=True` ile sırayla koşuyor, çalışan örneğin
  `job_id`'si dışarı verilmiyor → DOE canlı paneli backend değişikliği ister (ayrı katman).
  - a1 ✅ (2026-10-15) Koşu paneli (UI): `CrashLiveProgress` evreli — "Başlıyor" (ilk adım gelene kadar
    değerler —) → "Koşuyor" → "Bitti / Başarısız · son canlı değerler" (geçen süre durur, kalan —).
    Son canlı değerler yalnız koşu sürerken alınır (bitmiş işte hub'ın "cycle 1" satırı kullanılmaz);
    yeni işte sıfırlanır. 30 s (`STALE_S`) yeni değer yoksa "son güncelleme … önce" (veri). Senaryo /
    şablon / panelden başlatılan her koşu aynı panelden geçer. Ölçüldü: #335 crash box 4 ms → Adım
    7400, t 4 / 4 ms, %100 bitince kaldı. Test: `CrashLiveProgress.test.tsx`, `CrashPanel.test.tsx`.
  - a2 DOE: çalışan örneğin işi (job_id) dışarı verilir + DOE panelinde aynı canlı panel.
    Kullanıcı kararı (2026-10-15): A — bellekte çalışan iş kaydı, şema değişmez.
    - a2-1 ✅ (2026-10-15) Backend: `doe/crash_runner.py` örneği `wait=False` ile kurar (iş + job_id),
      toplanan çözüm işini aynı süreçte koşturur; bu sırada `_CURRENT[study_id] = {case_index, job_id}`,
      örnek durumu `running`. `GET /crash/doe/studies/{id}` → `current_job_id`, `current_case_index`
      (yoksa null). Son durum işin `job.json`'undan. `crash.py` / `/solve` değişmedi. Ölçüldü: çalışma #4
      (crash box 4 ms, 2 örnek) — örnek 0 iş `fead4038…` %4 → %50 → %99.9, örnek 1 `0ef38431…`, sonra
      null; koşular #336, #337 solved. Test: `test_crash_doe_api.py::test_current_job_while_case_runs`.
    - a2-2 ✅ (2026-10-15) UI: `CrashDoeLive` — DOE çalışma panelinde ilerleme çubuğunun altında
      "Örnek #i · N örnekten · iş …" + `CrashLiveProgress`; `current_job_id` (liste 5 s'de bir) →
      `/crash/jobs/{id}` 1,5 s yoklama. Örnek değişince yeni iş ("Başlıyor"); çalışma bitince son
      örneğin son canlı değerleri ("Bitti"); başka çalışmaya geçince temizlenir. Örnekler arasında
      (sıradakinin geometri / mesh'i, iş yok) "Çalışma sürüyor · sıradaki örnek hazırlanıyor" notu —
      tarayıcıda bu arada "Bitti" göründüğü görülüp eklendi. Ölçüldü: çalışma #5 (20 örnek) örnek #2
      adım 1200 %16.2 canlı; #6 (3 örnek, 10 ms) son örnek adım 18500 %100. 1.25a ✅.
      Test: `CrashDoeLive.test.tsx`, `CrashDoePanel.test.tsx`.
- e ✅ (2026-10-15) Model 1 kurulumu: Süre 20 ms + Ek tanımlar → Kütle / kızak (kutu_arka, 100 kg,
  serbest; kullanıcının #321 kurulumu). Gerekçe ayrı not (`TrainingGroup.note`); T1–T5'e "Ölçülen"
  satırı (`TrainingTest.measured`, koşu no ile): #361 LAW1 impuls 2017 N·s ≈ 2·m·v, KE_son 5038 J;
  #362 LAW2 Fmax 119.6 kN, IE 4320 J; #364 b500/n0.5 155.5 kN; #365 a400 201.7 kN; #366/#367 15 m/s
  c 0 → 0.05: 121.3 → 152.6 kN; #368 sıcaklık: T3b'den fark < %1.5; #369 LAW36 126.5 kN. Gözlem (veri):
  T2'nin ilk adımı (b = 0, n = 1) varsayılan → T1b ile aynı koşu. `crashTraining.ts` + `CRASH_EGITIM.md`
  birlikte. T6–T7 aynı modelde, değerleri yenilenmedi. Test: `DocsDialog.test.tsx`.
  Eski not: T1–T5 eğitim senaryoları: kızak kütlesi + uzun t_end (gerekçe: crash box 1.2 kg, 59 J, ~1 mm ezilip
  duruyor; katlanma için arka kütle gerekir); örnek koşu değerleri yenilenir.

*Ertelenen (Faz 1 dışı / ayrı karar)*
- Karma model: kabuk kutu + solid plaka aynı mesh'te (mesh katmanı değişikliği)
- Kesit yerel ekseni (N1–N3) — FN/FT ayrımı gerekirse
- Midsurface kenar ikizlenmesi, parça numarası tutarlılığı (durability ile ortak)
- Araç (NHTSA) ve IIHS bariyer modelleri — lisans (LSTC ftp kimlik istiyor),
  proje kuralı (Ansys / LS-DYNA yok) ve hesap gücü (MPI yok; Camry 8 MPI ile
  ~15 sa)

## Faz 2 — CFD / akış (OpenFOAM)

**Sıra değişikliği (kullanıcı, 2026-10-07):** Faz 2 artık OpenFOAM ile akış;
kompozit Faz 3'e kaydı. **Durum: BAŞLADI (kullanıcı onayı 2026-10-08)** —
arayüzde "AKIŞ · OpenFOAM" sekmesi iskeleti (plan + açık kararlar, çözücü
bağlı değil). 2.0 / 2.1 aşağıdaki açık soruların 1 ve 2'sinin cevabını bekliyor. Faz 0 (CalculiX `/solve`) ve Faz 1 (crash) yollarına dokunulmaz;
yeni CFD yolu eklenir. Solver/mesh çağrıları yalnız sunucuda (Docker imajı).
ML en sonda (2.9), crash'teki sırayla aynı.

Mimari: `OpenFoamAdapter(SolverAdapter)` — `InputArtifact` bir **case klasörü**
(`0/`, `constant/`, `system/`); üst katmanlar farkı bilmez. CFD mesh'i
`MesherAdapter`'ın CFD implementasyonu (`mesh/cfd_mesher.py`): basit
geometride `blockMesh`, STEP geometride Gmsh → STL → `snappyHexMesh`.
İlerleme: solver log'undan iterasyon / residual (crash'teki websocket deseni).

**Kullanıcıya açık sorular (başlamadan önce):**
1. ✅ ESI seçildi (2026-10-08). OpenFOAM dağıtımı + Docker imajı: ESI (openfoam.com, v2406/v2412 —
   resmi Docker imajı var) mı, Foundation (openfoam.org v12) mı?
2. İlk hedef vaka: iç akış (boru/kanal — basınç düşümü) mı, dış akış
   (silindir/küre/araç — Cd/Cl) mı?
3. Akış tipi ilk adımda: daimi sıkıştırılamaz (`simpleFoam`; laminer +
   RANS k-ω SST) — zamana bağlı (`pimpleFoam`) sonra mı?
4. Yeni bağımlılık: alan sonuçları için PyVista (VTK okuma) — 2.5'te mi,
   yoksa önce bağımlılıksız (function object metin çıktıları) mı?
5. DB şeması: `cfd_runs` tablosu (crash_runs deseni) — Alembic migration.

**Mikro-adımlar (her biri ayrı onay; bir adım bitince dur):**
- 2.0 ✅ (2026-10-08) Altyapı: OpenFOAM Docker imajı (`.env`: `OPENFOAM_DOCKER_IMAGE`),
  Codespace devcontainer'a ekleme; duman testi (resmi `pitzDaily`
  öğretici vakası `simpleFoam` ile koşar, log okunur). Lisans notu
  `LICENSING.md` (GPL, sunucu tarafı). **Sonuç:** ESI v2412 resmi imajı
  (`opencfd/openfoam-default:2412`); `app/solvers/openfoam.py` (imaj, `docker
  run` komutu, log → iterasyon + başlangıç residual), `scripts/openfoam_smoke.py`;
  pitzDaily 281 iterasyonda yakınsadı (SIMPLE residualControl), ~13 s; test
  `tests/test_openfoam_runtime.py` (Docker testi imaj yoksa atlanır). Codespace:
  docker-in-docker zaten var, imaj isteğe bağlı çekilir.
- 2.1 ✅ (2026-10-08) Case yazıcı: `solvers/openfoam.py` `build_input` — parametrelerden
  `0/U`, `0/p`, (`k`, `omega`, `nut`), `constant/transportProperties` /
  `momentumTransport`, `system/controlDict|fvSchemes|fvSolution` üretimi;
  Docker'sız birim testi (dosya içerikleri). **Sonuç:** `app/solvers/openfoam_case.py`
  (`CfdCaseParams`: ν, ρ, yamalar inlet/outlet/wall/symmetry/empty, laminer | k-ω SST —
  giriş k/ω yoğunluk I ve uzunluk ölçeği L'den, SIMPLE ayarları; varsayılanlar pitzDaily),
  `OpenFoamAdapter.build_input` → case klasörü. Kontrol: yazıcının dosyaları + pitzDaily
  ağı (`scripts/openfoam_case_check.py`) — k-ω SST 382 iterasyonda yakınsadı (~15 s);
  laminer aynı ağda (Re ≈ 25 000) 2000 iterasyonda yakınsamadı (daimi laminer çözüm
  yok; laminer doğrulama 2.3'te düşük Re kanalda). Test `tests/test_openfoam_case.py`.
  İlk vaka kararı gelmeden yapıldı: yazıcı iç/dış akıştan bağımsız; varsayım iç akış (2.3 kanal).
- 2.2 ✅ (2026-10-08) Koşu + ilerleme: `submit` / `poll_status` Docker'da; log'dan iterasyon
  + başlangıç residual'ları; `/cfd/solve` + `/cfd/jobs/{id}` (+ ws); test.
  **Sonuç:** `OpenFoamAdapter.submit` (Docker; `blockMeshDict` varsa önce
  blockMesh, ardından controlDict'teki application; çıktı satır satır →
  `SolverLogStream`, her iterasyonda geri çağırma), `parse_results` residual
  geçmişi + yakınsama; `app/api/cfd.py` (arka plan işi, `uploads/cfd/<id>/job.json`,
  canlı residual geçmişi GET'te, ws). Mesh şimdilik ham `blockMeshDict` metni
  (2.3 parametrik kanal, 2.5 STEP). Canlı deneme: pitzDaily k-ω SST, 2 s'de bir
  iterasyon + residual'lar, 382 iterasyonda yakınsadı (~12 s). Yüzde = iterasyon /
  iterasyon sınırı (yakınsayınca erken biter). DB kaydı yok (2.4, ayrı onay).
  Test `tests/test_cfd_api.py` (sahte süreç + gerçek Docker).
- 2.3 ✅ (2026-10-08) İlk doğrulama vakası (blockMesh): 2B kanal laminer Poiseuille —
  basınç düşümü analitik değerle karşılaştırılır (V-C1, veri olarak).
  **Sonuç:** `app/mesh/cfd_blockmesh.py` (parametrik kanal: L, H, D, nx/ny/nz, 2B/3B,
  duvara sıklaşma; yamalar inlet/outlet/walls/frontAndBack; Poiseuille referansı),
  case yazıcıda izleme fonksiyonları (`pAvg_<yama>` alan ortalaması p, `uMax`),
  `read_monitors`; `/cfd/solve` `channel` alanı → Δp (kinematik + Pa) ve
  `reference` (analitik / CFD / % fark). V-C1 (Re 10, L = 20H, 200×20 hücre,
  643 iterasyon, ~7 s): Δp %+2.9 (girişteki gelişme bölgesi dahil, L_e ≈ 0.5H),
  u_max %−0.5. Test `tests/test_cfd_channel.py`.
- 2.4 ✅ (2026-10-08) Sonuç okuma (`parse_results`): function object çıktıları (forces /
  forceCoeffs, patch ortalama basınç / debi), residual geçmişi →
  `ResultSet`; `cfd_runs` kaydı (şema ayrı onay).
  **Sonuç:** case yazıcıda `forces` bloğu (`CfdForces`: gövde yamaları, CofR,
  sürükleme/kaldırma/yunuslama yönleri, U_ref, l_ref, A_ref, son N iterasyon) →
  `forceCoeffs` (`coeffs`) + `forces_total` + yama başına `forces_<yama>`;
  `read_forces`: Cd/Cl/Cs/Cm son değer + son N ortalama ve std, kuvvet/moment
  toplam/basınç/viskoz bileşenleri, katsayı geçmişi; API'de CdA. **`cfd_runs`
  tablosu** (kullanıcı onayı 2026-10-08; migration `b8c9d0e1f2a3`, geometri
  bağı isteğe bağlı) + `/cfd/runs` (liste, ayrıntı + eğriler, karşılaştır, ad /
  dışla). Canlı: pitzDaily duvarları Cd 0.318 (son 50 ort. 0.320, std 0.003),
  toplam = yamaların toplamı. Test `tests/test_cfd_forces_runs.py`.
- 2.5 ✅ CFD mesh: STEP → Gmsh yüzey STL → `snappyHexMesh` (arka plan
  blockMesh kutusu, yüzey/bölge inceltme, sınır tabakası katmanları —
  değerler mühendisten); `checkMesh` çıktısı veri olarak.
  **Mesh kurgusu (kullanıcı 2026-10-08):** CFD mesh'i FEA mesh'inden ayrıdır —
  parçanın değil akışkan hacminin sonlu hacim ağı (hex ağırlıklı, duvarda sınır
  tabakası, adlandırılmış yamalar). `MesherAdapter`'ın CFD uygulaması
  (`mesh/cfd_mesher.py`); AKIŞ sekmesinde FEA mesh panelinden ayrı bir CFD mesh
  paneli (tünel boyutu, taban hücre, inceltme, katmanlar, checkMesh tablosu, y+).
  Geometri adımı ortak. Parça/bölge başına ayrı STL yüzeyi → ayrı yama → parça
  başına kuvvet (roket: burun / gövde / kanatçık / taban).
  - 2.5a ✅ (2026-10-08) `snappyHexMesh` (varsayılan; akademi ve yarışmalarda standart).
    `app/mesh/cfd_mesher.py`: STEP → Gmsh yüzey üçgenlemesi → çok-katılı STL
    (yüzey Physical Group'u başına ayrı solid → ayrı yama; kalanı `body`; mm → m;
    açık kenar sayısı veri), tünel kutusu (gövde boyu L'nin katları: önde 3,
    arkada 6, yanlarda 3 — parametre; zemin isteğe bağlı), blockMeshDict,
    surfaceFeatureExtractDict, snappyHexMeshDict (yüzey / kenar / iz kutusu
    inceltmesi, sınır tabakası), ESI meshQualityDict; checkMesh ve snappy
    günlüğü okuyucuları (hücre tipleri, non-orthogonality, skewness, aspect ratio,
    yama yüzleri, seviye dağılımı, katman kapsaması). API: `POST /cfd/mesh`
    (arka plan), `GET /cfd/mesh/{id}`; `/cfd/solve` `mesh_id` ile polyMesh'i
    kullanır (yama adı denetimi). Case yazıcıya `slip` yaması (tünel yanları).
    Uçtan uca: 100 mm küre, taban 50 mm, yüzey seviyesi 3 → 13 615 hücre,
    checkMesh OK, 3 katman %100, mesh 7 s; k-ω SST 10 m/s (Re 6.7e4) 203
    iterasyon, Cd 0.406 (kaba ağ; doğrulama 2.6). Test `tests/test_cfd_mesh.py`.
  - 2.5b ✅ (2026-10-09) `cfMesh` (`cartesianMesh`; daha az ayar, sınır
    tabakasını kendisi ekler) — NLGEOM gibi seçilebilir ikinci mesh'leyici.
    **Düzeltme:** resmi ESI imajında cfMesh YOK (önce "hazır" denmişti, yanlıştı).
    Kullanıcı kararı 2026-10-09 ("ikisini de yap"): `backend/docker/openfoam/Dockerfile`
    resmi imajın üzerine ESI cfMesh modülünü (GPL, v2406 etiketi) derler →
    `simsurrogate-openfoam:2412-cfmesh` (derleme ~2 dk); snappy ve geri kalanı aynı.
    `cfd_mesher.py`: tünel kutusu + gövde tek STL (`domain.stl`), `meshDict`
    (snappy ayarlarıyla aynı anlam: gövde hücresi = taban/2^seviye_maks, iz kutusu,
    katman sayısı + büyüme oranı, `renameBoundary` ile yama türleri). `/cfd/mesh`
    `mesher: snappy | cfmesh` (otomatik seçim yok). Küre: cfMesh 17 094 hücre,
    checkMesh OK, max non-orthogonality 24.6° (snappy 13 615 hücre, 34.5°). Ogive roket (aynı tünel, taban 0.15 m): cfMesh 27 s'de 328 233 hücre (snappy 124 s / 142 346), checkMesh 1 kontrol başarısız (max non-orth 71°, skewness 4.1); 50 m/s k-ω SST salınımlı (Cd 0.78, son 100 ort. 0.70, std 0.12) — snappy ile karşılaştırma için ayar eşlemesi ve ağ yakınsaması 2.6'da (veri, yorum yok). Test `tests/test_cfd_cfmesh.py`.
  - (seçenek) Gmsh hacim tet ağı + `gmshToFoam` — yalnız gerekirse.
- 2.6 ✅ Dış akış doğrulaması: silindir (Re 20/40 — Cd literatür), ardından
  `pitzDaily` yeniden bağlanma uzunluğu (V-C2, V-C3). Sonuçlar `docs/CFD_VALIDATION.md`.
  - 2.6a ✅ (2026-10-09) V-C2 küre (silindir yerine 3B küre — mevcut tünel akışı):
    şablon `cfd_sphere`, Re 20/40/100 laminer, snappy seviye 2/3/4 + cfMesh; referans
    Schiller–Naumann ve Clift–Grace–Weber. En ince ağ CGW'ye +%1.4–1.9, seviye 3→4
    değişim ≤ %0.8; cfMesh snappy s3'ten %0.2–0.9 farklı. Betik
    `scripts/cfd_validation_sphere.py`, test `tests/test_cfd_sphere_validation.py`.
  - 2.6b ✅ (2026-10-09) V-C3 pitzDaily: k-ω SST, öğretici ağı → x_r/h 7.89 (deney
    7.0, %+12.7); residual ~1e-4'te plato; yeniden bağlanma daralma başlangıcına
    (206 mm) yakın. `app/postprocess/openfoam_fields.py` (yama değerleri, τ_x işaret
    değişimi), betik `scripts/cfd_validation_pitzdaily.py`, test `tests/test_openfoam_fields.py`.
  - 2.6c ✅ (2026-10-09) V-C4 Ahmed gövdesi: şablon `ahmed_body` (φ 0–40°, bacaksız),
    zeminli tünel, φ 25°: 217k hücre, k-ω SST 40 m/s → Cd 0.367 (deney 0.285, %+29;
    kaba ağ, residual hedefe inmedi). Betik `scripts/cfd_validation_ahmed.py`, test
    `tests/test_template_ahmed.py`. **2.6 kapandı**; V-C5 Basic Finner
    (sıkıştırılabilir) R4 ile.
- 2.7 ✅ (2026-10-09) Frontend: Analiz tipi "CFD · OpenFOAM" sekmesi; adımlar
  1 Geometri · 2 Mesh (blockMesh / snappy ayarları) · 3 Akışkan (ρ, ν) ·
  4 Sınır koşulları (giriş hızı, çıkış basıncı, duvar, simetri,
  türbülans modeli) · 5 Sonuçlar (residual grafiği, Cd/Cl, Δp). İşlevle
  birlikte sunulabilir kalitede; öneri/uyarı mekanizması yok.
  - 2.7a ✅ (2026-10-09) CFD mesh paneli (AKIŞ · 2 · Mesh, FEA panelinden ayrı):
    tünel (önde / arkada / yan × L, taban hücre, zemin + açıklık), mesh'leyici
    snappyHexMesh | cfMesh, yüzey / kenar / iz seviyeleri, katmanlar; "Mesh üret" →
    `/cfd/mesh` arka plan + yoklama; sonuç tablosu (yüzey, tünel, hücre tipleri,
    non-orthogonality, skewness, aspect ratio, checkMesh), katman kapsaması, yama
    listesi. `api/cfd.ts`, `CfdMeshPanel.tsx` (+ test). Tarayıcı: roket, taban 0.3 m,
    seviye 2–3 → 56 298 hücre, Mesh OK.
  - 2.7b ✅ (2026-10-09) Çözüm paneli (AKIŞ · 3 · Akış): yama rolleri (mesh yamalarından;
    giriş / çıkış / duvar / kaymalı / serbest akım / simetri / boş), hız vektörü, ν, ρ,
    laminer | k-ω SST, Re verisi, iterasyon / residual / gevşetme, kuvvet yamaları + A, l;
    Çalıştır → `/cfd/solve` + `/cfd/jobs` yoklama, canlı residual grafiği (log ölçek,
    `CfdResidualChart`), özet (iterasyon, Cd ± std, Cl, CdA, Fx). Tarayıcı: roket kaba ağ
    50 m/s → 202 iterasyon, Cd 0.247 (kaba ağ, yalnız arayüz denemesi).
  - 2.7c ✅ Sonuçlar (`CfdResults`): özet (Cd/Cl/Cm, CdA, toplam ve basınç/viskoz
    kuvvet, Δp), yama başına kuvvet tablosu, katsayı geçmişi (doğrusal grafik). Roket
    modu (roket yamaları varsa, `Genel akış | Roket rüzgâr tüneli`): hız, α, CG,
    sıcaklık → Mach verisi, Barrowman ön izleme (bileşen tablosu + kararlılık),
    `/cfd/rocket/solve`; sonuçta CA/CN, CD/CL, Cm, basınç merkezi, CNα, kararlılık
    payı ve Barrowman ile yan yana. Tarayıcı: kaba ağ α 4°, CG 900 → CNα 13.86
    (Barrowman 10.81), x_cp 1159.6 mm (1176.6), kararlılık 2.60 kal.
  - 2.7d ✅ Koşu geçmişi (`CfdRunsPanel`, `cfd_runs`): bu geometri / tümü, en çok 6
    koşuyu yan yana (Cd, Cl, CdA, Fx, Δp, roket CN / CNα / x_cp / kararlılık), dışla /
    geri al; çözüm bitince liste yenilenir.
  - 2.7e ✅ (2026-10-09) Koşu başına PDF rapor (`GET /cfd/runs/{id}/report.pdf`,
    `cfd_report.py`, reportlab: kurulum, yamalar, katsayılar ort.±std, yama kuvvetleri,
    roket / Barrowman, residual (log) + Cd grafikleri; Türkçe TTF) ve Belgeler'de
    "Akış" kitabı (`docs/cfdDoc.ts`: 8 bölüm + 3 şablon, görsel `public/docs/cfd/`).
- 2.8 ✅ Alan görselleştirme (2026-10-09; yeni bağımlılık yok, PyVista gerekmedi):
  case yazıcıda `CfdViz` → controlDict'e `surfaces` (raw: gövde yamaları p/U +
  `cuttingPlane` kesit) ve `streamLine` (düz metin eski VTK) fonksiyon nesneleri,
  `writeTime`'da yazılır. Tünel mesh'li koşularda (`/cfd/solve` mesh_id,
  `/cfd/rocket/solve`) varsayılan: gövde duvarları, gövde merkezinden y-kesiti,
  gövde önünde 5×5 tohum. `GET /cfd/jobs/{id}/fields` (`openfoam_viz.build_fields`):
  gövde Cp = (p − p∞)/(½ρ∞U∞²), kesit |U|, akım çizgileri |U|; `fields.json`
  önbelleği. Arayüz `CfdFieldViewer` (three.js; katman aç/kapa, min–max aralığı).
  Roket 56k hücre, 40 m/s, α 4°: 384 gövde, 2249 kesit noktası, 25 akım çizgisi.
  Testler `test_openfoam_viz.py`, `CfdFieldViewer.test.tsx`.
- 2.9 ✅ CFD DOE + vekil model (2026-10-09; crash 1.19 deseni, yeni bağımlılık /
  DB şeması yok): `POST /cfd/ml/doe` — roket şablonu, taranan değişkenler sayısal
  şablon parametreleri ve/veya mach / alpha_deg (LHS, tohumlu); her örnek şablondan
  geometri → tünel mesh'i → R3 koşusu (aynı çözücü), sıralı, örnek hatası taramayı
  durdurmaz; durum `uploads/cfd_doe/<id>/doe.json`. Korpus `app/ml/cfd/corpus.py`
  (cfd_runs roket koşuları, çözücü başına; girdiler flow.mach / alpha_deg / x_ref_m +
  geom.*; hedefler CD, CL, CA, CN, Cm, x_cp), eğitim / tahmin crash RF + K-fold
  koduyla (`/cfd/ml/corpus|train|models|predict`, model `uploads/models/cfd/rocket/`).
  Arayüz: ML Stüdyo → "Akış" (`CfdMlPanel`: DOE, model + CV tablosu, tahmin + aralık
  dışı). Deneme: 10 örnek (kanatçık açıklığı 70–130 mm × M 0.1–0.3 × α 0–6°),
  53–57k hücre, simpleFoam, 10/10 çözüldü, 630 s. 5-kat CV R²: CN 0.63, CL 0.62,
  CD 0.49, CA 0.15, Cm −0.20, x_cp −0.42 (10 örnek; küçük α'da x_cp = −Cm/CN oranı
  oynak — örn. α 1.46°'de 0.56 m). Veri; örnek sayısı mühendisin kararı.
  Testler `test_cfd_ml.py`, `CfdMlPanel.test.tsx`.

**Kapsam ve hedef (kullanıcı, 2026-10-08):** Akışta hem iç hem dış akış ve
aerodinamik olacak. Ek hedef: akademik yarışmalar — savunma sanayii roket
yarışmaları. Bunun için hazır şablon mantığımızın rokete özel ayrı bir modülü
(aşağıda **Roket modülü R1–R6**): parametrik roket şablonu ya da gerçek roketin
STEP modeli ile dış akış çözümü. Referans ürünler (yalnız fikir; kod/veri
alınmaz): AirShaper (bulut "sanal rüzgâr tüneli": Cd/Cl, parça başına kuvvet,
Cp haritası, akım çizgileri, tasarım karşılaştırma) ve OpenRocket (parametrik
parça ağacı, Barrowman, kararlılık; GPL — kodu kullanılmaz, formüller
literatürden). AirShaper'ın "AI tasarım önerisi / morphing" özellikleri
alınmaz (kural 4: araç öneri vermez); karşılığı parametrik DOE + vekil model.

**Mevcut adımlara eklenenler (2026-10-08):**
- 2.4'e: CdA (sürükleme alanı), yama/parça başına kuvvet ve moment kırılımı,
  kuvvet katsayısının iterasyon geçmişi (son N iterasyon ortalaması ve salınımı
  — yalnız veri), basınç merkezi için moment (CofR mühendisten).
- 2.5'e: "sanal rüzgâr tüneli" — akış alanı geometrinin sınır kutusundan
  (önde/arkada/yanda kaç boy: parametre), zemin var/yok, hız + hücum (α) /
  sapma (β) açısı; STL kapalılık (watertight) kontrolü veri olarak.
- 2.6'ya: Ahmed gövdesi (otomotiv benchmark'ı) ve roket benchmark'ı
  "Basic Finner" (deneysel Cd / CNα / CP verisi Mach'a göre literatürde).
- 2.8'e: akım çizgileri (ESI `streamLine`), yüzey Cp haritası.
- Karşılaştırma / PDF: durability ve crash'teki geçmiş–karşılaştır–PDF deseni
  `cfd_runs` için (2.4 kaydı ile).

**Roket modülü (R1–R6; her biri ayrı onay, Faz 2 içinde):**
- R1 ✅ (2026-10-09) Parametrik roket şablonu (Gmsh OCC): burun konisi (konik / ogive /
  elips / von Kármán; boy, çap), gövde tüpü (boy, çap), kanatçıklar (adet,
  kök/uç veter, açıklık, ok açısı, kalınlık), isteğe bağlı boat-tail;
  bölgeler: burun, gövde, kanatçık, taban. Gerçek roket STEP'i de aynı akışa
  girer (bölgeler elle).
  **Sonuç:** `app/templates/rocket.py` (`rocket`, etiket `cfd`): burun konik /
  ogive / elips / von Kármán (formüller docstring'de), gövde, 2–8 kanatçık (kök /
  uç veteri, açıklık, ok, kalınlık, firar konumu), boat-tail; eksen +x, burun ucu
  x = 0. Bölgeler `burun`, `govde`, `kanatcik`, `taban` (boat-tail yüzeyi `body`
  yamasına düşer). Kurulum: profil eğrileri döndürülüp dikişli kabuktan hacim
  (yüzey döndürme iç dikiş yüzü bırakıyordu), kanatçıklar birleştirilir. STL
  dışa aktarımı: ikiz düğümler 10 nm ızgarada birleştirilir; dikişsiz okumada
  açık kenar kalırsa dikişli okuma (yüz merkezi + alanla bölge eşleme) — 4 burun ×
  boat-tail'li/siz hepsi kapalı. Arayüz: AKIŞ sekmesi şablon listesi yalnız `cfd`
  etiketlileri gösterir (durability görmez), roket şeması. Uçtan uca: ogive roket,
  tünel 2/4/1 × L, taban 0.15 m, seviye 3–5, 2 katman → 142 346 hücre, checkMesh
  OK (mesh 124 s); k-ω SST 50 m/s: Cd 0.53 (power-off, kaba ağ), yama başına Fx:
  taban 2.32 N · kanatçık 2.16 · gövde 1.55 · burun 0.36 (toplam 6.40). Test
  `tests/test_template_rocket.py` (+ Docker'da kaba tünel).
- R2 ✅ (2026-10-09) Analitik referans: Barrowman (sesaltı) — basınç merkezi (CP) ve CNα;
  durability'deki "analitik referans tablosu" deseni, CFD sonucunun yanında
  veri olarak.
  **Sonuç:** `app/postprocess/barrowman.py`: burun (ince gövde: CNα = 2, X = Ln −
  V/A — her profil sayısal integralle; koni 0.667·Ln, ogive 0.46, elips 0.333, von
  Kármán 0.5), gövde (0), boat-tail (konik geçiş), kanatçık (4N(s/d)², gövde
  etkileşimi K = 1 + R/(s+R), orta veter çizgisi), toplam CNα ve X_cp, CG
  verilirse kararlılık payı (kalibre). N > 4 kanatçıkta not düşülür. API
  `POST /cfd/rocket/barrowman` (params ya da roket şablonundan geometry_id).
  Varsayılan roket: CNα 10.81 /rad, X_cp 1177 mm (ogive). Test `tests/test_barrowman.py`.
  Arayüzde gösterim 2.7'de.
- R3 ✅ (2026-10-09) Roket rüzgâr tüneli kurulumu: Mach / hız, α, ağırlık merkezi (CG,
  mühendisten) → sonuçta CP, CN, CA, Cd, Cm ve kararlılık payı
  (CP − CG)/D kalibre cinsinden — yalnız veri.
  **Sonuç:** case yazıcıya `farfield` yaması (`freestreamVelocity` /
  `freestreamPressure`, k/ω `inletOutlet`) — hücum açısında tünel sınırları serbest
  akım. `POST /cfd/rocket/solve` (mesh_id roket şablonundan; hız, α, CG, ρ, ν, T,
  türbülans, iterasyon, gevşetme): U∞ = V(cos α, 0, sin α), gövde yamaları kuvvet,
  moment CG'ye göre. Koşu sonunda `rocket_aero`: CA, CN (gövde), CD, CL (rüzgâr), Cm,
  x_cp = x_ref − M_y/F_z, CNα = CN/α, kararlılık payı, Barrowman ile fark; Mach veri
  (a = √γRT). Kayıt `cfd_runs.reference.kind = rocket_r3`. Gerçek koşu (ogive, 142k
  hücre, 50 m/s, Mach 0.147, CG 900 mm): α 0° → CA 0.531, CN 0.002; α 4° gevşetme
  0.9/0.9 ile ıraksadı (k, ω negatif, çıkış 136), 0.5/0.3 ile 113 iterasyon: CN 1.10,
  CNα 15.8/rad (Barrowman 10.8, %+46), x_cp 1.221 m (Barrowman 1.177, +0.44 kal.),
  kararlılık 3.21 kal. Kaba ağ + varsayılan p residual 1e-2 — doğrulama değil (2.6).
  Test `tests/test_rocket_r3.py`.
- R4 ✅ Çözücü seçimi (**karar verildi 2026-10-08:** üçü de bulunur, NLGEOM gibi
  kullanıcı seçer; otomatik seçim yok — Mach sayısı yalnız veri olarak
  gösterilir). Case yazıcıda `solver` alanı: `simpleFoam` (sıkıştırılamaz,
  Mach ≲ 0.3, iç akış) | `rhoSimpleFoam` | `rhoCentralFoam`; üst katmanlar
  değişmez (adaptör deseni). Her çözücünün doğrulandığı Mach aralığı belgede veri.
  Not: hesaplanan Cd motor kapalı (power-off); y+ veri olarak gösterilir.
  - R4a ✅ `rhoSimpleFoam` (daimi, sıkıştırılabilir, `transonic` seçeneği;
    Mach ~0.3–0.8): `0/T`, `0/alphat`, mutlak `0/p` (Pa),
    `thermophysicalProperties` (hePsiThermo, mükemmel gaz, μ = ρ·ν), NACA0012
    öğretici ayarları (`openfoam_compressible.py`). Roket 56k hücre, 170 m/s
    (M 0.50), α 4°: 182 iterasyon yakınsadı, 102 s; CNα 16.4 /rad (Barrowman
    10.8, +%51 — kaba ağ, doğrulama değil), x_cp 1183.8 mm (1176.6).
  - R4b ✅ `rhoCentralFoam` (yoğunluk tabanlı, Kurganov akısı, yerel zaman
    adımı `localEuler`, `maxCo` parametre) + paralel koşu (`n_procs` →
    `decomposeParDict` scotch, `decomposePar -force`, `mpirun -np N … -parallel`,
    `reconstructPar -latestTime`; docker `--shm-size 1g`). Roket 510 m/s (M 1.50),
    α 4°, 1500 iterasyon, 362 s: CD 0.703, CNα 17.9 /rad, x_cp 1042.7 mm.
    Basic Finner doğrulaması ayrı (ağ yakınsaması ile). Arayüz: "Çözücü ve
    çözüm ayarları" grubunda üç düğme, Mach yalnız veri. Test
    `test_openfoam_compressible.py`.
- R5 ✅ Mach × α taraması (2026-10-09): `POST /cfd/rocket/sweep` (Mach listesi ×
  α listesi, her nokta bir R3 koşusu, sıralı, aynı mesh + çözücü — çözücü Mach'a
  göre değişmez), `GET /cfd/rocket/sweep/{id}`, `…/csv?kind=table|points`.
  Tablo (`rocket_table.aero_table`): Mach başına CD (en küçük |α|), CNα (CN–α
  en küçük kareler eğimi), x_cp ortalaması. Arayüz `CfdSweepPanel` (roket modu).
  Deneme: 56k hücre, simpleFoam, M 0.1 / 0.2 × α 0 / 2 / 4, 149 s: CNα 10.74 /rad
  (Barrowman 10.81), CD₀ 0.248 / 0.242, x_cp ort. 1194.7 mm. Not (veri): α 0'da
  CN 0.218 — kaba ağın simetri dışı olması; eğim bundan etkilenmez.
  Test `test_rocket_sweep.py`, `CfdSweepPanel.test.tsx`.
- R6 ✅ OpenRocket `.ork` içe aktarma (2026-10-09; yeni bağımlılık yok):
  `POST /cfd/rocket/ork` (zip ya da düz XML, ≤ 5 MB, DOCTYPE/ENTITY reddedilir) →
  R1 parametreleri (mm) + eşlenemeyenler notu; geometri üretmez. Eşleme: ilk
  aşama; nosecone (ogive / conical → konik / ellipsoid → elips / haack 0 →
  von_karman), bodytube'lar toplam boy + ilk çap, ilk trapezoidfinset (N, Cr, Ct,
  s, Xs, t; `axialoffset`/`position` bottom → Xf), son tüpten sonra daralan
  transition → boat-tail. Arayüz: roket şablonunda "OpenRocket .ork içe aktar"
  formu doldurur. 2026-10-10: OpenRocket deposundaki 6 örnek (.ork) ile denendi → 6/6 şablon
  doğrulamasından geçti ve geometri üretildi; düzeltmeler: tüm kademeler fırlatma
  konfigürasyonunda birleşir, kanatçık en arkadaki tüpten, çap kanatçık tüpünden,
  aynı geometrideki tek kanatçıklı setler toplanır (tüp kanatçık: not, varsayılan).
  Test `test_rocket_ork.py`, `TemplatePanel.test.tsx`.

**Sonraya (ayrı adım/faz):** zamana bağlı çözüm (`pimpleFoam` — girdap
kopması, kuvvet salınımı), dönen tekerlek / hareketli zemin (MRF), kapalı
olmayan geometri desteği.

## Faz 3 — Kompozit modelleme (CalculiX üzerine katman; Dalga 1)

**Durum: BAŞLADI (kullanıcı onayı 2026-10-12); `main`'e birleşti (2026-10-14)** —
`feature/phase3-composite` dalında başladı, `main`'e merge edildi (`a0809f0`);
mevcut CFD/crash işine dokunulmaz. **Yeni solver yok.** Code_Aster yok.
Dalga 1 solver'ı CalculiX (`*SHELL SECTION, COMPOSITE`). `/solve` refaktör edilmez;
koşu 3.9'da `POST /composite/solve` → `CalculiXAdapter`. Arayüz ACP Pre benzeri
hazırlık bölümüdür (ANALİZ TİPİ → KOMPOZIT), beşinci çözücü değil.

**Kararlar (2026-10-12):** Dalga 1 = ortotrop ply, rozet, stackup, CLT, COMPOSITE
kesit, Tsai-Wu/Hashin, katman sonuçları. Draping / sandwich / katmanlı solid /
OpenRadioss crash kompozit = Dalga 2+ (ayrı onay).

**Mikro-adımlar (her biri ayrı onay; bir adım bitince dur):**

- 3.0 ✅ (2026-10-12) İskelet: KOMPOZIT sekmesi + `CompositePlanPanel` (plan/kararlar
  veri); ROADMAP / ARCHITECTURE / CLAUDE.md. Test `CompositePlanPanel.test.tsx`.
  Solver bağlı değil. Doğrulama: `localhost:5173` KOMPOZIT sekmesi.
- 3.1 ✅ (2026-10-12) Ply malzemesi (backend): `composite_materials` + Alembic
  (`c4d5e6f7a8b9`) + UD seed (tipik T300/epoxy, E-glass/epoxy — mill test değil)
  + `GET/POST /composite/materials`. Test `test_composite_materials.py`.
  Metal `/materials` ve `/solve` dokunulmaz.
- 3.2 ✅ (2026-10-12) Ply kütüphanesi (UI): `CompositeMaterialsPanel` — liste +
  kullanıcı tanımlı ortotrop form (9 sabit GPa + Xt/Xc/Yt/Yc/S12 MPa → Pa).
  Test `CompositeMaterialsPanel.test.tsx`.
- 3.3 ✅ (2026-10-12) CLT: `backend/app/composite/layup.py` — katman listesi →
  ABD (A N/mm, B N, D N·mm; E Pa, t mm). [0/90/0] B=0, A11>A22; [±45]s
  A11=A22, A16=0. Test `test_composite_layup.py`.
- 3.4 ✅ (2026-10-12) CLT önizleme: `POST /composite/clt` (E Pa, t mm, θ°; DB yok)
  + `CompositeCltPanel` ABD (A N/mm, B N, D N·mm; yorum yok).
  Test `test_composite_clt.py`, `CompositeCltPanel.test.tsx`.
- 3.5 ✅ (2026-10-12) Layup CRUD: `composite_layups` (geometry_id + part_id +
  `plies` JSON, alt → üst). Alembic `d5e6f7a8b9c0`. `GET/PUT /composite/layups`.
  Test `test_composite_layups.py`. UI 3.6.
- 3.6 ✅ (2026-10-12) Layup tablosu (UI): `CompositeLayupPanel` — parça, açı /
  kalınlık / malzeme / sıra (↑↓), `PUT /composite/layups`, ABD canlı
  (`POST /composite/clt`). Test `CompositeLayupPanel.test.tsx`.
- 3.7 ✅ (2026-10-12) Rozet + OSS: `composite_orientations` (paralel, dir0
  varsayılan global X, OSS parça | seçili yüzey). Alembic `e6f7a8b9c0d1`.
  `GET/PUT /composite/orientations`. `CompositeRosettePanel` + viewport 0° oku.
  Test `test_composite_orientations.py`, `CompositeRosettePanel.test.tsx`.
- 3.8 ✅ (2026-10-12) `section_writer`: `*ELASTIC, TYPE=ENGINEERING CONSTANTS`
  + `*ORIENTATION` + `*SHELL SECTION, COMPOSITE`. `calculix.py` yalnız
  `params["composite_layup"]` doluysa bu yolu kullanır; `/solve` aynı.
  Test `test_composite_section_writer.py`.
- 3.9 ✅ (2026-10-12) `POST /composite/solve`: mesh + layup + BC →
  CalculiXAdapter (`composite_layup`); `composite_runs` (Alembic `f7a8b9c0d1e2`).
  `GET /composite/runs`. `/solve` değişmez. Test `test_composite_solve.py`.
- 3.10 V-P1: klasik laminat kabuk plaka; CLT vs ccx (ccx yoksa atlanır).
  `docs/COMPOSITE_VALIDATION.md`.
- 3.11 Katman gerilmesi: `.frd` katman S → ply tensörü.
- 3.12 Hasar: Tsai-Wu + Hashin IRF (`ResultSet.scalars` + ply alanı). Puck yok.
- 3.13 Sonuç UI: katman seçici, gerilme / IRF kontur, min IRF.
- 3.14 Belgeler: Kompozit kitabı.

**Sonraya (Dalga 2+, bu dalgada yok):** draping, sandwich/core, ply drop-off,
katmanlı solid, üretim ply kesimi, Puck/LaRC, OpenRadioss `/PROP/STACK` + LAW25.

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
