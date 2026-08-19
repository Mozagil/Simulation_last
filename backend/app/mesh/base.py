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
from typing import Any


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
    """Küçük delik/fillet bastırma için aday bir kenar (dairesel/döngü).

    Bu adımın kapsamı sadece TESPİT — ROADMAP: "o eşiğin altındaki dairesel
    yüzeyler işaretlenir (henüz kaldırmadan)". Gerçek kaldırma (boolean
    operasyon) Gmsh'in düz Python API'sinde yok (OCC'nin BRepAlgoAPI_Defeaturing
    sınıfı gerekir, bu da pythonocc-core bağımlılığı ister — ayrı bir mimari
    karar, ROADMAP/ARCHITECTURE'da zaten "Gmsh'in yetersiz kaldığı yerlerde"
    pythonocc-core kullanılacağı belirtilmiş).
    """

    edge_id: int
    approx_diameter: float
    part_id: int


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
        """Küçük boşluk/tolerans hatalarını düzeltir (`occ.healShapes`).

        Kalıcılık: `copy_surface` ile aynı desen — sonuç `geom.source_file`'a
        geri yazılır.
        """

    @abstractmethod
    def find_defeature_candidates(
        self, geom: GeometryHandle, max_diameter: float
    ) -> list[DefeatureCandidate]:
        """Verilen eşik altındaki dairesel/döngü kenarları tespit eder (henüz
        kaldırmaz — sadece işaretleme adımı).
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
    def generate_mesh(self, geom: GeometryHandle, params: dict[str, Any]) -> Any:
        """Gerçek FEA mesh'i üretir (tet/tri, shell/solid). Henüz implemente edilmedi."""
