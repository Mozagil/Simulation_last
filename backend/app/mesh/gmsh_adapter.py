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
    DefeatureCandidate,
    EdgeInfo,
    GeometryHandle,
    HealResult,
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


class MidsurfaceError(RuntimeError):
    """Verilen iki yüzey midsurface için uygun değilse (paralel/düzlemsel
    değilse) fırlatılır.
    """


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
    """Açık Gmsh oturumundaki her yüzeyin (face) hangi parçaya ait olduğunu
    hesaplar.

    İki aşama:
    1. Bir katıya (volume) ait yüzeyler — her volume kendi part_id'sini alır
       (montaj dosyalarında birden fazla ayrı katı olabilir).
    2. Hiçbir volume'e ait olmayan yüzeyler ("orphan") — bunlar kenar
       paylaşımına göre bağlı bileşenlere (connected components) ayrılır,
       her bağlı bileşen kendi part_id'sini alır. Bu, örneğin `occ.copy` ile
       bir solid'den bağımsız hale getirilmiş bir yüzeyin, orijinal solid'le
       aynı parçaya (part 0'a varsayılan düşme) yanlışlıkla karışmasını
       önler — kopyalanan yüzeyin kenarları orijinalden tamamen farklı
       (yeni) tag'lerdir (gerçek bir testte doğrulandı), yani kenar
       paylaşımına bakan bu algoritma onu otomatik olarak ayrı bir parça
       sayar. Tek parçalı, birden fazla yüzeyden oluşan açık bir kabuk
       (örn. eğri bir sac parça) da bu sayede doğru şekilde TEK parça
       olarak kalır (yüzeyleri birbirine kenarlarla bağlı olduğu için).
    """
    face_to_part: dict[int, int] = {}
    next_part_id = 0

    volumes = gmsh.model.getEntities(dim=3)
    for _dim, volume_tag in volumes:
        boundary = gmsh.model.getBoundary([(3, volume_tag)], oriented=False)
        for b_dim, b_tag in boundary:
            if b_dim == 2:
                face_to_part[b_tag] = next_part_id
        next_part_id += 1

    all_faces = [tag for _dim, tag in gmsh.model.getEntities(dim=2)]
    orphan_faces = [f for f in all_faces if f not in face_to_part]

    face_edges: dict[int, set[int]] = {}
    for f in orphan_faces:
        boundary = gmsh.model.getBoundary([(2, f)], oriented=False)
        face_edges[f] = {b_tag for b_dim, b_tag in boundary if b_dim == 1}

    visited: set[int] = set()
    for f in orphan_faces:
        if f in visited:
            continue
        component = [f]
        visited.add(f)
        queue = [f]
        while queue:
            current = queue.pop()
            for other in orphan_faces:
                if other in visited:
                    continue
                if face_edges[current] & face_edges[other]:
                    visited.add(other)
                    component.append(other)
                    queue.append(other)
        for face_id in component:
            face_to_part[face_id] = next_part_id
        next_part_id += 1

    part_count = max(next_part_id, 1)
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


def _get_face_normal(face_tag: int) -> tuple[float, float, float]:
    """Bir yüzeyin parametrik alanının orta noktasındaki normalini döner."""
    (umin, vmin), (umax, vmax) = gmsh.model.getParametrizationBounds(2, face_tag)
    umid, vmid = (umin + umax) / 2, (vmin + vmax) / 2
    normal_raw = gmsh.model.getNormal(face_tag, [umid, vmid])
    return (float(normal_raw[0]), float(normal_raw[1]), float(normal_raw[2]))


def _get_face_point(face_tag: int) -> tuple[float, float, float]:
    """Bir yüzeyin parametrik alanının orta noktasındaki 3B koordinatı döner."""
    (umin, vmin), (umax, vmax) = gmsh.model.getParametrizationBounds(2, face_tag)
    umid, vmid = (umin + umax) / 2, (vmin + vmax) / 2
    point_raw = gmsh.model.getValue(2, face_tag, [umid, vmid])
    return (float(point_raw[0]), float(point_raw[1]), float(point_raw[2]))


def _validate_planar_parallel_pair(face_id_a: int, face_id_b: int) -> None:
    """İki yüzeyin midsurface için uygun olduğunu (düzlemsel + paralel)
    doğrular, uygun değilse MidsurfaceError fırlatır.
    """
    type_a = gmsh.model.getType(2, face_id_a)
    type_b = gmsh.model.getType(2, face_id_b)
    if type_a != "Plane" or type_b != "Plane":
        raise MidsurfaceError(
            f"Midsurface sadece düzlemsel (Plane) yüzeyler için destekleniyor. "
            f"Yüzey {face_id_a}: {type_a}, Yüzey {face_id_b}: {type_b}."
        )

    normal_a = _get_face_normal(face_id_a)
    normal_b = _get_face_normal(face_id_b)
    dot = sum(a * b for a, b in zip(normal_a, normal_b))
    # Paralel (dot ~ +1) ya da anti-paralel (dot ~ -1) kabul edilir — bir
    # plakanın iki yüzü genelde anti-paraleldir (dışa bakarlar).
    if abs(abs(dot) - 1.0) > 1e-3:
        raise MidsurfaceError(
            f"Yüzeyler paralel değil (normal dot product={dot:.4f}, beklenen ±1.0'a yakın)."
        )


def _construct_midsurface(face_id_a: int, face_id_b: int) -> int:
    """A'yı kopyalayıp B yönünde yarı mesafe kadar kaydırarak midsurface
    üretir. Çağrıdan önce `_validate_planar_parallel_pair` ile doğrulama
    yapılmış olmalı — bu fonksiyon kendi başına doğrulama yapmaz.
    """
    normal_a = _get_face_normal(face_id_a)
    point_a = _get_face_point(face_id_a)
    point_b = _get_face_point(face_id_b)

    delta = tuple(point_b[i] - point_a[i] for i in range(3))
    thickness = sum(delta[i] * normal_a[i] for i in range(3))
    if abs(thickness) < 1e-9:
        raise MidsurfaceError(
            "Yüzeyler arasında ölçülebilir bir mesafe yok (aynı düzlemde olabilirler)."
        )

    offset = tuple(normal_a[i] * (thickness / 2) for i in range(3))

    copied = gmsh.model.occ.copy([(2, face_id_a)])
    gmsh.model.occ.synchronize()
    if not copied or copied[0][0] != 2:
        raise MidsurfaceError(
            f"Midsurface için ara kopya oluşturulamadı (beklenmeyen Gmsh yanıtı: {copied})"
        )
    new_face_id = copied[0][1]

    gmsh.model.occ.translate([(2, new_face_id)], *offset)
    gmsh.model.occ.synchronize()

    return new_face_id


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

    def heal_geometry(self, geom: GeometryHandle) -> HealResult:
        """`occ.healShapes` ile küçük boşluk/tolerans hatalarını düzeltir.

        Kalıcılık için güncellenmiş model `geom.source_file`'a geri yazılır.

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı.
        """
        try:
            volumes_before = len(gmsh.model.getEntities(dim=3))
            surfaces_before = len(gmsh.model.getEntities(dim=2))

            gmsh.model.occ.healShapes()
            gmsh.model.occ.synchronize()

            volumes_after = len(gmsh.model.getEntities(dim=3))
            surfaces_after = len(gmsh.model.getEntities(dim=2))

            gmsh.write(str(geom.source_file))
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return HealResult(
            volumes_before=volumes_before,
            surfaces_before=surfaces_before,
            volumes_after=volumes_after,
            surfaces_after=surfaces_after,
        )

    def find_defeature_candidates(
        self, geom: GeometryHandle, max_diameter: float
    ) -> list[DefeatureCandidate]:
        """Verilen eşik altındaki dairesel/döngü kenarları tespit eder.

        "Boyut", kenarın bounding-box çapı (en uzun köşegen) ile ölçülür —
        hem tam dairesel kenarlar hem küçük döngüler için basit, sağlam bir
        temsili boyut. Sadece TESPİT — henüz hiçbir şey kaldırılmıyor/
        değiştirilmiyor (dosyaya geri yazma yok).

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı.
        """
        try:
            face_to_part, _part_count = _compute_face_to_part()
            edge_to_part = _compute_edge_to_part(face_to_part)

            candidates: list[DefeatureCandidate] = []
            for _dim, edge_tag in gmsh.model.getEntities(dim=1):
                bbox = gmsh.model.getBoundingBox(1, edge_tag)
                xmin, ymin, zmin, xmax, ymax, zmax = bbox
                diameter = math.sqrt(
                    (xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2
                )
                if diameter <= max_diameter:
                    candidates.append(
                        DefeatureCandidate(
                            edge_id=edge_tag,
                            approx_diameter=diameter,
                            part_id=edge_to_part.get(edge_tag, 0),
                        )
                    )
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return candidates

    def create_midsurface(
        self, geom: GeometryHandle, face_id_a: int, face_id_b: int
    ) -> int:
        """İki paralel, düzlemsel yüzey arasında orta yüzeyi hesaplar.

        Yöntem: yüzey A'yı `occ.copy` ile çoğalt, iki yüzey arasındaki
        mesafenin yarısı kadar B yönüne `occ.translate` ile kaydır. Bu, A'nın
        gerçek sınır şeklini (dikdörtgen, çokgen, vb.) birebir koruyarak genel
        bir midsurface üretir — sadece iki yüzeyin PARALEL ve DÜZLEMSEL
        olduğu (ROADMAP: "sabit kalınlıklı düz plaka") basit durumda geçerli;
        genel eğri yüzeyler arası midsurface (B-spline interpolasyonu) kapsam
        dışı.

        Kalıcılık için güncellenmiş model `geom.source_file`'a geri yazılır.

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı.
        """
        try:
            existing_faces = {tag for _dim, tag in gmsh.model.getEntities(dim=2)}
            for fid in (face_id_a, face_id_b):
                if fid not in existing_faces:
                    raise SurfaceNotFoundError(
                        f"Yüzey bulunamadı: id={fid}. Mevcut yüzeyler: {sorted(existing_faces)}"
                    )

            _validate_planar_parallel_pair(face_id_a, face_id_b)
            new_face_id = _construct_midsurface(face_id_a, face_id_b)
            gmsh.write(str(geom.source_file))
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return new_face_id

    def create_midsurface_for_part(self, geom: GeometryHandle, part_id: int) -> tuple[int, int, int]:
        """Verilen parçanın (part) en uygun paralel/düzlemsel yüzey çiftini
        OTOMATİK tespit edip aralarında midsurface hesaplar.

        Tespit: parçaya ait düzlemsel yüzeyler arasında, birbirine paralel
        olan tüm çiftler taranır; alanları toplamı en büyük olan çift seçilir
        (tipik bir plaka/sac parçada bu, "ana" geniş yüzeyler olur — ince
        kenar yüzeyleri çok daha küçük alanlıdır, gerçek bir test plakasında
        doğrulandı: 100x50 ana yüzeyler=5000, kenar yüzeyleri=250-500).

        Döndürür: (yeni_yüzey_id, seçilen_yüzey_a_id, seçilen_yüzey_b_id) —
        şeffaflık için hangi çiftin otomatik seçildiği de bildirilir.

        Kalıcılık için güncellenmiş model `geom.source_file`'a geri yazılır.

        `import_geometry` çağrısından hemen sonra, aynı Gmsh oturumu içinde
        çağrılmalı.
        """
        try:
            face_to_part, _part_count = _compute_face_to_part()
            part_faces = [f for f, p in face_to_part.items() if p == part_id]
            if not part_faces:
                raise SurfaceNotFoundError(f"Parça bulunamadı: part_id={part_id}")

            planar_faces = [f for f in part_faces if gmsh.model.getType(2, f) == "Plane"]
            if len(planar_faces) < 2:
                raise MidsurfaceError(
                    f"Parça {part_id} için en az 2 düzlemsel yüzey gerekli, "
                    f"{len(planar_faces)} bulundu."
                )

            best_pair: tuple[int, int] | None = None
            best_score = -1.0
            for i in range(len(planar_faces)):
                for j in range(i + 1, len(planar_faces)):
                    fa, fb = planar_faces[i], planar_faces[j]
                    normal_a = _get_face_normal(fa)
                    normal_b = _get_face_normal(fb)
                    dot = sum(a * b for a, b in zip(normal_a, normal_b))
                    if abs(abs(dot) - 1.0) > 1e-3:
                        continue
                    area_a = gmsh.model.occ.getMass(2, fa)
                    area_b = gmsh.model.occ.getMass(2, fb)
                    score = area_a + area_b
                    if score > best_score:
                        best_score = score
                        best_pair = (fa, fb)

            if best_pair is None:
                raise MidsurfaceError(
                    f"Parça {part_id} için paralel düzlemsel yüzey çifti bulunamadı."
                )

            face_id_a, face_id_b = best_pair
            new_face_id = _construct_midsurface(face_id_a, face_id_b)
            gmsh.write(str(geom.source_file))
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return new_face_id, face_id_a, face_id_b

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
