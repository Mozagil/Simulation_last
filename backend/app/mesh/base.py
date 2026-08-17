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
    """

    stl_path: Path
    triangle_to_face: list[int]


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
    def generate_mesh(self, geom: GeometryHandle, params: dict[str, Any]) -> Any:
        """Gerçek FEA mesh'i üretir (tet/tri, shell/solid). Henüz implemente edilmedi."""
