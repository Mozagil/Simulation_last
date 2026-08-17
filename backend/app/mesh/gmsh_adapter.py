"""Gmsh tabanlı MesherAdapter implementasyonu.

Bu adımda sadece STEP/IGES import + STL tessellation (web önizleme) var.
Gerçek FEA mesh üretimi (`generate_mesh`) ROADMAP.md'deki "2. Mesh üretimi"
adımında eklenecek.
"""

from pathlib import Path
from typing import Any

import gmsh

from app.mesh.base import GeometryHandle, MesherAdapter


class GmshImportError(RuntimeError):
    """Gmsh geometriyi okuyamadığında (bozuk/desteklenmeyen dosya) fırlatılır."""


class GmshMesherAdapter(MesherAdapter):
    def import_geometry(self, cad_file: Path) -> GeometryHandle:
        model_name = cad_file.stem

        gmsh.initialize(interruptible=False)
        try:
            gmsh.model.add(model_name)
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.open(str(cad_file))
            gmsh.model.occ.synchronize()

            volumes = gmsh.model.getEntities(dim=3)
            surfaces = gmsh.model.getEntities(dim=2)
            if not volumes and not surfaces:
                raise GmshImportError(
                    f"Dosyadan hiçbir geometri okunamadı: {cad_file.name}"
                )
        except Exception as exc:
            gmsh.finalize()
            if isinstance(exc, GmshImportError):
                raise
            raise GmshImportError(
                f"Gmsh dosyayı içe aktaramadı: {cad_file.name} ({exc})"
            ) from exc

        return GeometryHandle(model_name=model_name, source_file=cad_file)

    def preview_tessellation(self, geom: GeometryHandle, output_path: Path) -> Path:
        """Açık olan Gmsh modelini STL olarak dışa aktarır.

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı (Gmsh o an tek bir aktif model tutar).
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            gmsh.write(str(output_path))
        finally:
            gmsh.finalize()

        return output_path

    def generate_mesh(self, geom: GeometryHandle, params: dict[str, Any]) -> Any:
        raise NotImplementedError(
            "FEA mesh üretimi henüz implemente edilmedi — ROADMAP.md '2. Mesh "
            "üretimi' adımında eklenecek."
        )
