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
import threading
from pathlib import Path
from typing import Any

import gmsh

from app.mesh.base import (
    EdgeInfo,
    GeometryHandle,
    MesherAdapter,
    PointInfo,
    SurfaceInfo,
    TessellationResult,
)

# Gmsh eleman tipi kodu: 3 düğümlü üçgen (bkz. Gmsh dokümantasyonu, "elementType").
_TRIANGLE_ELEMENT_TYPE = 2

# Gmsh'in Python API'si süreç genelinde TEK bir global C++ durumu paylaşır
# (gmsh.initialize/open/finalize hepsi aynı global context'i değiştirir).
# FastAPI'nin sync endpoint'leri (bu adaptörü kullananlar) uvicorn tarafından
# bir thread pool'da çalıştırılıyor — iki istek gerçekten aynı anda farklı
# thread'lerde Gmsh'e dokunursa (örn. frontend'in Promise.all ile edges+points'i
# paralel çekmesi), Gmsh'in global durumu bozuluyor ve segfault/tutarsız hata
# oluşabiliyor (bu, gerçek bir testte doğrulandı). Bu kilit, herhangi bir anda
# sadece TEK bir Gmsh oturumunun (import_geometry -> ... -> finalize) aktif
# olmasını garanti eder.
#
# ÖNEMLİ: import_geometry() kilidi alır; onu izleyen tam olarak bir sonraki
# çağrı (preview_tessellation/list_surfaces/list_edges/list_points) kilidi
# serbest bırakır (finally bloğunda gmsh.finalize() ile birlikte). Bu adaptörü
# kullanan her kod, import_geometry()'den sonra MUTLAKA bu metodlardan birini
# çağırmalı — aksi halde kilit serbest kalmaz (deadlock).
_gmsh_lock = threading.Lock()


class GmshImportError(RuntimeError):
    """Gmsh geometriyi okuyamadığında (bozuk/desteklenmeyen dosya) fırlatılır."""


class SurfaceNotFoundError(RuntimeError):
    """İstenen yüzey (face) modelde bulunamadığında fırlatılır."""


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


def _compute_face_to_part() -> tuple[dict[int, int], int]:
    """Açık Gmsh oturumundaki her yüzeyin (face) hangi katıya (volume/parça)
    ait olduğunu hesaplar. Montaj dosyalarında birden fazla ayrı katı olabilir;
    hiç volume yoksa (örn. tek açık yüzey/kabuk) her şey part 0 sayılır.
    """
    face_to_part: dict[int, int] = {}
    volumes = gmsh.model.getEntities(dim=3)
    for part_id, (_dim, volume_tag) in enumerate(volumes):
        boundary = gmsh.model.getBoundary([(3, volume_tag)], oriented=False)
        for b_dim, b_tag in boundary:
            if b_dim == 2:
                face_to_part[b_tag] = part_id
    part_count = max(len(volumes), 1)
    return face_to_part, part_count


def _compute_edge_to_part(face_to_part: dict[int, int]) -> dict[int, int]:
    """Her kenarın (curve) parçasını, komşu olduğu ilk yüzeyin parçasından belirler."""
    edge_to_part: dict[int, int] = {}
    for _dim, edge_tag in gmsh.model.getEntities(dim=1):
        upward, _downward = gmsh.model.getAdjacencies(1, edge_tag)
        for face_tag in upward:
            if int(face_tag) in face_to_part:
                edge_to_part[edge_tag] = face_to_part[int(face_tag)]
                break
        else:
            edge_to_part[edge_tag] = 0
    return edge_to_part


def _compute_point_to_part(edge_to_part: dict[int, int]) -> dict[int, int]:
    """Her noktanın (vertex) parçasını, komşu olduğu ilk kenarın parçasından belirler."""
    point_to_part: dict[int, int] = {}
    for _dim, point_tag in gmsh.model.getEntities(dim=0):
        upward, _downward = gmsh.model.getAdjacencies(0, point_tag)
        for edge_tag in upward:
            if int(edge_tag) in edge_to_part:
                point_to_part[point_tag] = edge_to_part[int(edge_tag)]
                break
        else:
            point_to_part[point_tag] = 0
    return point_to_part


class GmshMesherAdapter(MesherAdapter):
    def import_geometry(self, cad_file: Path) -> GeometryHandle:
        model_name = cad_file.stem

        _gmsh_lock.acquire()
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
            _gmsh_lock.release()
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
            # eşlemesi kur (part_id = sıradaki parça indeksi, 0'dan başlar).
            face_to_part, part_count = _compute_face_to_part()

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
            _gmsh_lock.release()

        return TessellationResult(
            stl_path=output_path,
            triangle_to_face=triangle_to_face,
            triangle_to_part=triangle_to_part,
            part_count=part_count,
        )

    def list_surfaces(self, geom: GeometryHandle) -> list[SurfaceInfo]:
        """Modeldeki her yüzeyin id, alan, normal ve parça bilgisini döner.

        Alan `gmsh.model.occ.getMass` ile (mesh'e değil, tam OCC geometrisine
        dayalı, yani mesh çözünürlüğünden bağımsız kesin değer) hesaplanır.
        Normal, yüzeyin parametrik alanının orta noktasında `getNormal` ile
        alınır — eğri (kavisli) yüzeylerde bu tek bir temsili yön olur, tüm
        yüzeyin ortalama normali değil.

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı.
        """
        try:
            face_to_part, _part_count = _compute_face_to_part()

            surfaces: list[SurfaceInfo] = []
            for _dim, face_tag in gmsh.model.getEntities(dim=2):
                area = gmsh.model.occ.getMass(2, face_tag)

                (umin, vmin), (umax, vmax) = gmsh.model.getParametrizationBounds(
                    2, face_tag
                )
                umid, vmid = (umin + umax) / 2, (vmin + vmax) / 2
                normal_raw = gmsh.model.getNormal(face_tag, [umid, vmid])
                normal = (float(normal_raw[0]), float(normal_raw[1]), float(normal_raw[2]))

                surfaces.append(
                    SurfaceInfo(
                        id=int(face_tag),
                        area=float(area),
                        normal=normal,
                        part_id=face_to_part.get(face_tag, 0),
                    )
                )
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return surfaces

    def list_edges(self, geom: GeometryHandle) -> list[EdgeInfo]:
        """Modeldeki her kenarın id, uzunluk, parça ve uç nokta bilgisini döner.

        Uzunluk `gmsh.model.occ.getMass(1, tag)` ile (mesh'e değil, tam OCC
        eğrisine dayalı kesin değer) hesaplanır. Parça, kenarın komşu olduğu
        ilk yüzeyin parçasından belirlenir.

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı.
        """
        try:
            face_to_part, _part_count = _compute_face_to_part()
            edge_to_part = _compute_edge_to_part(face_to_part)

            edges: list[EdgeInfo] = []
            for _dim, edge_tag in gmsh.model.getEntities(dim=1):
                length = gmsh.model.occ.getMass(1, edge_tag)
                _upward, downward = gmsh.model.getAdjacencies(1, edge_tag)
                # Bir kenarın normalde 2 uç noktası olur; kapalı eğrilerde
                # (örn. tam çember) tek nokta olabilir — bu durumda ikisini de
                # aynı noktaya eşitliyoruz.
                start_point = int(downward[0]) if len(downward) > 0 else 0
                end_point = int(downward[1]) if len(downward) > 1 else start_point

                edges.append(
                    EdgeInfo(
                        id=int(edge_tag),
                        length=float(length),
                        part_id=edge_to_part.get(edge_tag, 0),
                        start_point=start_point,
                        end_point=end_point,
                    )
                )
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return edges

    def list_points(self, geom: GeometryHandle) -> list[PointInfo]:
        """Modeldeki her köşe noktasının id, koordinat ve parça bilgisini döner.

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı.
        """
        try:
            face_to_part, _part_count = _compute_face_to_part()
            edge_to_part = _compute_edge_to_part(face_to_part)
            point_to_part = _compute_point_to_part(edge_to_part)

            points: list[PointInfo] = []
            for _dim, point_tag in gmsh.model.getEntities(dim=0):
                coord_raw = gmsh.model.getValue(0, point_tag, [])
                coordinate = (float(coord_raw[0]), float(coord_raw[1]), float(coord_raw[2]))

                points.append(
                    PointInfo(
                        id=int(point_tag),
                        coordinate=coordinate,
                        part_id=point_to_part.get(point_tag, 0),
                    )
                )
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return points

    def copy_surface(self, geom: GeometryHandle, face_id: int) -> int:
        """Verilen yüzeyi `occ.copy` ile çoğaltır, yeni yüzeyin tag'ini döner.

        Kalıcılık için güncellenmiş model `geom.source_file`'a geri yazılır
        (overwrite) — bir sonraki istek bu dosyayı tekrar içe aktardığında
        kopyalanan yüzey de görünür.

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı.
        """
        try:
            existing_faces = {tag for _dim, tag in gmsh.model.getEntities(dim=2)}
            if face_id not in existing_faces:
                raise SurfaceNotFoundError(
                    f"Yüzey bulunamadı: id={face_id}. Mevcut yüzeyler: {sorted(existing_faces)}"
                )

            copied = gmsh.model.occ.copy([(2, face_id)])
            gmsh.model.occ.synchronize()

            if not copied or copied[0][0] != 2:
                raise SurfaceNotFoundError(
                    f"Yüzey kopyalanamadı: id={face_id} (beklenmeyen Gmsh yanıtı: {copied})"
                )
            new_face_id = copied[0][1]

            # Kalıcılık: mutasyonu diske geri yaz.
            gmsh.write(str(geom.source_file))
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return new_face_id

    def create_physical_group(
        self, geom: GeometryHandle, face_ids: list[int], name: str
    ) -> int:
        """Verilen yüzeyleri isimli bir Gmsh Physical Group'a atar, tag'i döner.

        Gmsh'in kendi `addPhysicalGroup` API'si geçersiz entity tag'lerini
        sessizce kabul edip hatayı ancak sonradan sorgulamada veriyor (gerçek
        bir testte doğrulandı) — bu yüzden face_id'leri KENDİMİZ önceden
        doğruluyoruz.

        Kalıcılık DB katmanında (bkz. app.models.geometry.PhysicalGroup) —
        burada dosyaya geri yazma yok, Physical Group STEP formatının bir
        parçası değil.

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı.
        """
        try:
            existing_faces = {tag for _dim, tag in gmsh.model.getEntities(dim=2)}
            invalid_ids = [fid for fid in face_ids if fid not in existing_faces]
            if invalid_ids:
                raise SurfaceNotFoundError(
                    f"Geçersiz yüzey id'leri: {invalid_ids}. "
                    f"Mevcut yüzeyler: {sorted(existing_faces)}"
                )

            group_tag = gmsh.model.addPhysicalGroup(2, face_ids, name=name)
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return group_tag

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
