"""Mesh aracı adaptör arayüzü.

CLAUDE.md kural 1: hiçbir iş mantığı doğrudan bir mesh aracına (Gmsh) bağımlı
yazılmaz — her mesh aracı bu arayüzü uygular. Bu şu an sadece `import_geometry`
ve `preview_tessellation` içeriyor; `generate_mesh` (gerçek FEA mesh üretimi)
ROADMAP.md'deki "2. Mesh üretimi" adımında implemente edilecek — bilinçli
olarak `NotImplementedError` bırakıldı, bu adımın kapsamı sadece web önizleme.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GeometryHandle:
    """İçe aktarılmış geometriye referans (Gmsh model adı + kaynak dosya)."""

    model_name: str
    source_file: Path


@dataclass
class TessellationResult:
    """Web önizleme tessellation çıktısı.

    `triangle_to_face[i]`, STL dosyasındaki i. üçgenin ait olduğu Gmsh yüzey
    (face) tag'ini verir — ROADMAP.md "1b. Geometri işleme operasyonları"
    adımında, frontend'de yüzey picking (tıklanan üçgenden yüzeyi bulma) için
    gereken temel eşleme.

    `triangle_to_part[i]`, aynı üçgenin ait olduğu Gmsh katısını (volume/parça)
    verir — montaj (assembly) STEP dosyalarında birden fazla ayrı parça olduğunda,
    bir yüzeyin hangi parçaya ait olduğunu ayırt etmek için. Modelde hiç volume
    yoksa (örn. tek bir açık yüzey/kabuk), tüm üçgenler part 0'a atanır.
    """

    stl_path: Path
    triangle_to_face: list[int]
    triangle_to_part: list[int]
    part_count: int
    # GERÇEK bir 3B katıya (volume) karşılık gelen part_id'ler — "Solid
    # gizle/göster" gibi işlemler sadece bunları hedeflemeli, `copy_surface`/
    # `midsurface` çıktısı gibi düz (volume'süz) yüzey parçalarını değil.
    volume_part_ids: list[int]


@dataclass
class SurfaceInfo:
    """Bir Gmsh yüzeyinin (face) özet bilgisi.

    ROADMAP.md "1b. Geometri işleme operasyonları" — dış yüzey (skin)
    listeleme adımı için: id + alan + normal. `part_id`, montaj dosyalarında
    yüzeyin hangi parçaya ait olduğunu gösterir (bkz. TessellationResult).
    """

    id: int
    area: float
    normal: tuple[float, float, float]
    part_id: int


@dataclass
class EdgeInfo:
    """Bir Gmsh kenarının (curve) özet bilgisi.

    Frontend'de seçim modu (Part/Surface/Edge/Point) için — kullanıcı bir
    kenara tıkladığında hangi Gmsh curve tag'ine ait olduğunu bulabilmek.
    `start_point`/`end_point`, kenarın uç noktalarının (vertex) tag'leridir —
    frontend'in kenarı çizebilmesi için gereken koordinatlar `list_points`'ten
    alınır.
    """

    id: int
    length: float
    part_id: int
    start_point: int
    end_point: int


@dataclass
class PointInfo:
    """Bir Gmsh köşe noktasının (vertex) özet bilgisi."""

    id: int
    coordinate: tuple[float, float, float]
    part_id: int


@dataclass
class HealResult:
    """Geometry healing öncesi/sonrası özet — ROADMAP kabul kriteri: "önce/sonra
    yüzey-katı sayısı loglanıp karşılaştırılır".
    """

    volumes_before: int
    surfaces_before: int
    volumes_after: int
    surfaces_after: int


@dataclass
class DefeatureCandidate:
    """Fillet/blend adayı yüzey (Cylinder / Sphere / Torus).

    Tespit: yaklaşık yarıçap <= eşik. Through-hole silindirleri (Heal kapsamı)
    aday değildir. Kaldırma: 2D/midsurface kabukta keskin shell; solid'de
    keskin AABB kutu (`apply_defeature`).
    """

    face_id: int
    approx_radius: float
    surface_type: str
    part_id: int



@dataclass
class MeshParams:
    """FEA mesh üretim parametreleri.

    `dimension=3`: solid volume mesh.
    `dimension=2`: shell (orphan/midsurface) yüzey mesh.
    `element_scheme`: tet | quad | mix
      - 2D: tet→tri, quad→recombine quad, mix→tri+quad
      - 3D: tet→tet, quad→hex (recombine3D), mix→tet (şimdilik)
    """

    element_size: float
    dimension: int  # 2 | 3
    element_scheme: str = "tet"  # tet | quad | mix


@dataclass
class MeshResult:
    """Üretilmiş FEA mesh özeti + viewer wireframe önizleme dosyası."""

    mesh_path: Path
    node_count: int
    element_count: int
    dimension: int
    element_type_counts: dict[str, int]
    preview_path: Path | None = None
    element_scheme: str = "tet"


@dataclass
class MeshQualityMetric:
    """Tek bir kalite metriğinin özeti + eleman bazlı değerler."""

    name: str
    min: float
    max: float
    mean: float
    values: list[float]


@dataclass
class MeshQualityResult:
    """Mesh kalite raporu (Jacobian + aspect ratio)."""

    mesh_path: Path
    dimension: int
    element_count: int
    element_tags: list[int]
    jacobian: MeshQualityMetric
    aspect_ratio: MeshQualityMetric


class MeshError(Exception):
    """Mesh üretimi için geçersiz parametre / yetersiz geometri."""


class MesherAdapter(ABC):
    @abstractmethod
    def import_geometry(self, cad_file: Path) -> GeometryHandle:
        """STEP/IGES dosyasını içe aktarır."""

    @abstractmethod
    def preview_tessellation(
        self, geom: GeometryHandle, output_path: Path
    ) -> TessellationResult:
        """Hızlı tessellation (STL) + üçgen→yüzey eşlemesi üretir - web önizleme için."""

    @abstractmethod
    def list_surfaces(self, geom: GeometryHandle) -> list[SurfaceInfo]:
        """Modeldeki tüm yüzeylerin (id, alan, normal, parça) listesini döner."""

    @abstractmethod
    def list_edges(self, geom: GeometryHandle) -> list[EdgeInfo]:
        """Modeldeki tüm kenarların (id, uzunluk, parça, uç noktaları) listesini döner."""

    @abstractmethod
    def list_points(self, geom: GeometryHandle) -> list[PointInfo]:
        """Modeldeki tüm köşe noktalarının (id, koordinat, parça) listesini döner."""

    @abstractmethod
    def copy_surface(self, geom: GeometryHandle, face_id: int) -> int:
        """Verilen yüzeyi (face) ayrı bir entity olarak çoğaltır, yeni tag'i döner.

        Kalıcılık: kopyalama sonrası güncellenmiş model `geom.source_file`'a
        geri yazılır (`gmsh.write`, overwrite) — bir sonraki istek bu dosyayı
        tekrar içe aktardığında kopyalanan yüzey de görünür. Bu, gerçek bir
        testte doğrulandı (ayrı bir Python sürecinde dosya tekrar açıldığında
        yeni yüzey hâlâ mevcuttu).
        """

    @abstractmethod
    def create_physical_group(
        self, geom: GeometryHandle, face_ids: list[int], name: str
    ) -> int:
        """Verilen yüzeyleri isimli bir Gmsh Physical Group'a atar, tag'i döner.

        NOT: Physical Group'lar STEP dosyasının bir parçası değil (bu saf bir
        Gmsh/mesh modelleme kavramı) — bu yüzden `copy_surface`'ın aksine
        burada dosyaya geri yazma YOK. Kalıcılık tamamen veritabanı katmanında
        (bkz. `app.models.geometry.PhysicalGroup`) sağlanıyor; bu metod sadece
        Gmsh'in kendi doğrulama/API'siyle atamanın geçerli olduğunu kanıtlıyor.
        """

    @abstractmethod
    def heal_geometry(self, geom: GeometryHandle) -> HealResult:
        """Tolerans onarımı + silindirik yüzey deliklerini kapatma.

        `occ.healShapes` sonrası Cylinder delikleri plug+fuse ile doldurulur.
        Kalıcılık: sonuç `geom.source_file`'a geri yazılır.
        """

    @abstractmethod
    def find_defeature_candidates(
        self, geom: GeometryHandle, max_radius: float
    ) -> list[DefeatureCandidate]:
        """Yarıçapı eşik altındaki fillet yüzeylerini tespit eder (kaldırmadan)."""

    @abstractmethod
    def apply_defeature(
        self,
        geom: GeometryHandle,
        max_radius: float | None = None,
        face_ids: list[int] | None = None,
    ) -> HealResult:
        """Fillet/radyus kaldırıp keskin köşe üretir.

        face_ids (2D seçim) veya max_radius (otomatik) ile çalışır.
        """

    @abstractmethod
    def create_midsurface(
        self, geom: GeometryHandle, face_id_a: int, face_id_b: int
    ) -> int:
        """İki paralel, düzlemsel yüzey arasında orta yüzeyi hesaplar, yeni
        yüzeyin tag'ini döner.

        Kapsam (ROADMAP: "test parçası: sabit kalınlıklı düz plaka"): sadece
        DÜZLEMSEL ve PARALEL yüzey çiftleri desteklenir — genel eğri yüzeyler
        arası midsurface (B-spline interpolasyonu) kapsam dışı. Yüzeyler bu
        koşulu sağlamıyorsa `MidsurfaceError` fırlatılır.

        Kalıcılık: `copy_surface` ile aynı desen — sonuç `geom.source_file`'a
        geri yazılır.
        """

    @abstractmethod
    def create_midsurface_for_part(
        self, geom: GeometryHandle, part_id: int
    ) -> list[tuple[int, int, int]]:
        """Verilen parçadaki TÜM ince-cidar (thin-wall) yüzey çiftleri için
        midsurface hesaplar.

        Döndürür: [(yeni_yüzey_id, yüz_a_id, yüz_b_id), ...] — kutu profilde
        her cidar için bir orta yüzey (örn. 40×40×2 mm profil → ~38×38 mid-shell
        oluşturan 4 yüzey); düz plakada tek çift.

        Tespit: her düzlemsel yüzeyin en yakın paralel eşi; kalınlık /
        sqrt(min_alan) eşiğin altındaysa ince cidar sayılır. "En büyük alan"
        tek çifti seçilmez.
        """

    @abstractmethod
    def generate_mesh(self, geom: GeometryHandle, params: MeshParams) -> MeshResult:
        """FEA mesh üretir: dimension=3 tet (solid), dimension=2 tri (shell)."""