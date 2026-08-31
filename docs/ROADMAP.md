# Yol haritası

Fazlar sırayla ilerler. Bir fazdan diğerine geçmeden önce agent kullanıcıdan onay ister.
Şu anki faz `CLAUDE.md` içinde "Mevcut faz" başlığında belirtilir — o dosya güncel kaynak.

## Faz 0 — Durability pilotu (CalculiX + Gmsh) — ŞU AN BURADAYIZ

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
      mesh bar **Kalite** butonu (Free edge / Equivalence / Rigid body yer tutucu)
- [ ] Mesh kalite hesaplama: skewness + warpage (custom) → aynı endpoint'e eklenir,
      bilinen kötü bir test mesh'inde (bilerek çarpık üretilmiş) yüksek değer çıktığı
      doğrulanır
- [ ] Frontend'de kalite görselleştirme: kötü elemanları renkli vurgulama + histogram →
      viewer'da düşük kaliteli elemanlar kırmızı görünür, yanında bir histogram grafiği.
      Yazılım burada bir yorum/öneri üretmez — sayıyı ve görseli gösterir, karar mühendisin
- [ ] Free edge kontrolü → shell mesh'te bilerek bir boşluk bırakılmış test parçasında,
      o boşluğun kenarları viewer'da vurgulanır
- [ ] Node-to-node equivalence (tespit + birleştirme) → iki ayrı meshlenmiş parça birleşim
      yüzeyinde çakışan düğüm sayısı önce raporlanır, onaylanınca birleştirilip düğüm
      sayısındaki azalma terminalde görülür
- [ ] Rigid body ataması (solver-özel, mesh'ten sonra): bir yüzey/delik + referans node
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
      Displacement / Sliding / Bearing / Gravity) + parametre alanları + BC listesi +
      shell kalınlık + .inp üret/çöz
- [x] Parametrelerin forma bağlanması (Fx/Fy/Fz, |P|, U, normal, bearing ekseni, g)
- [ ] Nokta/kenar/yüzey → node listesi ayrı rapor endpoint'i (şimdilik solve içinde
      NSET üretiliyor)

### 4. Sonuçlar (deformation, von Mises, safety factor, modal)
- [ ] Deformation okuma (`.frd`'den `U`) → terminalde maksimum deplasman değeri görülür
- [ ] Von Mises stress hesaplama (gerilme tensöründen) → terminalde maksimum von Mises
      değeri görülür, viewer'da renk skalası ile gösterilir
- [ ] Safety factor hesaplama (malzeme akma değeri girişiyle) → aynı akışa bir sayı daha
      eklenir, kritik (SF<1) bölgeler viewer'da vurgulanır
- [ ] Modal analiz (`*FREQUENCY` step'i, ayrı bir analiz tipi seçeneği) → kullanıcı
      "modal" seçtiğinde farklı bir step üretilir, sonuçta doğal frekanslar listesi +
      seçilen moda ait şekil viewer'da animasyonlu/statik gösterilir

### 5. Job kuyruğu + durum takibi
- [ ] Senkron çağrıyı asenkron job'a çevirme (basit runner, henüz Celery değil) →
      `POST /runs` hemen `job_id` döner, `GET /runs/{id}` durumu gösterir
- [ ] Frontend'de "çalışıyor... / bitti" durum göstergesi (polling) → sayfa job bitene
      kadar durumu günceller

### 6. Post-process (fatigue)
- [ ] pyLife ile yorulma ömrü hesaplama (Adım 4'te üretilen gerilme verisinden) → akış
      bir "cycles" sayısı üretir, terminalde görülür
- [ ] Frontend'de sonuç grafiği (basit bir bar/line chart) → tarayıcıda sayısal sonuç ve
      grafik görülür

### 7. Veritabanına kayıt + geçmiş
- [ ] Her run'ın (girdi + sonuç) veritabanına yazılması → `psql` ile satır görülür
- [ ] Frontend'de geçmiş analizler listesi → tarayıcıda önceki run'lar listelenir, birine
      tıklanınca sonucu tekrar gösterir

Çıkış kriteri: yukarıdaki tüm adımlar tek tek onaylanmış olacak ve bir kullanıcı tamamen
web üzerinden, lokal kurulum yapmadan (CAD/mesh/solver yazılımı olmadan) bir durability
analizi çalıştırıp sonucu görebiliyor olacak.

**Not:** Faz 1/2/3'ün planları da aynı mikro-adım mantığıyla, bu fazın somut kod yapısı
netleştikten sonra detaylandırılacak — şimdiden hepsini yazmıyoruz çünkü Faz 0'da
öğrenilecekler (örn. hangi adımın daha da bölünmesi gerektiği) sonraki fazların adım
boyutunu da etkileyecek.

## Faz 1 — Crash analizi (OpenRadioss + Gmsh)

Ön koşul: Faz 0 tamamlanmış olmalı ve kullanıcı onayı alınmalı.

- [ ] `OpenRadiossAdapter` implementasyonu (Radioss block format `.rad`/`.inc` üretimi)
- [ ] Gmsh mesh export'unun OpenRadioss formatına uyarlanması (Faz 0'da kullanılan aynı
      mesh modülü, farklı export fonksiyonu)
- [ ] Barrier geometrisinin/parametrelerinin (hız, açı, rigid wall pozisyonu) girdi
      dosyasına yazılması
- [ ] OpenRadioss'un sunucuya kurulumu (derleme ya da hazır binary — lisans sunucusu
      GEREKMEZ, bkz. `LICENSING.md`)
- [ ] Post-process: OpenRadioss çıktı dosyalarından (time-history, animasyon) enerji,
      reaksiyon kuvveti, ivme, HIC gibi metriklerin çıkarılması
- [ ] Job süresi uzun olduğu için websocket tabanlı ilerleme takibi
- [ ] Aynı frontend/backend/db şeması Faz 0'dan yeniden kullanılır — sadece solver
      adaptörü, mesh export fonksiyonu ve post-process modülü eklenir

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

## Faz 4 — Surrogate model (tüm analiz tipleri için)

Ön koşul: Faz 1/2/3'ten (hangileri tamamlandıysa) yeterli sayıda (en az birkaç yüz) analiz
sonucu veritabanında birikmiş olmalı. Analiz tipi başına ayrı bir surrogate model eğitilir
(durability, crash, kompozit, CFD — her birinin girdi/çıktı uzayı farklı).

- [ ] DOE (Latin Hypercube Sampling) ile parametre uzayının toplu taranması
- [ ] Özellik çıkarımı (skaler metrikler + gerekirse PCA ile eğri indirgeme)
- [ ] Baseline model: scikit-learn Random Forest / Gradient Boosting
- [ ] Değerlendirme: k-fold cross-validation, hata metrikleri (MAE/RMSE), güven aralığı
- [ ] Model versiyonlama (MLflow ya da basit dosya tabanlı versiyonlama)
- [ ] Backend'e "hızlı tahmin" endpoint'i eklenmesi
- [ ] Frontend'de "hızlı tahmin (saniyeler)" vs "tam çözüm (saatler)" seçeneği
- [ ] Periyodik yeniden eğitim pipeline'ı (yeni veri geldikçe)

## Faz sırasını değiştirme

Kullanıcı isterse fazlar atlanabilir ya da paralel ilerletilebilir, ama agent bunu kendi
başına yapmaz — her faz geçişinde veya sırası değiştiğinde bu dosyayı güncelleyip
kullanıcıya bildirir.
