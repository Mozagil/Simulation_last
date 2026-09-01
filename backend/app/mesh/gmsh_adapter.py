"""Gmsh tabanlı MesherAdapter implementasyonu.

Bu adımda STEP/IGES import + STL tessellation (web önizleme) + her üçgenin
hangi Gmsh yüzeyine (face) ait olduğunu veren `triangle_to_face` eşlemesi var.

STL dosyasını Gmsh'in kendi `gmsh.write()` fonksiyonuna bırakmak yerine
üçgenleri kendimiz üretip STL'i kendimiz yazıyoruz — böylece üçgen sırası
garantili biliniyor, `triangle_to_face` eşlemesi Gmsh'in dahili yazıcısının
üçgenleri nasıl sıraladığına bel bağlamıyor.

Gerçek FEA mesh üretimi (`generate_mesh`): 2D shell / 3D tet + wireframe
önizleme JSON (viewer).
"""

import json
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
    MeshError,
    MeshParams,
    MeshQualityMetric,
    MeshQualityResult,
    MeshResult,
    MesherAdapter,
    PointInfo,
    SurfaceInfo,
    TessellationResult,
)

# Gmsh eleman tipi kodu: 3 düğümlü üçgen (bkz. Gmsh dokümantasyonu, "elementType").
_TRIANGLE_ELEMENT_TYPE = 2
_TETRAHEDRON_ELEMENT_TYPE = 4

# İnsan-okur Gmsh eleman tipi adları (getElementType name)
_GMSH_ELEMENT_TYPE_NAMES = {
    1: "Line",
    2: "Triangle",
    3: "Quad",
    4: "Tetrahedron",
    5: "Hexahedron",
    6: "Prism",
    7: "Pyramid",
}
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


def _face_vertex_keys(face_tag: int, decimals: int = 4) -> set[tuple[float, float, float]]:
    """Yüzeyin köşe koordinatları (yuvarlanmış) — kenar tag'i paylaşmayan mid'ler için."""
    keys: set[tuple[float, float, float]] = set()
    try:
        boundary = gmsh.model.getBoundary(
            [(2, face_tag)], oriented=False, recursive=True
        )
    except Exception:
        return keys
    for bdim, btag in boundary:
        if bdim != 0:
            continue
        try:
            bb = gmsh.model.getBoundingBox(0, int(btag))
        except Exception:
            continue
        keys.add(
            (
                round(float(bb[0]), decimals),
                round(float(bb[1]), decimals),
                round(float(bb[2]), decimals),
            )
        )
    return keys


def _merge_orphan_faces_by_coincident_vertices(
    face_to_part: dict[int, int],
    orphan_faces: list[int],
    volume_backed_part_ids: set[int],
    next_part_id: int,
) -> int:
    """Köşesi çakışan orphan yüzeyleri aynı part_id'ye toplar."""
    if len(orphan_faces) < 2:
        return next_part_id
    parent: dict[int, int] = {}

    def find(a: int) -> int:
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    coord_to_pid: dict[tuple[float, float, float], int] = {}
    for face in orphan_faces:
        pid = face_to_part[face]
        if pid in volume_backed_part_ids:
            continue
        parent.setdefault(pid, pid)
        for key in _face_vertex_keys(face):
            existing = coord_to_pid.get(key)
            if existing is None:
                coord_to_pid[key] = pid
            else:
                union(pid, existing)

    orphan_pids = sorted(
        {face_to_part[f] for f in orphan_faces if face_to_part[f] not in volume_backed_part_ids}
    )
    roots: dict[int, int] = {}
    remap_start = min(orphan_pids) if orphan_pids else next_part_id
    n_new = 0
    for pid in orphan_pids:
        r = find(pid)
        if r not in roots:
            roots[r] = remap_start + n_new
            n_new += 1
    for face in orphan_faces:
        pid = face_to_part[face]
        if pid in volume_backed_part_ids:
            continue
        face_to_part[face] = roots[find(pid)]
    return remap_start + n_new


def _compute_face_to_part() -> tuple[dict[int, int], int, set[int]]:
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

    Üçüncü dönüş değeri: `volume_backed_part_ids` — GERÇEK bir 3B katıya
    (volume) karşılık gelen part_id'lerin kümesi. Aşama 2'de üretilen
    "orphan" part_id'ler (örn. `copy_surface`/`midsurface` çıktısı düz bir
    yüzey) bu kümede YOK — çünkü bunlar gerçek bir solid değil, sadece
    bağımsız bir yüzey parçası. "Solid gizle/göster" gibi işlemler sadece
    gerçek solid'leri hedeflemeli, düz yüzeyleri değil.
    """
    face_to_part: dict[int, int] = {}
    next_part_id = 0
    volume_backed_part_ids: set[int] = set()

    volumes = gmsh.model.getEntities(dim=3)
    for _dim, volume_tag in volumes:
        boundary = gmsh.model.getBoundary([(3, volume_tag)], oriented=False)
        for b_dim, b_tag in boundary:
            if b_dim == 2:
                face_to_part[b_tag] = next_part_id
        volume_backed_part_ids.add(next_part_id)
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

    # Midsurface dikdörtgenleri CAD kenar tag'i paylaşmaz; köşede çakışan
    # vertex ile aynı orphan parçaya al (Parça / Attached tek cidarda kalmasın).
    next_part_id = _merge_orphan_faces_by_coincident_vertices(
        face_to_part, orphan_faces, volume_backed_part_ids, next_part_id
    )

    part_count = max(next_part_id, 1)
    return face_to_part, part_count, volume_backed_part_ids


def _surface_parts_by_coincident_nodes(decimals: int = 5) -> dict[int, int]:
    """2D kabuk: çakışan düğüm koordinatı paylaşan yüzeyler aynı PART.

    Midsurface yüzleri CAD kenar tag'i paylaşmaz. Gmsh `getNodes(2, tag)`
    sınır eğrilerindeki düğümleri vermez — eleman bağlantısı kullanılır.
    """
    entities = gmsh.model.getEntities(2)
    if not entities:
        return {}
    tags = [int(t) for _d, t in entities]
    n = len(tags)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    node_tags, coords, _p = gmsh.model.mesh.getNodes()
    tag_to_coord: dict[int, tuple[float, float, float]] = {
        int(t): (
            round(float(coords[3 * i]), decimals),
            round(float(coords[3 * i + 1]), decimals),
            round(float(coords[3 * i + 2]), decimals),
        )
        for i, t in enumerate(node_tags)
    }

    coord_to_ents: dict[tuple[float, float, float], list[int]] = {}
    for i, tag in enumerate(tags):
        _etypes, _etags_list, enodes_list = gmsh.model.mesh.getElements(2, tag)
        seen: set[int] = set()
        for enodes in enodes_list:
            for nid in enodes:
                nid_i = int(nid)
                if nid_i in seen:
                    continue
                seen.add(nid_i)
                key = tag_to_coord.get(nid_i)
                if key is None:
                    continue
                coord_to_ents.setdefault(key, []).append(i)
    for ents in coord_to_ents.values():
        first = ents[0]
        for other in ents[1:]:
            union(first, other)

    roots: dict[int, int] = {}
    next_id = 0
    result: dict[int, int] = {}
    for i, tag in enumerate(tags):
        r = find(i)
        if r not in roots:
            roots[r] = next_id
            next_id += 1
        result[tag] = roots[r]
    return result


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


# İnce cidar eşiği: kalınlık / sqrt(min_yüzey_alanı). Düz plaka (5 / √5000 ≈ 0.07)
# ve kutu profil cidarı (2 / √3600 ≈ 0.03) geçer; katı küp karşı yüzleri
# (10 / √100 = 1.0) elenir.
_THIN_WALL_RATIO_MAX = 0.25


def _plane_separation(face_id_a: int, face_id_b: int) -> float:
    """İki paralel yüzey arasındaki mutlak düzlem mesafesi (kalınlık)."""
    normal_a = _get_face_normal(face_id_a)
    point_a = _get_face_point(face_id_a)
    point_b = _get_face_point(face_id_b)
    delta = tuple(point_b[i] - point_a[i] for i in range(3))
    return abs(sum(delta[i] * normal_a[i] for i in range(3)))


def _find_nearest_parallel_face(
    target_face: int, candidate_faces: list[int]
) -> tuple[int, float] | None:
    """`target_face`'e en yakın PARALEL düzlemsel yüzeyi (ve aralarındaki
    mesafeyi) bulur — `create_offset_midsurfaces`'in otomatik kalınlık
    tespiti için. `_find_thin_wall_pairs`'deki eşleştirme mantığıyla aynı,
    ama tek bir hedef yüzey için.
    """
    normal_a = _get_face_normal(target_face)
    best_face: int | None = None
    best_dist = float("inf")
    for face_b in candidate_faces:
        if face_b == target_face:
            continue
        normal_b = _get_face_normal(face_b)
        dot = sum(a * b for a, b in zip(normal_a, normal_b))
        if abs(abs(dot) - 1.0) > 1e-3:
            continue
        dist = _plane_separation(target_face, face_b)
        if dist < 1e-9 or dist >= best_dist:
            continue
        best_dist = dist
        best_face = face_b
    if best_face is None:
        return None
    return (best_face, best_dist)


def _find_thin_wall_pairs(planar_faces: list[int]) -> list[tuple[int, int]]:
    """Her düzlemsel yüzey için en yakın paralel eşi bulur; ince cidar
    oranını sağlayan benzersiz çiftleri döner.
    """
    pairs: list[tuple[int, int]] = []
    seen: set[frozenset[int]] = set()

    for face_a in planar_faces:
        normal_a = _get_face_normal(face_a)
        best_b: int | None = None
        best_dist = float("inf")

        for face_b in planar_faces:
            if face_b == face_a:
                continue
            normal_b = _get_face_normal(face_b)
            dot = sum(a * b for a, b in zip(normal_a, normal_b))
            if abs(abs(dot) - 1.0) > 1e-3:
                continue
            dist = _plane_separation(face_a, face_b)
            if dist < 1e-9 or dist >= best_dist:
                continue
            best_dist = dist
            best_b = face_b

        if best_b is None:
            continue

        key = frozenset((face_a, best_b))
        if key in seen:
            continue

        area_a = gmsh.model.occ.getMass(2, face_a)
        area_b = gmsh.model.occ.getMass(2, best_b)
        min_area = min(area_a, area_b)
        if min_area < 1e-12:
            continue
        if best_dist / math.sqrt(min_area) > _THIN_WALL_RATIO_MAX:
            continue

        seen.add(key)
        pairs.append((face_a, best_b))

    return pairs


def _coords_on_plane(
    fixed_axis: int, fixed_pos: float, a_axis: int, a: float, b_axis: int, b: float
) -> tuple[float, float, float]:
    """Sabit eksen + iki serbest eksen ile 3B nokta."""
    p = [0.0, 0.0, 0.0]
    p[fixed_axis] = fixed_pos
    p[a_axis] = a
    p[b_axis] = b
    return (p[0], p[1], p[2])


def _add_rectangle_on_fixed_axis(
    fixed_axis: int,
    fixed_pos: float,
    a_axis: int,
    a0: float,
    a1: float,
    b_axis: int,
    b0: float,
    b1: float,
) -> int:
    """Sabit düzlemde (fixed_axis=pos) a×b dikdörtgeni oluşturur."""
    c1 = _coords_on_plane(fixed_axis, fixed_pos, a_axis, a0, b_axis, b0)
    c2 = _coords_on_plane(fixed_axis, fixed_pos, a_axis, a1, b_axis, b0)
    c3 = _coords_on_plane(fixed_axis, fixed_pos, a_axis, a1, b_axis, b1)
    c4 = _coords_on_plane(fixed_axis, fixed_pos, a_axis, a0, b_axis, b1)
    p1 = gmsh.model.occ.addPoint(*c1)
    p2 = gmsh.model.occ.addPoint(*c2)
    p3 = gmsh.model.occ.addPoint(*c3)
    p4 = gmsh.model.occ.addPoint(*c4)
    l1 = gmsh.model.occ.addLine(p1, p2)
    l2 = gmsh.model.occ.addLine(p2, p3)
    l3 = gmsh.model.occ.addLine(p3, p4)
    l4 = gmsh.model.occ.addLine(p4, p1)
    loop = gmsh.model.occ.addCurveLoop([l1, l2, l3, l4])
    return gmsh.model.occ.addPlaneSurface([loop])


def _try_construct_connected_planar_midshell(
    wall_pairs: list[tuple[int, int]],
) -> list[tuple[int, int, int]] | None:
    """Eksenel ince cidarları köşede birleşen mid-shell olarak kurar.

    Destek: kutu (2+2 cidar), C/U kanal (1+2), L (1+1). Her cidarın kısa
    bbox ortalaması yerine komşu mid-düzlem kesişimlerine kadar uzatılır —
    fillet yüzleri atlanmış olsa bile gap kalmaz.
    """
    if len(wall_pairs) < 2:
        return None

    walls: list[dict[str, Any]] = []
    for face_a, face_b in wall_pairs:
        normal = _get_face_normal(face_a)
        axis = max(range(3), key=lambda i: abs(normal[i]))
        if abs(abs(normal[axis]) - 1.0) > 1e-6:
            return None
        ba = gmsh.model.getBoundingBox(2, face_a)
        bb = gmsh.model.getBoundingBox(2, face_b)
        mid_min = [(ba[i] + bb[i]) / 2 for i in range(3)]
        mid_max = [(ba[i + 3] + bb[i + 3]) / 2 for i in range(3)]
        pos = (mid_min[axis] + mid_max[axis]) / 2
        walls.append(
            {
                "axis": axis,
                "pos": pos,
                "pair": (face_a, face_b),
                "mid_min": mid_min,
                "mid_max": mid_max,
            }
        )

    return _construct_connected_planar_shell_from_walls(walls)


def _construct_connected_planar_shell_from_walls(
    walls: list[dict[str, Any]],
) -> list[tuple[int, int, int]] | None:
    """Wall dict listesinden köşede birleşen dikdörtgen mid/shell yüzeyleri kurar."""
    if len(walls) < 2:
        return None

    by_axis: dict[int, list[dict[str, Any]]] = {0: [], 1: [], 2: []}
    for w in walls:
        by_axis[int(w["axis"])].append(w)

    extrusion_axes = [ax for ax in range(3) if len(by_axis[ax]) == 0]
    wall_axes = [ax for ax in range(3) if len(by_axis[ax]) >= 1]
    if len(extrusion_axes) != 1 or len(wall_axes) != 2:
        return None

    ext = extrusion_axes[0]
    ax_u, ax_v = wall_axes[0], wall_axes[1]
    u_pos = sorted(w["pos"] for w in by_axis[ax_u])
    v_pos = sorted(w["pos"] for w in by_axis[ax_v])
    t0 = min(w["mid_min"][ext] for w in walls)
    t1 = max(w["mid_max"][ext] for w in walls)
    if abs(t1 - t0) < 1e-9:
        return None

    def _span_for_wall(
        wall: dict[str, Any], ortho_axis: int, ortho_positions: list[float]
    ) -> tuple[float, float] | None:
        lo = wall["mid_min"][ortho_axis]
        hi = wall["mid_max"][ortho_axis]
        if ortho_positions:
            lo = min(lo, min(ortho_positions))
            hi = max(hi, max(ortho_positions))
        if abs(hi - lo) < 1e-9:
            return None
        return lo, hi

    results: list[tuple[int, int, int]] = []
    for w in by_axis[ax_u]:
        span = _span_for_wall(w, ax_v, v_pos)
        if span is None:
            return None
        v0, v1 = span
        surf = _add_rectangle_on_fixed_axis(ax_u, w["pos"], ax_v, v0, v1, ext, t0, t1)
        pair = w.get("pair", (w.get("face", 0), w.get("face", 0)))
        results.append((surf, pair[0], pair[1]))
    for w in by_axis[ax_v]:
        span = _span_for_wall(w, ax_u, u_pos)
        if span is None:
            return None
        u0, u1 = span
        surf = _add_rectangle_on_fixed_axis(ax_v, w["pos"], ax_u, u0, u1, ext, t0, t1)
        pair = w.get("pair", (w.get("face", 0), w.get("face", 0)))
        results.append((surf, pair[0], pair[1]))

    gmsh.model.occ.synchronize()
    return results


def _orphan_face_ids(
    face_to_part: dict[int, int], volume_backed_part_ids: set[int]
) -> list[int]:
    """Solid'e bağlı olmayan (2D / midsurface) yüzey id'leri."""
    return [
        fid
        for fid, pid in face_to_part.items()
        if pid not in volume_backed_part_ids
    ]


def _wall_specs_from_orphan_planes(planar_faces: list[int]) -> list[dict[str, Any]] | None:
    """Orphan düzlemlerden eksenel cidar spec'leri (end-cap hariç)."""
    walls: list[dict[str, Any]] = []
    for face in planar_faces:
        normal = _get_face_normal(face)
        axis = max(range(3), key=lambda i: abs(normal[i]))
        if abs(abs(normal[axis]) - 1.0) > 1e-6:
            continue
        bb = gmsh.model.getBoundingBox(2, face)
        extents = [bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]]
        # Cidar: normal ekseninde ince; end-cap diğer iki yönde geniş ama
        # normal ekseni de "düz" — end-cap'te diğer iki extent büyük ve
        # extrusion doğrultusu normal'dir. Extrusion = en uzun bbox boyutu
        # olan eksenlerden, normal'in o olmadığı durumda cidar.
        sorted_ext = sorted((extents[i], i) for i in range(3))
        if sorted_ext[0][0] > 1e-4:
            continue
        # En uzun doğrultu extrusion adayı; cidar normali extrusion olmamalı
        longest_axis = sorted_ext[2][1]
        if axis == longest_axis:
            continue  # end-cap benzeri
        pos = (bb[axis] + bb[axis + 3]) / 2
        walls.append(
            {
                "axis": axis,
                "pos": pos,
                "pair": (face, face),
                "face": face,
                "mid_min": [bb[0], bb[1], bb[2]],
                "mid_max": [bb[3], bb[4], bb[5]],
            }
        )

    # Aynı (axis, pos) için tek temsilci
    dedup: dict[tuple[int, float], dict[str, Any]] = {}
    for w in walls:
        key = (int(w["axis"]), round(float(w["pos"]), 5))
        dedup[key] = w
    unique = list(dedup.values())
    if len(unique) < 2:
        return None
    return unique


def _try_defeature_orphan_midshell(max_radius: float) -> bool:
    """2D/midsurface kabuktaki fillet'leri kaldırıp keskin köşeli shell kurar.

    Solid (volume) yüzlerine dokunmaz. Orphan Cylinder/Sphere/Torus (r<=eşik)
    + orphan düz cidarlar varsa: eski orphan yüzeyler silinir, keskin bağlı
    dikdörtgen shell yazılır.
    """
    face_to_part, _part_count, volume_backed = _compute_face_to_part()
    orphans = _orphan_face_ids(face_to_part, volume_backed)
    if not orphans:
        return False

    volumes = gmsh.model.getEntities(dim=3)
    part_bbox = (
        gmsh.model.getBoundingBox(3, volumes[0][1])
        if volumes
        else gmsh.model.getBoundingBox(-1, -1)
    )

    orphan_fillets: list[int] = []
    orphan_planes: list[int] = []
    for fid in orphans:
        stype = gmsh.model.getType(2, fid)
        if stype == "Plane":
            orphan_planes.append(fid)
        elif stype in {"Cylinder", "Sphere", "Torus"}:
            if stype == "Cylinder" and _is_through_hole_cylinder(fid, part_bbox):
                continue
            radius = _approx_radius_of_blend_face(fid, stype)
            if radius is None or radius > max_radius + 1e-9:
                continue
            orphan_fillets.append(fid)

    if not orphan_fillets:
        return False

    return _rebuild_sharp_shell_removing(
        remove_face_ids=orphan_fillets + orphan_planes,
        plane_face_ids=orphan_planes,
    )


def _try_defeature_selected_faces(face_ids: list[int]) -> bool:
    """Seçilen 2D/midsurface yüzeylerini kaldırır; kalan düz cidarlardan keskin shell.

    Solid yüzeyi seçildiyse False (çağıran başka yola düşer).
    """
    if not face_ids:
        return False

    existing = {tag for _d, tag in gmsh.model.getEntities(dim=2)}
    missing = [fid for fid in face_ids if fid not in existing]
    if missing:
        raise RuntimeError(f"Seçilen yüzeyler bulunamadı: {missing}")

    face_to_part, _part_count, volume_backed = _compute_face_to_part()
    orphans = set(_orphan_face_ids(face_to_part, volume_backed))
    selected_orphans = [fid for fid in face_ids if fid in orphans]
    if not selected_orphans:
        return False

    orphan_planes = [
        fid for fid in orphans if gmsh.model.getType(2, fid) == "Plane"
    ]
    planes_for_spec = [fid for fid in orphan_planes if fid not in selected_orphans]
    if not planes_for_spec:
        planes_for_spec = [
            fid for fid in selected_orphans if gmsh.model.getType(2, fid) == "Plane"
        ]

    if planes_for_spec:
        remove_ids = list(dict.fromkeys(selected_orphans + planes_for_spec))
        return _rebuild_sharp_shell_removing(remove_ids, planes_for_spec)

    gmsh.model.occ.remove([(2, fid) for fid in selected_orphans], recursive=True)
    gmsh.model.occ.synchronize()
    return True


def _rebuild_sharp_shell_removing(
    remove_face_ids: list[int], plane_face_ids: list[int]
) -> bool:
    """Verilen düzlemlerden keskin shell kurmayı DENER (henüz hiçbir şey
    SİLMEDEN) — başarılı olursa eski duvarlar + seçilenler silinip yeni
    shell'le değiştirilir. Rebuild karmaşık profillerde (basit kutu/tüp
    kesiti olmayan) BAŞARISIZ olabilir — bu durumda GÜVENLİ BİR YEDEĞE
    düşülür: SADECE kullanıcının seçtiği (remove_face_ids) yüzeyler
    silinir, diğer düz duvarlara HİÇ DOKUNULMAZ (gerçek bir kullanım
    hatasında doğrulandı — önceden burada hem duvarlar siliniyor hem de
    hata fırlatılıyordu, bu da veri kaybına yol açıyordu; artık dosyaya
    hiçbir şey yazılmadan önce rebuild'in başarılı olacağından emin
    oluyoruz).
    """
    wall_specs = _wall_specs_from_orphan_planes(plane_face_ids)

    if wall_specs is not None:
        specs_snapshot = [
            {
                "axis": w["axis"],
                "pos": w["pos"],
                "pair": w["pair"],
                "face": w["face"],
                "mid_min": list(w["mid_min"]),
                "mid_max": list(w["mid_max"]),
            }
            for w in wall_specs
        ]
        # ÖNEMLİ: hiçbir şey silinmeden ÖNCE deniyoruz — yeni yüzeyler
        # sadece sayısal koordinatlardan (specs_snapshot) kuruluyor, eski
        # yüzey objelerine bağımlı değil, bu yüzden sırayı değiştirmek
        # güvenli.
        built = _construct_connected_planar_shell_from_walls(specs_snapshot)
        if built is not None:
            to_remove = list(dict.fromkeys(remove_face_ids + [w["face"] for w in wall_specs]))
            gmsh.model.occ.remove([(2, fid) for fid in to_remove], recursive=True)
            gmsh.model.occ.synchronize()
            return True

    # Rebuild mümkün değil (karmaşık/kesik profil) — GÜVENLİ YEDEK: sadece
    # kullanıcının seçtiği yüzeyleri sil, diğer düz duvarlara DOKUNMA.
    if not remove_face_ids:
        return False
    gmsh.model.occ.remove([(2, fid) for fid in remove_face_ids], recursive=True)
    gmsh.model.occ.synchronize()
    return True


def _construct_midsurface_from_averaged_bbox(face_id_a: int, face_id_b: int) -> int | None:
    """Eksenel hizalı yüzeyler için bbox ortalamasıyla orta dikdörtgen oluşturur.

    Kutu profilde dış 40 + iç 36 → mid 38 (kullanıcı örneği 40×40×2 mm).
    Eksenel hizalı değilse None döner (çağıran copy+translate'e düşer).
    """
    ba = gmsh.model.getBoundingBox(2, face_id_a)
    bb = gmsh.model.getBoundingBox(2, face_id_b)
    xmin = (ba[0] + bb[0]) / 2
    ymin = (ba[1] + bb[1]) / 2
    zmin = (ba[2] + bb[2]) / 2
    xmax = (ba[3] + bb[3]) / 2
    ymax = (ba[4] + bb[4]) / 2
    zmax = (ba[5] + bb[5]) / 2

    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    flat_eps = 1e-6

    if dx <= flat_eps and dy > flat_eps and dz > flat_eps:
        x = (xmin + xmax) / 2
        p1 = gmsh.model.occ.addPoint(x, ymin, zmin)
        p2 = gmsh.model.occ.addPoint(x, ymax, zmin)
        p3 = gmsh.model.occ.addPoint(x, ymax, zmax)
        p4 = gmsh.model.occ.addPoint(x, ymin, zmax)
    elif dy <= flat_eps and dx > flat_eps and dz > flat_eps:
        y = (ymin + ymax) / 2
        p1 = gmsh.model.occ.addPoint(xmin, y, zmin)
        p2 = gmsh.model.occ.addPoint(xmax, y, zmin)
        p3 = gmsh.model.occ.addPoint(xmax, y, zmax)
        p4 = gmsh.model.occ.addPoint(xmin, y, zmax)
    elif dz <= flat_eps and dx > flat_eps and dy > flat_eps:
        z = (zmin + zmax) / 2
        p1 = gmsh.model.occ.addPoint(xmin, ymin, z)
        p2 = gmsh.model.occ.addPoint(xmax, ymin, z)
        p3 = gmsh.model.occ.addPoint(xmax, ymax, z)
        p4 = gmsh.model.occ.addPoint(xmin, ymax, z)
    else:
        return None

    l1 = gmsh.model.occ.addLine(p1, p2)
    l2 = gmsh.model.occ.addLine(p2, p3)
    l3 = gmsh.model.occ.addLine(p3, p4)
    l4 = gmsh.model.occ.addLine(p4, p1)
    loop = gmsh.model.occ.addCurveLoop([l1, l2, l3, l4])
    surf = gmsh.model.occ.addPlaneSurface([loop])
    gmsh.model.occ.synchronize()
    return surf


def _construct_midsurface(face_id_a: int, face_id_b: int) -> int:
    """İki yüzey arasında midsurface üretir.

    Önce eksenel hizalı bbox ortalaması dener (kutu profilde doğru mid boyut:
    dış/iç ortalama). Olmazsa A'yı kopyalayıp B yönünde yarı mesafe kaydırır
    (eşit boyutlu plaka yüzleri). Çağrıdan önce `_validate_planar_parallel_pair`
    ile doğrulama yapılmış olmalı.
    """
    averaged = _construct_midsurface_from_averaged_bbox(face_id_a, face_id_b)
    if averaged is not None:
        return averaged

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




def _cylinder_radius_and_axis(face_tag: int) -> tuple[float, int, tuple[float, float, float], float, float]:
    """Silindir yüzünden (r, axis_index, axis_point, t0, t1) kestirimi.

    Çeyrek fillet bbox'u r×r×L; tam delik cidarı D×D×h. Mass ile ayırt edilir.
    """
    bb = gmsh.model.getBoundingBox(2, face_tag)
    extents = [
        (bb[3] - bb[0], 0),
        (bb[4] - bb[1], 1),
        (bb[5] - bb[2], 2),
    ]
    extents.sort(key=lambda item: item[0], reverse=True)
    axis_len, axis_i = extents[0]
    cross_a, cross_b = extents[1][0], extents[2][0]
    cross = (cross_a + cross_b) / 2.0
    mass = gmsh.model.occ.getMass(2, face_tag)
    r_quarter = cross
    r_full = cross / 2.0
    err_q = abs(mass - 0.5 * math.pi * r_quarter * axis_len)
    err_f = abs(mass - 2.0 * math.pi * r_full * axis_len)
    radius = r_quarter if err_q <= err_f else r_full

    pt = _get_face_point(face_tag)
    normal = _get_face_normal(face_tag)
    # Eksen noktası: yüzey noktasından radyal içeri/dışarı — iki adaydan
    # bbox merkezine daha yakın olan (fillet için genelde tutarlı).
    c_minus = tuple(pt[i] - normal[i] * radius for i in range(3))
    c_plus = tuple(pt[i] + normal[i] * radius for i in range(3))
    bb_mid = ((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2)

    def _dist2(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return sum((a[i] - b[i]) ** 2 for i in range(3))

    axis_pt = c_minus if _dist2(c_minus, bb_mid) < _dist2(c_plus, bb_mid) else c_plus
    t0 = bb[axis_i]
    t1 = bb[axis_i + 3]
    return radius, axis_i, axis_pt, t0, t1


def _find_thin_cylinder_pairs(cylinder_faces: list[int]) -> list[tuple[int, int]]:
    """İnce cidar oluşturan eş fillet silindir çiftlerini bulur (dış↔iç).

    İki yaygın durum:
    - Eşmerkezli farklı R (dış R = iç R + kalınlık): eksenler çakışır, |ra−rb| = t.
    - Kayık eş R (sac köşe: iç/dış R aynı, merkezler diyagonal kaymış):
      merkez mesafesi ≈ t√2; eski kod bunu eliyordu → köşe mid'i çıkmıyordu.
    """
    pairs: list[tuple[int, int]] = []
    seen: set[frozenset[int]] = set()
    frames = {f: _cylinder_radius_and_axis(f) for f in cylinder_faces}

    for fa in cylinder_faces:
        ra, ax_a, ca, t0a, t1a = frames[fa]
        best_b: int | None = None
        best_score = float("inf")
        for fb in cylinder_faces:
            if fb == fa:
                continue
            rb, ax_b, cb, t0b, t1b = frames[fb]
            if ax_a != ax_b:
                continue
            dist_centers = math.sqrt(
                sum((ca[i] - cb[i]) ** 2 for i in range(3) if i != ax_a)
            )
            r_max = max(ra, rb)
            radial_gap = abs(ra - rb)

            if dist_centers <= r_max * 0.35:
                # Eşmerkezli (veya neredeyse): kalınlık = yarıçap farkı
                if radial_gap < 1e-9:
                    continue
                thickness = radial_gap
            else:
                # Kayık eş-R fillet: aynı köşede, merkezler t√2 kadar ayrı
                if dist_centers > r_max * 2.5:
                    continue
                if radial_gap / max(r_max, 1e-12) > 0.25:
                    continue
                thickness = dist_centers / math.sqrt(2.0)

            area = 0.5 * math.pi * min(ra, rb) * min(t1a - t0a, t1b - t0b)
            if area < 1e-12:
                continue
            if thickness / math.sqrt(area) > _THIN_WALL_RATIO_MAX:
                continue
            if thickness < best_score:
                best_score = thickness
                best_b = fb
        if best_b is None:
            continue
        key = frozenset((fa, best_b))
        if key in seen:
            continue
        seen.add(key)
        pairs.append((fa, best_b))
    return pairs


def _construct_cylinder_midsurface(face_id_a: int, face_id_b: int) -> int:
    """İki eş fillet silindiri arasında orta yarıçaplı çeyrek-silindir yüzey."""
    ra, ax, ca, t0a, t1a = _cylinder_radius_and_axis(face_id_a)
    rb, ax_b, cb, t0b, t1b = _cylinder_radius_and_axis(face_id_b)
    if ax != ax_b:
        raise MidsurfaceError("Fillet silindir eksenleri paralel değil.")
    r_mid = (ra + rb) / 2.0
    # Ortak eksen noktası / aralık
    cx = tuple((ca[i] + cb[i]) / 2 for i in range(3))
    t0, t1 = min(t0a, t0b), max(t1a, t1b)
    height = t1 - t0
    if height < 1e-9 or r_mid < 1e-9:
        raise MidsurfaceError("Fillet midsurface için geçersiz boyut.")

    # addCylinder varsayılan çeyrek +X+Y; bbox ortasına göre döndür.
    bb_a = gmsh.model.getBoundingBox(2, face_id_a)
    bb_b = gmsh.model.getBoundingBox(2, face_id_b)
    mx = ((bb_a[0] + bb_a[3]) / 2 + (bb_b[0] + bb_b[3]) / 2) / 2
    my = ((bb_a[1] + bb_a[4]) / 2 + (bb_b[1] + bb_b[4]) / 2) / 2
    mz = ((bb_a[2] + bb_a[5]) / 2 + (bb_b[2] + bb_b[5]) / 2) / 2

    if ax == 2:
        origin = (cx[0], cx[1], t0)
        direction = (0.0, 0.0, height)
        rot_axis = (0.0, 0.0, 1.0)
        sector_dir = math.atan2(my - cx[1], mx - cx[0])
    elif ax == 1:
        origin = (cx[0], t0, cx[2])
        direction = (0.0, height, 0.0)
        rot_axis = (0.0, 1.0, 0.0)
        sector_dir = math.atan2(mx - cx[0], mz - cx[2])
    else:
        origin = (t0, cx[1], cx[2])
        direction = (height, 0.0, 0.0)
        rot_axis = (1.0, 0.0, 0.0)
        sector_dir = math.atan2(mz - cx[2], my - cx[1])

    existing_faces = {t for _d, t in gmsh.model.getEntities(dim=2)}

    vol = gmsh.model.occ.addCylinder(
        origin[0],
        origin[1],
        origin[2],
        direction[0],
        direction[1],
        direction[2],
        r_mid,
        angle=math.pi / 2,
    )
    gmsh.model.occ.synchronize()
    rot = sector_dir - (math.pi / 4)
    if abs(rot) > 1e-9:
        gmsh.model.occ.rotate([(3, vol)], cx[0], cx[1], cx[2], *rot_axis, rot)
        gmsh.model.occ.synchronize()

    # Volume'u sil ama sınır yüzlerini bırak; kapak düzlemlerini temizle —
    # böylece çeyrek-silindir yüzeyi STEP'e yazılabilir kalır.
    gmsh.model.occ.remove([(3, vol)], recursive=False)
    gmsh.model.occ.synchronize()
    new_faces = [
        t for _d, t in gmsh.model.getEntities(dim=2) if t not in existing_faces
    ]
    planar_caps = [(2, t) for t in new_faces if gmsh.model.getType(2, t) == "Plane"]
    if planar_caps:
        gmsh.model.occ.remove(planar_caps, recursive=True)
        gmsh.model.occ.synchronize()
    cyl_new = [
        t
        for _d, t in gmsh.model.getEntities(dim=2)
        if t not in existing_faces and gmsh.model.getType(2, t) == "Cylinder"
    ]
    if not cyl_new:
        raise MidsurfaceError("Fillet midsurface yüzeyi oluşturulamadı.")
    return cyl_new[0]
def _cylinder_plug_params(face_tag: int) -> tuple[float, float, float, float, float, float, float] | None:
    """Silindir yüzünden (axis-aligned) plug parametreleri: x,y,z, dx,dy,dz, radius.

    addCylinder(x,y,z, dx,dy,dz, r) ile uyumlu. Eksen, bbox'un en uzun kenarı.
    """
    bb = gmsh.model.getBoundingBox(2, face_tag)
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    extents = [
        (xmax - xmin, 0),
        (ymax - ymin, 1),
        (zmax - zmin, 2),
    ]
    extents.sort(key=lambda item: item[0], reverse=True)
    axis_len, axis_i = extents[0]
    d1, d2 = extents[1][0], extents[2][0]
    if axis_len < 1e-9 or d1 < 1e-9 or d2 < 1e-9:
        return None
    # Dairesel kesit: diğer iki bbox boyutu yaklaşık eşit (çap).
    if abs(d1 - d2) / max(d1, d2) > 0.25:
        return None
    radius = (d1 + d2) / 4.0
    cx, cy, cz = (xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2
    if axis_i == 0:
        return (xmin, cy, cz, axis_len, 0.0, 0.0, radius)
    if axis_i == 1:
        return (cx, ymin, cz, 0.0, axis_len, 0.0, radius)
    return (cx, cy, zmin, 0.0, 0.0, axis_len, radius)


def _fill_cylindrical_holes() -> int:
    """Silindirik delikleri solid plug + boolean fuse ile kapatır.

    Kutu profil gibi düzlem cidarlı boşluklara dokunmaz (Cylinder yüzeyi yok).
    Döner: kapatılan delik (silindir yüzü) sayısı.
    """
    if not gmsh.model.getEntities(dim=3):
        return 0

    filled = 0
    radial_eps = 1e-3
    # Fuse yüz etiketlerini değiştirdiği için her adımda yeniden tara.
    while filled < 64:
        cylinders = [
            tag
            for _dim, tag in gmsh.model.getEntities(dim=2)
            if gmsh.model.getType(2, tag) == "Cylinder"
        ]
        if not cylinders:
            break

        face_tag = cylinders[0]
        params = _cylinder_plug_params(face_tag)
        if params is None:
            # Bu yüzeyi atlamak için tipini bozamayız; çık (sonsuz döngü riski).
            break

        x, y, z, dx, dy, dz, radius = params
        vols_now = gmsh.model.getEntities(dim=3)
        if not vols_now:
            break
        plug = gmsh.model.occ.addCylinder(x, y, z, dx, dy, dz, radius + radial_eps)
        gmsh.model.occ.fuse(vols_now, [(3, plug)], removeObject=True, removeTool=True)
        gmsh.model.occ.synchronize()
        filled += 1

    return filled



def _approx_radius_of_blend_face(face_tag: int, surface_type: str) -> float | None:
    """Cylinder / Sphere / Torus yüzeyi için yaklaşık fillet yarıçapı."""
    if surface_type == "Cylinder":
        # Çeyrek fillet bbox'u r×r×L → (r+r)/4 yanıltıcı; mass tabanlı kestirim.
        radius, _ax, _pt, _t0, _t1 = _cylinder_radius_and_axis(face_tag)
        return radius
    bb = gmsh.model.getBoundingBox(2, face_tag)
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    if surface_type == "Sphere":
        return max(dx, dy, dz) / 2.0
    if surface_type == "Torus":
        return min(dx, dy, dz) / 2.0
    return None


def _is_through_hole_cylinder(face_tag: int, part_bbox: tuple[float, ...]) -> bool:
    """Silindir, cidarı delen delik mi (eksen boyunca fillet değil mi)?

    Fillet: eksen parçanın uzun kenarı kadar (profil boyu).
    Delik: eksen cidar kalınlığı kadar kısa — kutu profilde bbox'un en kısa
    kenarı profil genişliği (40 mm) olduğu için eski 'axis ≈ min(bbox)'
    karşılaştırması deliği fillet sanıyordu.
    """
    bb = gmsh.model.getBoundingBox(2, face_tag)
    axis_len = max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])
    p_ext = [
        part_bbox[3] - part_bbox[0],
        part_bbox[4] - part_bbox[1],
        part_bbox[5] - part_bbox[2],
    ]
    longest = max(p_ext)
    if longest < 1e-9:
        return False
    return axis_len / longest < 0.25


def _filter_profile_wall_pairs(
    pairs: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Delik/uç kapak gibi küçük düzlem çiftlerini eler; asıl cidarlar kalır."""
    if len(pairs) <= 1:
        return pairs
    scored: list[tuple[float, int, int]] = []
    for face_a, face_b in pairs:
        area = min(
            gmsh.model.occ.getMass(2, face_a),
            gmsh.model.occ.getMass(2, face_b),
        )
        scored.append((area, face_a, face_b))
    max_area = max(item[0] for item in scored)
    if max_area < 1e-12:
        return pairs
    kept = [
        (face_a, face_b)
        for area, face_a, face_b in scored
        if area >= 0.2 * max_area
    ]
    return kept if kept else pairs


def _collect_fillet_faces(max_radius: float) -> list[tuple[int, float, str, int]]:
    """(face_id, radius, type, part_id) fillet adayları."""
    face_to_part, _part_count, _volume_backed = _compute_face_to_part()
    volumes = gmsh.model.getEntities(dim=3)
    if volumes:
        part_bbox = gmsh.model.getBoundingBox(3, volumes[0][1])
    else:
        part_bbox = gmsh.model.getBoundingBox(-1, -1)

    out: list[tuple[int, float, str, int]] = []
    for _dim, tag in gmsh.model.getEntities(dim=2):
        stype = gmsh.model.getType(2, tag)
        if stype not in {"Cylinder", "Sphere", "Torus"}:
            continue
        if stype == "Cylinder" and _is_through_hole_cylinder(tag, part_bbox):
            continue
        radius = _approx_radius_of_blend_face(tag, stype)
        if radius is None or radius > max_radius + 1e-9:
            continue
        out.append((tag, radius, stype, face_to_part.get(tag, 0)))
    return out


def _orphan_shell_face_tags() -> list[int]:
    """Solid hacmine bağlı olmayan yüzeyler (midsurface / saf shell).

    Volume yoksa tüm yüzeyler shell sayılır.
    """
    all_faces = [tag for _dim, tag in gmsh.model.getEntities(dim=2)]
    volumes = gmsh.model.getEntities(dim=3)
    if not volumes:
        return all_faces

    volume_faces: set[int] = set()
    for _dim, vol in volumes:
        for bdim, btag in gmsh.model.getBoundary(
            [(3, vol)], oriented=False, recursive=False
        ):
            if bdim == 2:
                volume_faces.add(btag)
    return [tag for tag in all_faces if tag not in volume_faces]


def _extract_mesh_wireframe_preview(dimension: int) -> dict[str, Any]:
    """Gmsh tarzı shaded+wireframe önizleme: nodes, faces (üçgenler), lines (eleman kenarları).

    - dimension=2: shell tri/quad — quad gölgeleme için 2 üçgene bölünür ama
      wireframe'de yalnız 4 kenar (köşegen çizilmez)
    - dimension=3: tet hacminin yalnız dış yüzey üçgenleri

    `triangle_to_element[i]`: FE eleman id (quad = iki üçgen aynı id).
    `triangle_to_face[i]`: Gmsh yüzey tag'i (Face grow).
    `triangle_to_part[i]`: CalculiX ELSET `PART_{n}` — 2D'de kenar paylaşan
    kabuk yüzeyler tek parça (`_compute_face_to_part`, Attached grow).
    """
    node_tags, coords, _param = gmsh.model.mesh.getNodes()
    tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}
    nodes = [
        [float(coords[3 * i]), float(coords[3 * i + 1]), float(coords[3 * i + 2])]
        for i in range(len(node_tags))
    ]

    faces: list[int] = []
    triangle_to_part: list[int] = []
    triangle_to_face: list[int] = []
    triangle_to_element: list[int] = []
    next_element_id = 0
    edge_set: set[tuple[int, int]] = set()

    def _add_edge(a: int, b: int) -> None:
        if a == b:
            return
        edge_set.add((a, b) if a < b else (b, a))

    def _add_tri_face(
        i0: int, i1: int, i2: int, part_id: int, face_id: int, element_id: int
    ) -> None:
        """Sadece shaded üçgen (kenar eklemez)."""
        faces.extend((i0, i1, i2))
        triangle_to_part.append(part_id)
        triangle_to_face.append(face_id)
        triangle_to_element.append(element_id)

    def _add_triangle_element(
        i0: int, i1: int, i2: int, part_id: int, face_id: int
    ) -> None:
        nonlocal next_element_id
        eid = next_element_id
        next_element_id += 1
        _add_tri_face(i0, i1, i2, part_id, face_id, eid)
        _add_edge(i0, i1)
        _add_edge(i1, i2)
        _add_edge(i2, i0)

    def _add_quad_element(
        i0: int, i1: int, i2: int, i3: int, part_id: int, face_id: int
    ) -> None:
        # Three.js Mesh üçgen ister → 2 üçgen; köşegen wireframe'e girmez
        nonlocal next_element_id
        eid = next_element_id
        next_element_id += 1
        _add_tri_face(i0, i1, i2, part_id, face_id, eid)
        _add_tri_face(i0, i2, i3, part_id, face_id, eid)
        _add_edge(i0, i1)
        _add_edge(i1, i2)
        _add_edge(i2, i3)
        _add_edge(i3, i0)

    def _emit_surface_elements(tag: int, part_id: int, face_id: int) -> None:
        etypes, etags_list, enodes_list = gmsh.model.mesh.getElements(
            dim=2, tag=tag
        )
        for etype, etags, enodes in zip(etypes, etags_list, enodes_list):
            n_elems = len(etags)
            if n_elems == 0:
                continue
            if int(etype) == _TRIANGLE_ELEMENT_TYPE:
                for e in range(n_elems):
                    i0 = tag_to_idx[int(enodes[e * 3])]
                    i1 = tag_to_idx[int(enodes[e * 3 + 1])]
                    i2 = tag_to_idx[int(enodes[e * 3 + 2])]
                    _add_triangle_element(i0, i1, i2, part_id, face_id)
            elif int(etype) == 3:
                for e in range(n_elems):
                    i0 = tag_to_idx[int(enodes[e * 4])]
                    i1 = tag_to_idx[int(enodes[e * 4 + 1])]
                    i2 = tag_to_idx[int(enodes[e * 4 + 2])]
                    i3 = tag_to_idx[int(enodes[e * 4 + 3])]
                    _add_quad_element(i0, i1, i2, i3, part_id, face_id)

    if dimension == 2:
        face_to_part = _surface_parts_by_coincident_nodes()
        entities = gmsh.model.getEntities(2)
        if entities:
            for _dim, tag in entities:
                part_id = face_to_part.get(tag, 0)
                _emit_surface_elements(tag, part_id, int(tag))
        else:
            _emit_surface_elements(-1, 0, 0)
    else:
        _tags, conn = gmsh.model.mesh.getElementsByType(_TETRAHEDRON_ELEMENT_TYPE)
        face_count: dict[tuple[int, int, int], int] = {}
        face_orient: dict[tuple[int, int, int], tuple[int, int, int]] = {}
        face_part: dict[tuple[int, int, int], int] = {}
        tet_faces = ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))
        volumes = gmsh.model.getEntities(3)
        volume_tets: list[tuple[int, list[int]]] = []
        if volumes:
            for part_id, (_dim, vtag) in enumerate(volumes):
                etypes, etags_list, enodes_list = gmsh.model.mesh.getElements(
                    dim=3, tag=vtag
                )
                for etype, etags, enodes in zip(etypes, etags_list, enodes_list):
                    if int(etype) != _TETRAHEDRON_ELEMENT_TYPE:
                        continue
                    for e in range(len(etags)):
                        idxs = [tag_to_idx[int(enodes[e * 4 + k])] for k in range(4)]
                        volume_tets.append((part_id, idxs))
        else:
            for e in range(len(_tags)):
                idxs = [tag_to_idx[int(conn[e * 4 + k])] for k in range(4)]
                volume_tets.append((0, idxs))

        for part_id, idxs in volume_tets:
            for a, b, c in tet_faces:
                tri = (idxs[a], idxs[b], idxs[c])
                key = tuple(sorted(tri))
                face_count[key] = face_count.get(key, 0) + 1
                face_orient[key] = tri
                if key not in face_part:
                    face_part[key] = part_id
        for key, count in face_count.items():
            if count != 1:
                continue
            i0, i1, i2 = face_orient[key]
            _add_triangle_element(i0, i1, i2, face_part.get(key, 0), 0)

    lines: list[int] = []
    for a, b in edge_set:
        lines.append(a)
        lines.append(b)

    return {
        "nodes": nodes,
        "faces": faces,
        "lines": lines,
        "triangle_to_part": triangle_to_part,
        "triangle_to_face": triangle_to_face,
        "triangle_to_element": triangle_to_element,
    }


def _apply_curve_node_seeds(
    curve_nodes: dict[int, int],
    *,
    transfinite_surfaces: bool,
) -> None:
    """Kenar başına düğüm sayısı (transfinite curve). İsteğe bağlı yüzey.

    `nodes` uç noktalar dahil (Gmsh setTransfiniteCurve). 4 mm / 5 mm gibi
    global size değişince topoloji sıçramasını azaltır.
    """
    if not curve_nodes:
        return
    existing = {int(t) for _d, t in gmsh.model.getEntities(dim=1)}
    seeded: set[int] = set()
    for raw_tag, raw_n in curve_nodes.items():
        tag = int(raw_tag)
        n = int(raw_n)
        if tag not in existing or n < 2:
            continue
        gmsh.model.mesh.setTransfiniteCurve(tag, n)
        seeded.add(tag)
    if not transfinite_surfaces or not seeded:
        return
    for _d, ftag in gmsh.model.getEntities(dim=2):
        boundary = gmsh.model.getBoundary([(2, int(ftag))], oriented=False)
        curves = [int(t) for dim, t in boundary if dim == 1]
        if len(curves) in (3, 4) and curves and all(c in seeded for c in curves):
            gmsh.model.mesh.setTransfiniteSurface(int(ftag))


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
            # Önizleme tessellation: eğri yüzeylerde (fillet/radyus) daha sık
            # örnekleme — aksi halde STL'de radyuslar kaba üçgen "kabarcık"
            # gibi görünüyor. CAD geometrisi değişmez; sadece web preview.
            bbox = gmsh.model.getBoundingBox(-1, -1)
            diag = math.sqrt(
                (bbox[3] - bbox[0]) ** 2
                + (bbox[4] - bbox[1]) ** 2
                + (bbox[5] - bbox[2]) ** 2
            )
            if diag > 1e-9:
                gmsh.option.setNumber("Mesh.MeshSizeMax", diag / 15.0)
                gmsh.option.setNumber("Mesh.MeshSizeMin", diag / 200.0)
            # 2π radyan başına eleman sayısı — radyus/fillet pürüzsüzlüğü.
            gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 16)

            # Yüzey bazlı sorgulanabilir bir mesh üret (Gmsh'in otomatik STL
            # tessellation'ı yüzey bilgisini saklamıyor, bu yüzden kendi 2B
            # yüzey mesh algoritmasını çalıştırıyoruz).
            gmsh.model.mesh.generate(2)

            # Montaj (assembly) dosyalarında birden fazla ayrı katı (volume)
            # olabilir. Her katının sınır yüzeylerinden face_tag -> part_id
            # eşlemesi kur (part_id = sıradaki parça indeksi, 0'dan başlar).
            face_to_part, part_count, volume_backed_part_ids = _compute_face_to_part()

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
            volume_part_ids=sorted(volume_backed_part_ids),
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
            face_to_part, _part_count, _volume_backed = _compute_face_to_part()

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
            face_to_part, _part_count, _volume_backed = _compute_face_to_part()
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
            face_to_part, _part_count, _volume_backed = _compute_face_to_part()
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
        """Tolerans onarımı + silindirik yüzey deliklerini kapatma.

        1) `occ.healShapes` — küçük boşluk/tolerans.
        2) Cylinder yüzeyli delikleri solid plug + fuse ile doldurur.
           (Kutu profil boşluğu düzlem cidarlıdır; buna dokunulmaz.)

        Kalıcılık için güncellenmiş model `geom.source_file`'a geri yazılır.
        """
        try:
            volumes_before = len(gmsh.model.getEntities(dim=3))
            surfaces_before = len(gmsh.model.getEntities(dim=2))

            gmsh.model.occ.healShapes()
            gmsh.model.occ.synchronize()
            _fill_cylindrical_holes()

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
        self, geom: GeometryHandle, max_radius: float
    ) -> list[DefeatureCandidate]:
        """Yarıçapı eşik altındaki fillet yüzeylerini tespit eder (kaldırmadan)."""
        try:
            raw = _collect_fillet_faces(max_radius)
            candidates = [
                DefeatureCandidate(
                    face_id=fid,
                    approx_radius=radius,
                    surface_type=stype,
                    part_id=part_id,
                )
                for fid, radius, stype, part_id in raw
            ]
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return candidates

    def apply_defeature(
        self,
        geom: GeometryHandle,
        max_radius: float | None = None,
        face_ids: list[int] | None = None,
    ) -> HealResult:
        """Fillet/radyus kaldırıp keskin köşe üretir.

        - face_ids: seçilen 2D/midsurface yüzeyleri kaldır + kalan cidarlardan
          keskin shell.
        - max_radius: orphan fillet otomatik veya solid AABB.
        """
        try:
            volumes_before = len(gmsh.model.getEntities(dim=3))
            surfaces_before = len(gmsh.model.getEntities(dim=2))

            applied = False
            if face_ids:
                applied = _try_defeature_selected_faces(face_ids)
                if not applied:
                    raise RuntimeError(
                        "Seçilen yüzeyler 2D/midsurface kabuğuna ait değil. "
                        "Solid gizleyip radyus mid yüzeylerini seçin."
                    )
            elif max_radius is not None and max_radius > 0:
                if _try_defeature_orphan_midshell(max_radius):
                    applied = True
                else:
                    # GÜVENLİK: eskiden burada tüm model silinip bounding
                    # box'tan ibaret boş bir kutuyla DEĞİŞTİRİLİYORDU (veri
                    # kaybı riski). Artık geometriye hiç dokunmadan, anlaşılır
                    # bir hata fırlatıyoruz.
                    raise RuntimeError(
                        "Bu geometri için otomatik fillet kaldırma desteklenmiyor "
                        "(cidar düzeni tanınmadı). Geometri DEĞİŞTİRİLMEDİ. "
                        "Yüzey modunda ilgili radyus (mid) yüzeylerini elle seçip "
                        "face_ids ile tekrar deneyin."
                    )
            else:
                raise RuntimeError("face_ids veya max_radius gerekli.")

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

    def create_midsurface_for_part(
        self, geom: GeometryHandle, part_id: int
    ) -> list[tuple[int, int, int]]:
        """Parçadaki ince cidarlar için midsurface.

        Kapalı/açık profil (kutu, C, L) tanınırsa köşede birleşen düz kabuk
        üretilir — fillet silindirleri mid olarak yazılmaz (ayrı 'kanat'
        yüzeyler Attached seçimini tek yüzde bırakıyordu). Tanınmazsa ve
        fillet çifti varsa eski düz+silindir mid yoluna düşülür.
        """
        try:
            face_to_part, _part_count, _volume_backed = _compute_face_to_part()
            part_faces = [f for f, p in face_to_part.items() if p == part_id]
            if not part_faces:
                raise SurfaceNotFoundError(f"Parça bulunamadı: part_id={part_id}")

            planar_faces = [f for f in part_faces if gmsh.model.getType(2, f) == "Plane"]
            cylinder_faces = [
                f for f in part_faces if gmsh.model.getType(2, f) == "Cylinder"
            ]

            wall_pairs = _find_thin_wall_pairs(planar_faces) if len(planar_faces) >= 2 else []
            wall_pairs = _filter_profile_wall_pairs(wall_pairs)

            volumes = gmsh.model.getEntities(dim=3)
            if part_id < len(volumes):
                part_bbox = gmsh.model.getBoundingBox(3, volumes[part_id][1])
            elif volumes:
                part_bbox = gmsh.model.getBoundingBox(3, volumes[0][1])
            else:
                part_bbox = gmsh.model.getBoundingBox(-1, -1)
            fillet_faces = [
                f
                for f in cylinder_faces
                if not _is_through_hole_cylinder(f, part_bbox)
            ]
            cyl_pairs = _find_thin_cylinder_pairs(fillet_faces) if len(fillet_faces) >= 2 else []

            if not wall_pairs and not cyl_pairs:
                raise MidsurfaceError(
                    f"Parça {part_id} için ince cidar veya fillet çifti bulunamadı."
                )

            results: list[tuple[int, int, int]] = []
            # Kapalı düz kabuk varsa radyus mid üretme — uzun fillet silindirleri
            # ayrı "kanat" yüzeyleri olarak kalıyordu (Attached tek yüzde kalıyordu).
            connected = (
                _try_construct_connected_planar_midshell(wall_pairs)
                if wall_pairs
                else None
            )
            if connected is not None:
                results.extend(connected)
            elif cyl_pairs:
                for face_id_a, face_id_b in wall_pairs:
                    _validate_planar_parallel_pair(face_id_a, face_id_b)
                    new_face_id = _construct_midsurface(face_id_a, face_id_b)
                    results.append((new_face_id, face_id_a, face_id_b))
                for face_id_a, face_id_b in cyl_pairs:
                    new_face_id = _construct_cylinder_midsurface(face_id_a, face_id_b)
                    results.append((new_face_id, face_id_a, face_id_b))
            else:
                for face_id_a, face_id_b in wall_pairs:
                    _validate_planar_parallel_pair(face_id_a, face_id_b)
                    new_face_id = _construct_midsurface(face_id_a, face_id_b)
                    results.append((new_face_id, face_id_a, face_id_b))

            gmsh.write(str(geom.source_file))
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return results

    def copy_surfaces(self, geom: GeometryHandle, face_ids: list[int]) -> list[int]:
        """Verilen TÜM yüzeyleri tek bir mutasyonda çoğaltır (çoklu seçim
        desteği) — her biri `copy_surface` ile aynı mantıkla ama tek Gmsh
        oturumunda, tek `gmsh.write` ile. Yeni yüzey id'lerini, verilen
        sırayla döner.
        """
        try:
            existing_faces = {tag for _dim, tag in gmsh.model.getEntities(dim=2)}
            for fid in face_ids:
                if fid not in existing_faces:
                    raise SurfaceNotFoundError(
                        f"Yüzey bulunamadı: id={fid}. Mevcut yüzeyler: {sorted(existing_faces)}"
                    )
            if not face_ids:
                raise MidsurfaceError("En az bir yüzey seçilmeli.")

            new_ids: list[int] = []
            for face_id in face_ids:
                copied = gmsh.model.occ.copy([(2, face_id)])
                gmsh.model.occ.synchronize()
                if not copied or copied[0][0] != 2:
                    raise MidsurfaceError(
                        f"Yüzey kopyalanamadı: id={face_id} (beklenmeyen Gmsh yanıtı: {copied})"
                    )
                new_ids.append(copied[0][1])

            gmsh.write(str(geom.source_file))
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return new_ids

    def create_offset_midsurfaces(
        self,
        geom: GeometryHandle,
        face_ids: list[int],
        thickness: float | None = None,
        flip: bool = False,
    ) -> list[tuple[int, float]]:
        """Verilen her yüzeyi KENDİ normali boyunca, kalınlığın yarısı kadar
        İÇE (ya da `flip=True` ise DIŞA) doğru kaydırarak orta yüzeyini
        üretir (`_construct_midsurface`'in aksine iki yüzey eşleştirmeye
        gerek yok — kullanıcı doğrudan dış yüzeyleri seçer).

        Yön belirleme: varsayılan olarak VOLUME'ün kütle merkezine göre
        MATEMATİKSEL olarak İÇE doğru hesaplanır (gerçek verilerle
        doğrulandı). `flip=True` verilirse bu yön TERSİNE çevrilir —
        kullanıcı yönü kendisi kontrol edebilsin diye (bazı geometrilerde
        otomatik tespit beklenmeyen sonuç verebilir).

        `thickness=None` verilirse, HER yüzey için AYRI AYRI otomatik tespit
        edilir: o yüzeye en yakın PARALEL düzlemsel yüzey aranır (aynı
        mantık `_find_thin_wall_pairs`'de kullanılan), aralarındaki mesafe
        kalınlık olarak alınır. Bir yüzey için eş bulunamazsa hata fırlatılır
        (o yüzey için elle kalınlık girilmeli).

        NOT: Sadece DÜZLEMSEL yüzeyler için matematiksel olarak kesin bir
        sonuç verir (öteleme = gerçek ofset). Eğri (silindirik vb.)
        yüzeylerde bu sadece bir yaklaşıklıktır (gerçek eş-mesafeli ofset
        değil) — kapsam bilinçli olarak düz panellerle sınırlı tutuluyor
        (ROADMAP'in "sabit kalınlıklı düz plaka" senaryosuyla uyumlu).

        Döndürür: (yeni_yüzey_id, kullanılan_kalınlık) çiftlerinin listesi —
        otomatik tespit edilen kalınlık da şeffaf şekilde bildirilsin diye.

        Kalıcılık için güncellenmiş model `geom.source_file`'a geri yazılır.
        """
        try:
            existing_faces = {tag for _dim, tag in gmsh.model.getEntities(dim=2)}
            for fid in face_ids:
                if fid not in existing_faces:
                    raise SurfaceNotFoundError(
                        f"Yüzey bulunamadı: id={fid}. Mevcut yüzeyler: {sorted(existing_faces)}"
                    )
            if not face_ids:
                raise MidsurfaceError("En az bir yüzey seçilmeli.")
            if thickness is not None and thickness <= 0:
                raise MidsurfaceError("thickness pozitif olmalı.")

            for fid in face_ids:
                face_type = gmsh.model.getType(2, fid)
                if face_type != "Plane":
                    raise MidsurfaceError(
                        f"Yüzey {fid} düzlemsel değil ({face_type}) — kalınlık/2 "
                        f"kaydırma sadece düzlemsel yüzeyler için destekleniyor."
                    )

            # face_id -> hangi volume'e ait olduğunu bul (kütle merkezi referansı için).
            face_to_part, _pc, volume_backed = _compute_face_to_part()
            volumes = gmsh.model.getEntities(dim=3)
            part_to_volume_tag: dict[int, int] = {}
            for idx, (_dim, vtag) in enumerate(volumes):
                part_to_volume_tag[idx] = vtag

            all_planar_faces = [
                tag for _dim, tag in gmsh.model.getEntities(dim=2)
                if gmsh.model.getType(2, tag) == "Plane"
            ]

            results: list[tuple[int, float]] = []
            for face_id in face_ids:
                normal = _get_face_normal(face_id)
                point = _get_face_point(face_id)

                part_id = face_to_part.get(face_id)
                vol_tag = part_to_volume_tag.get(part_id) if part_id is not None else None
                inward = normal
                if vol_tag is not None:
                    vol_center = gmsh.model.occ.getCenterOfMass(3, vol_tag)
                    inward_vec = [vol_center[i] - point[i] for i in range(3)]
                    dot = sum(normal[i] * inward_vec[i] for i in range(3))
                    if dot < 0:
                        inward = tuple(-n for n in normal)
                if flip:
                    inward = tuple(-n for n in inward)

                if thickness is not None:
                    face_thickness = thickness
                else:
                    match = _find_nearest_parallel_face(face_id, all_planar_faces)
                    if match is None:
                        raise MidsurfaceError(
                            f"Yüzey {face_id} için otomatik kalınlık tespit edilemedi "
                            f"(paralel bir eş bulunamadı) — bu yüzey için elle kalınlık girin."
                        )
                    _matched_face, face_thickness = match

                offset = tuple(inward[i] * (face_thickness / 2) for i in range(3))

                copied = gmsh.model.occ.copy([(2, face_id)])
                gmsh.model.occ.synchronize()
                if not copied or copied[0][0] != 2:
                    raise MidsurfaceError(
                        f"Yüzey kopyalanamadı: id={face_id} (beklenmeyen Gmsh yanıtı: {copied})"
                    )
                new_face_id = copied[0][1]
                gmsh.model.occ.translate([(2, new_face_id)], *offset)
                gmsh.model.occ.synchronize()
                results.append((new_face_id, face_thickness))

            gmsh.write(str(geom.source_file))
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return results

    def generate_mesh(self, geom: GeometryHandle, params: MeshParams) -> MeshResult:
        """FEA mesh üretir: 3D solid veya 2D shell; scheme tet/quad/mix.

        Çıktı: `uploads/meshes/{stem}_d{2|3}.msh` (Gmsh MSH). Geometri STEP'i değişmez.
        """
        try:
            if params.element_size <= 0:
                raise MeshError("element_size pozitif olmalı.")
            if params.dimension not in (2, 3):
                raise MeshError("dimension 2 (shell) veya 3 (solid) olmalı.")
            scheme = (params.element_scheme or "tet").lower()
            if scheme not in ("tet", "quad", "mix"):
                raise MeshError("element_scheme tet, quad veya mix olmalı.")

            gmsh.option.setNumber("Mesh.MeshSizeMax", params.element_size)
            gmsh.option.setNumber("Mesh.MeshSizeMin", params.element_size)
            gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
            gmsh.option.setNumber("Mesh.RecombineAll", 0)
            gmsh.option.setNumber("Mesh.Recombine3DAll", 0)
            gmsh.option.setNumber("Mesh.SubdivisionAlgorithm", 0)

            _apply_curve_node_seeds(
                params.curve_nodes or {},
                transfinite_surfaces=(
                    params.dimension == 2 or scheme == "quad"
                ),
            )

            if params.dimension == 3:
                if not gmsh.model.getEntities(dim=3):
                    raise MeshError(
                        "3D tet mesh için solid (volume) gerekli. "
                        "Midsurface kabuğu için dimension=2 kullanın."
                    )
                if scheme == "quad":
                    # 3D'de quad karşılığı hex
                    gmsh.option.setNumber("Mesh.Recombine3DAll", 1)
                    gmsh.option.setNumber("Mesh.SubdivisionAlgorithm", 1)
                gmsh.model.mesh.generate(3)
            else:
                shell_faces = _orphan_shell_face_tags()
                if not shell_faces:
                    raise MeshError(
                        "2D shell mesh için midsurface (solid'a bağlı olmayan yüzey) "
                        "gerekli. Önce Midsurface oluşturun; aksi halde solid cidarlara "
                        "yüzey mesh'i atılır."
                    )
                volumes = gmsh.model.getEntities(dim=3)
                if volumes:
                    gmsh.model.occ.remove(volumes, recursive=True)
                    gmsh.model.occ.synchronize()
                remaining = {tag for _d, tag in gmsh.model.getEntities(dim=2)}
                if not remaining:
                    raise MeshError(
                        "2D shell mesh: solid kaldırıldıktan sonra shell yüzey kalmadı."
                    )
                if scheme == "quad":
                    gmsh.option.setNumber("Mesh.Algorithm", 8)
                    gmsh.option.setNumber("Mesh.RecombineAll", 1)
                    gmsh.model.mesh.generate(2)
                    gmsh.model.mesh.recombine()
                elif scheme == "mix":
                    gmsh.option.setNumber("Mesh.Algorithm", 6)
                    gmsh.option.setNumber("Mesh.RecombineAll", 0)
                    gmsh.model.mesh.generate(2)
                    gmsh.model.mesh.recombine()
                else:
                    # tet → shell'de üçgen
                    gmsh.option.setNumber("Mesh.Algorithm", 6)
                    gmsh.model.mesh.generate(2)

            node_tags, _coords, _ = gmsh.model.mesh.getNodes()
            node_count = len(node_tags)

            element_type_counts: dict[str, int] = {}
            element_count = 0
            for etype in gmsh.model.mesh.getElementTypes():
                elem_tags, _nodes = gmsh.model.mesh.getElementsByType(etype)
                n = len(elem_tags)
                if n == 0:
                    continue
                name = _GMSH_ELEMENT_TYPE_NAMES.get(int(etype), f"Type{etype}")
                element_type_counts[name] = element_type_counts.get(name, 0) + n
                if params.dimension == 2 and int(etype) in (_TRIANGLE_ELEMENT_TYPE, 3):
                    element_count += n
                elif params.dimension == 3 and int(etype) in (
                    _TETRAHEDRON_ELEMENT_TYPE,
                    5,
                    6,
                    7,
                ):
                    element_count += n

            if element_count == 0:
                element_count = sum(
                    c for name, c in element_type_counts.items() if name != "Line"
                )

            mesh_dir = geom.source_file.parent / "meshes"
            mesh_dir.mkdir(parents=True, exist_ok=True)
            mesh_path = mesh_dir / f"{geom.source_file.stem}_d{params.dimension}.msh"
            gmsh.write(str(mesh_path))

            preview = _extract_mesh_wireframe_preview(params.dimension)
            preview_path = mesh_dir / f"{geom.source_file.stem}_d{params.dimension}.preview.json"
            preview_path.write_text(
                json.dumps(preview, separators=(",", ":")), encoding="utf-8"
            )

            result = MeshResult(
                mesh_path=mesh_path,
                node_count=node_count,
                element_count=element_count,
                dimension=params.dimension,
                element_type_counts=element_type_counts,
                preview_path=preview_path,
                element_scheme=scheme,
            )
        finally:
            gmsh.finalize()
            _gmsh_lock.release()

        return result

    def compute_mesh_quality(
        self, mesh_path: Path, dimension: int
    ) -> MeshQualityResult:
        """Kayıtlı .msh için Jacobian (minSJ) + aspect ratio (maxEdge/minEdge).

        Gmsh native `getElementQualities` kullanır. Geometri STEP'ine dokunmaz.
        """
        if dimension not in (2, 3):
            raise MeshError("dimension 2 veya 3 olmalı.")
        if not mesh_path.exists():
            raise MeshError(f"Mesh dosyası yok: {mesh_path.name}")

        _gmsh_lock.acquire()
        gmsh.initialize(interruptible=False)
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.open(str(mesh_path))

            _types, tag_lists, _node_lists = gmsh.model.mesh.getElements(dim=dimension)
            element_tags: list[int] = []
            for tags in tag_lists:
                element_tags.extend(int(t) for t in tags)

            if not element_tags:
                raise MeshError(
                    f"Mesh'te dimension={dimension} eleman yok "
                    f"({mesh_path.name})."
                )

            jac_vals = list(
                gmsh.model.mesh.getElementQualities(element_tags, "minSJ")
            )
            min_edges = list(
                gmsh.model.mesh.getElementQualities(element_tags, "minEdge")
            )
            max_edges = list(
                gmsh.model.mesh.getElementQualities(element_tags, "maxEdge")
            )
            aspect_vals: list[float] = []
            for mn, mx in zip(min_edges, max_edges):
                if mn is None or mx is None or mn <= 1e-30:
                    aspect_vals.append(float("inf"))
                else:
                    aspect_vals.append(float(mx) / float(mn))

            def _metric(name: str, values: list[float]) -> MeshQualityMetric:
                finite = [v for v in values if v == v and abs(v) != float("inf")]
                if not finite:
                    raise MeshError(f"Kalite metriği boş: {name}")
                return MeshQualityMetric(
                    name=name,
                    min=min(finite),
                    max=max(finite),
                    mean=sum(finite) / len(finite),
                    values=[float(v) for v in values],
                )

            return MeshQualityResult(
                mesh_path=mesh_path,
                dimension=dimension,
                element_count=len(element_tags),
                element_tags=element_tags,
                jacobian=_metric("minSJ", jac_vals),
                aspect_ratio=_metric("aspect_ratio", aspect_vals),
            )
        except MeshError:
            raise
        except Exception as exc:
            raise MeshError(f"Mesh kalite hesaplanamadı: {exc}") from exc
        finally:
            gmsh.finalize()
            _gmsh_lock.release()


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
