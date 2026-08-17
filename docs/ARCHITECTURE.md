# Mimari

## Akış

```
Frontend (React)
  -> Geometri yükleme (STEP/IGES dosyası)
       -> Backend: tessellation (önizleme meshi, glTF/STL) -> Frontend 3B önizleme (three.js)
  -> Backend API (FastAPI)
       -> Mesh Adaptör (Gmsh: geometri -> FEA mesh)
       -> Pre-process (mesh + parametreleri girdi dosyasına yaz)
       -> Job Queue (Celery/Redis ya da basit runner)
            -> Solver Adaptör (CalculiX | OpenRadioss)
                 -> Post-process (sonuç dosyasından metrik/eğri çıkar)
       -> Veritabanı (PostgreSQL: girdi, meta veri, sonuç, job durumu)
  <- Frontend sonucu grafik olarak gösterir
```

## Geometri ve mesh

Kullanıcı bir STEP (.stp/.step) ya da IGES (.igs/.iges) dosyası yükler. İki ayrı ihtiyaç
var ve bunlar birbirinden bağımsız çalışır:

1. **Web önizleme (hızlı, düşük çözünürlük):** Yüklenen geometri, gerçek FEA mesh'i
   beklemeden hemen üç boyutlu olarak gösterilmeli. Gmsh'in kendi OCC-tabanlı
   tessellation çıktısı (yüzey üçgenleme) alınıp glTF ya da STL'e çevrilir, frontend'de
   three.js ile render edilir. Kullanıcının bilgisayarında CAD yazılımı olmasına gerek
   yoktur.
2. **FEA mesh (analiz için, tam çözünürlük):** Kullanıcı parametreleri (eleman boyutu,
   kalite ayarları vb.) girdikten sonra Gmsh gerçek çözüm mesh'ini üretir (tet/tri —
   CalculiX; shell/solid — OpenRadioss'un beklediği formatta). Bu adım job kuyruğunda
   solver'dan önce çalışır.

`MesherAdapter` arayüzü (`backend/app/mesh/base.py`):

```python
class MesherAdapter(ABC):
    def import_geometry(self, cad_file: Path) -> GeometryHandle: ...
    def preview_tessellation(self, geom: GeometryHandle) -> Path:
        """Hızlı, düşük çözünürlüklü glTF/STL - web önizleme için."""
    def generate_mesh(self, geom: GeometryHandle, params: MeshParams) -> MeshResult: ...
```

Mesh aracı seçimi ve alternatifler için ayrı bir mesaj olarak gönderilen karşılaştırmaya
bak — özet: birincil araç **Gmsh** (STEP/IGES import + mesh üretimi + tessellation aynı
araçta, Python API, hem CalculiX hem OpenRadioss ile kanıtlanmış uyum).

## Geometri işleme operasyonları

Geometri import edildikten sonra, mesh üretiminden ÖNCE kullanıcının yapabileceği bir dizi
hazırlık operasyonu var. Bunların Gmsh'te ne kadar "hazır" olduğu operasyona göre çok
değişiyor — bunu şeffaf tutuyoruz, her biri için gerçek kapsam aşağıda:

| Operasyon | Gmsh'te durumu | Yaklaşım |
|---|---|---|
| Dış yüzey (skin) çıkarma | **Native** | Bir katının (volume) sınır yüzeyleri zaten `getBoundary(volume, dim=2)` ile geliyor — ayrı bir algoritma gerekmiyor |
| Yüzey seçme/kopyalama | **Native** | `gmsh.model.occ.copy([(2, face_tag)])` — kullanıcı frontend'de bir yüzeye tıklar, tıklanan üçgenden Gmsh face tag'ine geri eşleme yapılır |
| Seçilen yüzeye BC/mesh ataması | **Native** | Gmsh'in "Physical Group" mekanizması tam bunun için var — bir yüzey grubuna isim verilir (örn. `"inlet"`, `"fixed_support"`), solver adaptörü bu isimleri BC/yük tanımlarken kullanır |
| Geometry healing | **Native** | `gmsh.model.occ.healShapes()` — küçük boşluk/tolerans hatalarını düzeltir, yüzeyleri diker (`sewFaces`), dejenere/çok küçük kenar-yüzeyleri onarır |
| Defeature (küçük özellik bastırma) | **Hazır değil** | Gmsh otomatik "bu küçük deliği/fillet'i kaldır" demiyor. Basit kapsamla kendimiz yazacağız: kullanıcı bir boyut eşiği verir (örn. "5mm altındaki delikleri yok say"), küçük silindirik/dairesel yüzeyleri bulup boolean ile kapatan bir yardımcı modül |
| Midsurface çıkarma | **Hazır değil** (hiçbir açık kaynak araçta yok — Salome'da bile manuel) | Otomatik tespit YOK, kullanıcı odaklı: kullanıcı 2 yüzey seçer + butona basar, aralarında orta yüzey hesaplanır — detay aşağıda |

### Midsurface — kullanıcı odaklı, manuel seçim (otomatik tespit YOK)

Otomatik "bu parçanın kalınlığı sabit mi, hangi yüzeyler eşleşiyor" tespiti kapsam dışı —
kullanıcı zaten bunu istemiyor. Akış tamamen manuel:

1. Kullanıcı viewer'da bir yüzeye tıklar (Adım 1b'deki picking mekanizması), sonra
   Ctrl/Shift ile ikinci bir yüzeyi daha seçer (iki yüzey de picking mekanizması zaten
   yapılmış olacağı için ek altyapı gerekmiyor).
2. "Midsurface çıkar" butonuna basar.
3. Backend, pythonocc-core ile bu iki seçili yüzey arasında orta yüzeyi hesaplar: her
   yüzey üzerinde bir nokta ızgarası örneklenir, karşılıklı en yakın nokta çiftleri
   arasındaki orta noktalardan yeni bir yüzey (B-spline/mesh) kurulur.
4. Sonuç, orijinal katının yanında/üstünde ayrı bir "shell" geometrisi olarak viewer'da
   gösterilir — kullanıcı isterse mesh'i bunun üzerinden üretir (kabuk/shell eleman tipi).
5. Yüzeyler paralel değilse ya da eşleşme geometrik olarak anlamsızsa (örn. seçilen iki
   yüzey birbirine hiç bakmıyorsa), backend hesaplamayı reddedip anlaşılır bir hata mesajı
   döner — sessizce yanlış bir yüzey üretmez.

Bu, "otomatik defeature/midsurface" değil, **kullanıcının CAD bilgisiyle yönlendirdiği bir
araç** — tıpkı ANSA/HyperMesh'teki "select 2 faces → extract midsurface" butonunun aynısı,
sadece otomatik yüzey-çifti bulma adımı yok.

## Mesh üretimi ve kalite

### Eleman tipi seçimi

`MeshParams` içinde kullanıcı şunları seçebilir:
- **Boyut:** 3D solid (tet/hex/karma) ya da 2D shell/kabuk (tri/quad/karma)
- **Eleman türü:** quad, hexa, ya da mixed (karma — Gmsh'in kendi algoritması hangi
  bölgede hangi eleman tipinin uygun olduğuna göre karar verir)
- **Mesh boyutu (size):** global bir değer (`Mesh.MeshSizeMax`/`MeshSizeMin`) + istenirse
  yüzey/kenar bazlı yerel override (Adım 1b'deki yüzey seçim mekanizması burada da
  kullanılır — "bu yüzeyde daha ince mesh" gibi)

**Dürüst bir not:** Gmsh'in hex mesh üretimi (`Recombine3D` + ilgili algoritmalar) genel,
karmaşık katılarda ANSA/HyperMesh kalitesinde değil — extrusion/sweep'e uygun (prizmatik,
basit) geometrilerde iyi sonuç verir, serbest-form karmaşık parçalarda tet ya da karma mesh
daha güvenilir olabilir.

**Araç mühendise karar vermez, veri gösterir.** Kullanıcı zaten simülasyon mantığını bilen
bir mühendis — hangi durumda hex/tet/quad kullanacağını, kalite eşiklerinin ne olması
gerektiğini kendisi bilir. Bu yüzden hex kalitesi düşük çıksa bile yazılım "tet dener
misin?" gibi öneri/uyarı üretmez — sadece Adım 2'deki kalite modülünün ürettiği sayısal
veriyi ve görselleştirmeyi sunar, yorumu mühendise bırakır.

### Mesh kalite kriterleri

Gmsh'in `getElementQualities()` API'si bazı metrikleri native veriyor, bazılarını (sektörde
yaygın isimlerle: skewness, warpage) kendimiz hesaplıyoruz:

| Kriter | Kaynak |
|---|---|
| Jacobian (oranı) | Native — `minDetJac`/`maxDetJac` |
| Min/max kenar uzunluğu | Native — `minEdge`/`maxEdge` |
| Aspect ratio (kenar oranına dayalı) | Native'e yakın — `minEdge`/`maxEdge` oranından türetilir, ya da `gamma` (yazıt yarıçapı oranı) |
| Skewness (eşaçısal tanım) | **Custom** — üçgen için 60°, quad için 90° referans açıdan sapma, düğüm koordinatlarından hesaplanır |
| Warpage | **Custom** — quad/hex yüzünün düğümlerinin en iyi uyan düzlemden sapması |

`backend/app/mesh/quality.py`: her eleman için yukarıdaki metrikleri hesaplayıp
kullanıcı tanımlı eşik değerleriyle (örn. "aspect ratio > 5 olan elemanları işaretle")
karşılaştıran, sonucu hem sayısal özet (histogram) hem de viewer'da renkli
vurgulama (kötü elemanlar kırmızı) olarak sunan bir modül.

### Free edge kontrolü

Shell/kabuk mesh'lerde, her kenarın kaç elemana ait olduğu sayılır — 1 elemana ait olan
kenarlar "serbest kenar" (free edge). Kapalı olması beklenen bir yüzeyde beklenmeyen
serbest kenarlar varsa bu genelde bir mesh/geometri hatasına (boşluk, çakışmayan mesh)
işaret eder. `backend/app/mesh/free_edge_check.py`: kenar→eleman komşuluk sayacı,
sonucu viewer'da vurgulanacak kenar listesi olarak döner. Gmsh'te hazır değil, basit bir
topoloji taraması — karmaşık değil.

### 1D beam ve rigid body

- **1D beam mesh:** Kullanıcı bir kenar/eğri seçer, Gmsh o eğriyi çizgi (line) elemanlarıyla
  mesh'ler — bu zaten 2D/3D mesh üretiminin bir yan ürünü olarak native geliyor, ayrı bir
  şey yapmaya gerek yok.
- **Rigid body ataması:** Bu bir **mesh özelliği değil, solver girdisi tanımı**. Kullanıcı
  bir node seti (genelde bir yüzey/delik çevresi) + bir referans node seçer,
  `backend/app/preprocess/rigid_body.py` bunu solver'a göre doğru karta çevirir:
  CalculiX'te `*RIGID BODY`, OpenRadioss'ta `/RBODY`. Solver-adaptöre özgü olduğu için
  `SolverAdapter`'ın `build_input` adımına eklenir, `MesherAdapter`'a değil.

### Node-to-node equivalence

Ayrı ayrı meshlenmiş parçaların birleşim yüzeylerinde çakışan (aynı konumda, farklı ID'li)
düğümleri birleştirme — Gmsh'te native: `gmsh.model.mesh.getDuplicateNodes()` ile önce
tespit edilir (kullanıcıya "şu kadar çakışan düğüm bulundu" gösterilir), onaylanırsa
`removeDuplicateNodes()` ile birleştirilir. Tolerans kullanıcı tarafından girilebilir.

Kullanıcı three.js viewer'da bir üçgene tıkladığında (raycasting ile), o üçgenin ait
olduğu Gmsh yüzey (face) tag'i bilinmeli. Bu yüzden tessellation çıktısına, üçgen bazında
"hangi Gmsh face'e ait" bilgisi de eklenir (`triangle_to_face` dizisi) — Adım 1'de
ürettiğimiz `import_and_tessellate()` fonksiyonuna eklenecek küçük bir genişleme.

Faz 2'de: Veritabanı -> ML eğitim pipeline -> Surrogate model -> Backend API'ye
"hızlı tahmin" endpoint'i olarak eklenir.

## Malzeme kütüphanesi ve atama

Mesh üretildikten sonra, solver'a gitmeden önceki adım. Mesh'teki katı/parça (Adım 1b'deki
seçim mekanizmasıyla aynı — bir volume/element set seçilir) bir malzemeyle eşleştirilir.

### Veri modeli

`material` tablosu (PostgreSQL, `backend/app/models/material.py`):

```python
class Material:
    id: int
    name: str                 # "S355J2", "6061-T6"
    category: str             # "steel", "aluminum", ...
    standard: str | None      # "EN 10025-2", "ASM"
    density: float            # kg/m3
    youngs_modulus: float     # Pa
    poisson_ratio: float
    yield_strength: float     # Pa (Rp0.2)
    ultimate_strength: float  # Pa (Rm)
    elongation: float | None  # %
    sn_curve: dict | None     # yorulma için Wöhler eğrisi parametreleri (varsa)
    source: str                # "library" | "user_defined"
    is_editable: bool          # kullanıcı tanımlıysa True
```

`material_assignment` tablosu: `run_id`, `element_set_id` (mesh'teki hangi volume/parça),
`material_id`.

### Hazır kütüphane — kapsam ve dürüstlük notu

Başlangıç seti: yaygın yapısal çelikler (S235, S275, S355 — EN 10025 sınıfları,
kalınlığa göre değişen akma dayanımı dahil) ve alüminyum alaşımları (6061-T6, 7075-T6,
2024-T3, 5052-H32 gibi yaygın temper'lar). Değerler standart mühendislik el kitaplarındaki
**tipik/nominal** değerlerdir (EN 10025, ASM Handbook gibi kaynaklardan) — belirli bir
malzeme sertifikasının (mill test report) yerini TUTMAZ. Bu netlik `Material.source` alanı
ve frontend'de "kütüphane değeri (tipik)" etiketiyle kullanıcıya açıkça gösterilir.
Gerçek mühendislik kararları için kullanıcı kendi test verisiyle malzeme
tanımlayabilmeli — bu yüzden `is_editable`/`user_defined` yolu baştan var, salt-okunur bir
kütüphaneyle sınırlı kalmıyoruz.

### Fatigue (S-N eğrisi) — ayrı bir dürüstlük notu

`sn_curve` alanı doldurulabilir olacak ama şunu netleştirelim: gerçek S-N (Wöhler) test
verisi olmayan malzemeler için, statik dayanım değerlerinden (Rm) ampirik korelasyonlarla
(örn. FKM Guideline benzeri yaklaşımlar) **tahmini** bir eğri üretmek mümkün — ama bu
gerçek yorulma testinin yerini tutmaz, sadece kabaca bir başlangıç noktası verir. Bu
tahmini/gerçek ayrımı da veri modelinde (`sn_curve.source: "estimated" | "tested"`) ve
frontend'de görünür tutulur. Yorum/öneri üretmiyoruz (kural 4), sadece verinin kaynağını
şeffaf gösteriyoruz.

### Atama akışı

1. Kullanıcı bir volume/parça seçer (mevcut picking mekanizması).
2. Kütüphaneden bir malzeme seçer ya da kendi değerlerini girer.
3. Atama veritabanına kaydedilir.
4. Solver adaptörünün `build_input` adımında, her element set için doğru malzeme kartı
   yazılır: CalculiX'te `*MATERIAL` + `*ELASTIC` + `*DENSITY` (+ `*SOLID SECTION` ile
   element set'e bağlama), OpenRadioss'ta `/MAT/LAW` kartları.

## Solver adaptörü

CFD (OpenFOAM) diğer iki solver'dan farklı: tek bir girdi dosyası değil, bir **case
klasörü** (dictionary dosyaları: `system/`, `constant/`, `0/`) kullanır. Bu yüzden arayüz
tek dosya varsayımı yapmaz — her solver bu genelleştirilmiş arayüzü uygular
(`backend/app/solvers/base.py`):

```python
class SolverAdapter(ABC):
    def build_input(self, params: dict) -> InputArtifact:
        """Parametreleri alıp solver'ın anlayacağı girdiyi üretir.
        InputArtifact tek dosya (CalculiX .inp, OpenRadioss .rad) ya da
        klasör (OpenFOAM case) olabilir — üst katman farkı bilmez."""

    def submit(self, artifact: InputArtifact) -> JobHandle:
        """Solver'ı çalıştırır (senkron ya da subprocess/queue üzerinden async)."""

    def poll_status(self, job: JobHandle) -> JobStatus:
        """running / done / failed."""

    def parse_results(self, job: JobHandle) -> ResultSet:
        """Sonuç dosyasını/klasörünü okuyup standart ResultSet'e çevirir
        (skaler metrikler + zaman serisi eğriler + varsa alan verisi)."""
```

`ResultSet` şeması solver'dan bağımsız, sabit tutulur — böylece frontend ve db şeması
solver değişse bile aynı kalır:

```python
@dataclass
class ResultSet:
    scalars: dict[str, float]        # örn. {"max_stress": 210.5, "fatigue_life_cycles": 1.2e6}
    curves: dict[str, TimeSeries]    # örn. {"reaction_force": TimeSeries(t, y)}
    raw_result_path: Path            # ham dosya, referans için saklanır
```

## Kompozit modelleme

Kompozit, kendi solver'ı olan ayrı bir faz değil — **CalculiX ve OpenRadioss adaptörlerinin
üzerine eklenen bir modül**. İki solver de kompozit kabuk (shell) elemanlarını, katman
(ply) kalınlığı/açısı/malzemesi tanımını destekliyor. Eksik olan kısım — katman bazlı hasar
kriterleri (Tsai-Wu, Hashin, Puck) — solver çıktısından (katman bazlı gerilme) sonradan
Python'da hesaplanır, solver'ın kendisinden beklenmez.

- `backend/app/composite/layup.py`: klasik laminasyon teorisi (CLT) ile ABD matrisi ve
  katman dizilimi tanımı — bu adım solver'a gitmeden önce, saf Python/numpy ile yapılır.
- `backend/app/composite/section_writer.py`: CLT çıktısını CalculiX
  (`*SHELL SECTION, COMPOSITE`) ya da OpenRadioss (`/PROP/TYPE11` gibi kompozit özellik
  kartları) formatına yazar — solver adaptörünün `build_input` adımına eklenen bir katman.
- `backend/app/composite/failure_criteria.py`: solver sonuç dosyasından katman bazlı
  gerilme/gerinim okunduktan sonra Tsai-Wu/Hashin/Puck kriterlerini uygular, her katman
  için güvenlik faktörü (margin of safety) üretir. Bu, `ResultSet.scalars` içine eklenir.
- Durability (statik/yorulma) ve crash (darbe) senaryolarında kompozit parça analiz
  edilebilir — solver hangisiyse (CalculiX/OpenRadioss) o adaptör kullanılır, kompozit
  modülü ikisiyle de çalışacak şekilde solver-agnostik yazılır.

## CFD

CFD, gerçek anlamda yeni bir solver ailesi ve biraz farklı bir mesh stratejisi gerektirir.

- **Solver:** OpenFOAM (açık kaynak, GPL — OpenRadioss'un AGPL'inden farklı, network-copyleft
  kısıtı yok, bkz. `docs/LICENSING.md`).
- **Mesh stratejisi:** Saf Gmsh yeterli olmayabilir çünkü CFD'de duvar yakınında sınır
  tabakası (boundary layer/inflation) mesh'i kaliteyi doğrudan etkiler. Kanıtlanmış
  kombinasyon: Gmsh geometriyi temizleyip STL yüzey mesh'i üretir → OpenFOAM'ın kendi
  `snappyHexMesh` aracı (ek lisans gerektirmez, OpenFOAM ile birlikte gelir) bu STL'den
  sınır tabakalı hacim mesh'ini üretir. Basit/blok geometrilerde OpenFOAM'ın `blockMesh`'i
  yeterli olabilir — karar `MesherAdapter`'ın CFD-özel implementasyonunda (`cfd_mesher.py`)
  verilir.
- **Case yapısı:** OpenFOAM case'leri metin tabanlı dictionary dosyalarından oluşur
  (`.k` dosyasını parametrize etmeye benzer bir yaklaşımla) — `preprocess` modülü bu
  dictionary'leri (örn. `U`, `p`, `fvSchemes`, `controlDict`) kullanıcı parametrelerine
  göre (giriş hızı, basınç, türbülans modeli vb.) doldurur.
- **Post-process:** OpenFOAM sonuçları zaman adımı bazlı klasörlerde ya da VTK formatında
  yazılır. PyVista (VTK'nin Python arayüzü, açık kaynak) ile okunup kuvvet katsayıları
  (Cd/Cl), basınç dağılımı, akış alanı gibi metrikler/görseller çıkarılır — aynı `ResultSet`
  şemasına dönüştürülür.
- **Uzun süren job'lar:** CFD çözümleri de crash gibi uzun sürebilir (dakikalar-saatler) —
  aynı websocket tabanlı ilerleme takibi (residual/iterasyon bazlı) kullanılır.

## Veritabanı şeması (ilk taslak)

- `analysis_run`: id, created_at, input_params (JSONB), solver_type, status, result_id
- `result`: id, run_id (FK), scalars (JSONB), curves_path, raw_file_path
- `ml_dataset` (Faz 2): run_id (FK), feature_vector, target_vector, model_version

## Sınır koşulları ve yükler (CalculiX / Faz 0)

### Seçim mekanizması

Adım 1b'de kurduğumuz yüzey picking mekanizması burada da aynen kullanılıyor — sadece
yüzey değil, **nokta (vertex), kenar (edge) ve yüzey (face)** seviyesinde seçim
gerekiyor, çünkü point load bir node'a, distributed load bir yüzeye, sliding support bir
kenara uygulanabilir. `triangle_to_face` eşlemesine ek olarak, seçilen entity'nin
dim'ine göre (0=nokta, 1=kenar, 2=yüzey) hangi node/node grubunun etkilendiği backend'de
Gmsh'ten sorgulanır (`gmsh.model.mesh.getNodes(dim, tag)`).

### Yükler ve destekler — native / custom durumu

| Özellik | Durum | Not |
|---|---|---|
| Point load / Force | Native | `*CLOAD` |
| Pressure | Native | `*DLOAD`, P tipi |
| Distributed load | Native | `*DLOAD` — yüzey yükü, gravity, centrifugal |
| Bearing load | **Custom** | CalculiX'te hazır kart yok — delik çevresindeki node'lara açısal konuma göre kosinüs dağılımlı nodal kuvvet olarak `backend/app/preprocess/bearing_load.py`'de üretilir |
| Fixed support | Native | `*BOUNDARY`, tüm DOF = 0 |
| Displacement (prescribed) | Native | `*BOUNDARY`, DOF = değer |
| Sliding joint support | Native | Seçili DOF'lar serbest bırakılır; açılı/silindirik yönler için `*TRANSFORM` ile yerel eksen tanımlanır |
| Acceleration | Kısmen native | Sabit yerçekimi/ivme yükü (`*DLOAD, GRAV`) native; genel "herhangi bir yöne ivme BC'si" kavramı CalculiX'te yok, gravity-tipi yükle sınırlı |
| Velocity | **Bu fazda uygulanamaz** | Statik/modal analizde hız kavramı anlamlı değil — bu Faz 1'de (OpenRadioss/crash) `*INITIAL VELOCITY` olarak native geliyor |

### Sonuçlar — native / custom durumu

| Özellik | Durum | Not |
|---|---|---|
| Deformation | Native | `*NODE FILE, U` |
| Von Mises stress | Yarı-native | Gerilme tensörü (`S11..S23`) native çıkar, von Mises büyüklüğü standart formülle post-process'te bizim tarafımızdan hesaplanır |
| Fatigue | Custom | pyLife ile (zaten Faz 0 planında) |
| Safety factor | Custom | Malzeme akma/dayanım değeri ile von Mises oranından `backend/app/postprocess/safety_factor.py`'de hesaplanır |
| Modal analiz | Native, olgun | `*FREQUENCY` (Lanczos eigenvalue) — CalculiX'in güçlü olduğu alanlardan biri, doğal frekans + mod şekli çıktısı doğrudan gelir |

Bu tablodaki her "custom" satırı, `docs/CLAUDE.md`'deki 4. kuralla (araç veri gösterir,
karar vermez) çelişmiyor — buradaki custom kısımlar mühendislik kararı değil, CalculiX'in
sağlamadığı **hesaplama/veri üretimi** (von Mises formülü, bearing load dağılımı, safety
factor oranı gibi standart mühendislik formülleri). Yorum/öneri değil.

## Post-process sorumluluğu

- Faz 0 (durability, CalculiX): `.frd`/`.dat` sonuç dosyasından gerilme/gerinim çıktısını
  oku → pyLife ile rainflow counting + Miner kuralı → yorulma ömrü (cycles) hesapla.
- Faz 1 (crash, OpenRadioss): OpenRadioss'un `Txxx`/animasyon ve time-history (T01, T02...)
  çıktı dosyalarını oku (topluluk tarafından geliştirilen açık kaynak okuyucular / gerekirse
  kendi parser'ımız) → enerji dengesi, rigid wall reaksiyon kuvveti-zaman eğrisi, ivme
  sinyali, HIC gibi metrikleri çıkar.
- İki fazda da çıktı aynı `ResultSet` şemasına dönüştürülür — frontend grafik kodu
  değişmeden çalışır.

## Job durumu ve kullanıcıya geri bildirim

Analiz süresi saniyelerden saatlere kadar değişebileceği için: job kuyruğa girer girmez
`202 Accepted` + `job_id` dönülür. Frontend `job_id` ile polling ya da websocket üzerinden
durumu takip eder. Solver süresi uzunsa (crash analizleri gibi) websocket + ilerleme
yüzdesi (mümkünse solver log'undan parse edilir) tercih edilir.
