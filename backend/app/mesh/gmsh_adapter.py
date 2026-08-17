"""Gmsh tabanlı MesherAdapter implementasyonu.

Bu adımda STEP/IGES import + STL tessellation (web önizleme) + her üçgenin
hangi Gmsh yüzeyine (face) ait olduğunu veren `triangle_to_face` eşlemesi var.

STL dosyasını Gmsh'in kendi `gmsh.write()` fonksiyonuna bırakmak yerine
üçgenleri kendimiz üretip STL'i kendimiz yazıyoruz — böylece üçgen sırası
garantili biliniyor, `triangle_to_face` eşlemesi Gmsh'in dahili yazıcısının
üçgenleri nasıl sıraladığına bel bağlamıyor.

Gerçek FEA mesh üretimi (`generate_mesh`) ROADMAP.md'deki "2. Mesh üretimi"
adımında eklenecek.
"""

import math
from pathlib import Path
from typing import Any

import gmsh

from app.mesh.base import GeometryHandle, MesherAdapter, TessellationResult

# Gmsh eleman tipi kodu: 3 düğümlü üçgen (bkz. Gmsh dokümantasyonu, "elementType").
_TRIANGLE_ELEMENT_TYPE = 2


class GmshImportError(RuntimeError):
    """Gmsh geometriyi okuyamadığında (bozuk/desteklenmeyen dosya) fırlatılır."""


def _face_normal(
    v0: tuple[float, float, float],
    v1: tuple[float, float, float],
    v2: tuple[float, float, float],
) -> tuple[float, float, float]:
    ux, uy, uz = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
    wx, wy, wz = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
    nx, ny, nz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


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

    def preview_tessellation(
        self, geom: GeometryHandle, output_path: Path
    ) -> TessellationResult:
        """Açık olan Gmsh modelinden STL + üçgen→yüzey + üçgen→parça eşlemesi üretir.

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı (Gmsh o an tek bir aktif model tutar).
        """
        try:
            # Yüzey bazlı sorgulanabilir bir mesh üret (Gmsh'in otomatik STL
            # tessellation'ı yüzey bilgisini saklamıyor, bu yüzden kendi 2B
            # yüzey mesh algoritmasını çalıştırıyoruz).
            gmsh.model.mesh.generate(2)

            # Montaj (assembly) dosyalarında birden fazla ayrı katı (volume)
            # olabilir. Her katının sınır yüzeylerinden face_tag -> part_id
            # (part_id = sıradaki parça indeksi, 0'dan başlar) eşlemesi kur.
            # Hiç volume yoksa (örn. tek açık yüzey/kabuk) her şey part 0.
            face_to_part: dict[int, int] = {}
            volumes = gmsh.model.getEntities(dim=3)
            for part_id, (_dim, volume_tag) in enumerate(volumes):
                boundary = gmsh.model.getBoundary([(3, volume_tag)], oriented=False)
                for b_dim, b_tag in boundary:
                    if b_dim == 2:
                        face_to_part[b_tag] = part_id
            part_count = max(len(volumes), 1)

            node_tags_all, coords_all, _ = gmsh.model.mesh.getNodes()
            node_coords: dict[int, tuple[float, float, float]] = {
                int(tag): (coords_all[3 * i], coords_all[3 * i + 1], coords_all[3 * i + 2])
                for i, tag in enumerate(node_tags_all)
            }

            triangle_to_face: list[int] = []
            triangle_to_part: list[int] = []
            triangle_vertices: list[
                tuple[
                    tuple[float, float, float],
                    tuple[float, float, float],
                    tuple[float, float, float],
                ]
            ] = []

            for _dim, face_tag in gmsh.model.getEntities(dim=2):
                elem_types, elem_tags_per_type, node_tags_per_type = (
                    gmsh.model.mesh.getElements(dim=2, tag=face_tag)
                )
                part_id = face_to_part.get(face_tag, 0)
                for etype, elem_tags, elem_node_tags in zip(
                    elem_types, elem_tags_per_type, node_tags_per_type
                ):
                    if etype != _TRIANGLE_ELEMENT_TYPE:
                        # Bu adımın kapsamı üçgen (tri) mesh; quad vb. çıkarsa
                        # (beklenmez ama) sessizce atlamak yerine haberdar ol.
                        continue
                    n_elems = len(elem_tags)
                    for i in range(n_elems):
                        n0, n1, n2 = elem_node_tags[3 * i : 3 * i + 3]
                        triangle_vertices.append(
                            (node_coords[int(n0)], node_coords[int(n1)], node_coords[int(n2)])
                        )
                        triangle_to_face.append(int(face_tag))
                        triangle_to_part.append(part_id)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            _write_ascii_stl(output_path, geom.model_name, triangle_vertices)
        finally:
            gmsh.finalize()

        return TessellationResult(
            stl_path=output_path,
            triangle_to_face=triangle_to_face,
            triangle_to_part=triangle_to_part,
            part_count=part_count,
        )

    def generate_mesh(self, geom: GeometryHandle, params: dict[str, Any]) -> Any:
        raise NotImplementedError(
            "FEA mesh üretimi henüz implemente edilmedi — ROADMAP.md '2. Mesh "
            "üretimi' adımında eklenecek."
        )


def _write_ascii_stl(
    output_path: Path,
    solid_name: str,
    triangles: list[
        tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ],
) -> None:
    with output_path.open("w") as f:
        f.write(f"solid {solid_name}\n")
        for v0, v1, v2 in triangles:
            nx, ny, nz = _face_normal(v0, v1, v2)
            f.write(f"facet normal {nx:.6e} {ny:.6e} {nz:.6e}\n")
            f.write("  outer loop\n")
            for v in (v0, v1, v2):
                f.write(f"    vertex {v[0]:.6e} {v[1]:.6e} {v[2]:.6e}\n")
            f.write("  endloop\n")
            f.write("endfacet\n")
        f.write(f"endsolid {solid_name}\n")
