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


class MesherAdapter(ABC):
    @abstractmethod
    def import_geometry(self, cad_file: Path) -> GeometryHandle:
        """STEP/IGES dosyasını içe aktarır."""

    @abstractmethod
    def preview_tessellation(self, geom: GeometryHandle, output_path: Path) -> Path:
        """Hızlı, düşük çözünürlüklü tessellation (STL) üretir - web önizleme için."""

    @abstractmethod
    def generate_mesh(self, geom: GeometryHandle, params: dict[str, Any]) -> Any:
        """Gerçek FEA mesh'i üretir (tet/tri, shell/solid). Henüz implemente edilmedi."""
