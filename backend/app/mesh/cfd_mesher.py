"""CFD mesh — STEP geometri için sanal rüzgâr tüneli + snappyHexMesh (Faz 2.5a).

CFD mesh'i FEA mesh'inden ayrıdır: parçanın değil etrafındaki AKIŞKAN hacminin
sonlu hacim ağı. Akış:

1. STEP → Gmsh yüzey üçgenlemesi → ``constant/triSurface/body.stl`` (çok-katılı
   ASCII STL; her bölge ayrı ``solid`` → snappy'de ayrı yama → yama başına kuvvet).
   Birim: STEP mm, OpenFOAM m (×0.001). Açık kenar sayısı veri olarak döner
   (snappy kapalı yüzey ister; karar mühendisin).
2. Tünel: gövdenin sınır kutusundan, önde / arkada / yanlarda gövde boyunun
   katları (parametre) kadar kutu → ``blockMeshDict`` (taban hücre boyu
   mühendisten). Akış +x yönündedir; gövde buna göre yönlendirilmiş olmalı.
   Yamalar: ``inlet`` (x min), ``outlet`` (x max), ``sides`` (yanlar + üst,
   zemin yoksa alt da), ``ground`` (zemin seçiliyse alt, duvar).
3. ``surfaceFeatureExtractDict`` + ``snappyHexMeshDict`` (yüzey / kenar / iz
   bölgesi inceltmesi, sınır tabakası) + ``meshQualityDict`` (ESI varsayılanı).
4. Koşu sonrası ``checkMesh`` çıktısı veri olarak (``parse_check_mesh``).

Değerler mühendisindir; şema yalnız geçerliliği denetler. Varsayılanlar ESI
``motorBike`` öğreticisinden.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

BODY = "body"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: Tünel yamaları (gövde bölgeleri bu adları kullanamaz)
TUNNEL_PATCHES = ("inlet", "outlet", "sides", "ground")


class TunnelParams(BaseModel):
    """Gövde boyu L = sınır kutusunun x uzunluğu; mesafeler L'nin katı."""

    upstream: float = Field(3.0, gt=0, description="Girişe uzaklık (× L)")
    downstream: float = Field(6.0, gt=0, description="Çıkışa uzaklık (× L)")
    lateral: float = Field(3.0, gt=0, description="Yan ve üst duvarlara uzaklık (× L)")
    #: Zemin: tünel tabanı gövdenin en alt noktasından ``ground_clearance_m`` aşağıda
    #: duvar olur (araç). Kapalıysa alt da ``sides``.
    ground: bool = False
    ground_clearance_m: float = Field(0.0, ge=0)
    base_cell_m: float = Field(gt=0, description="Arka plan hücre boyu (m)")


class SnappyParams(BaseModel):
    """snappyHexMesh ayarları (inceltme seviyesi n → hücre = taban / 2ⁿ)."""

    surface_level_min: int = Field(2, ge=0, le=10)
    surface_level_max: int = Field(3, ge=0, le=10)
    feature_level: int = Field(3, ge=0, le=10)
    #: İz (wake) kutusu: gövde arkasında ``wake_length`` × L boyunca inceltme; 0 = yok.
    wake_level: int = Field(1, ge=0, le=10)
    wake_length: float = Field(2.0, gt=0)
    n_layers: int = Field(3, ge=0, le=50)
    expansion_ratio: float = Field(1.2, gt=0)
    #: relativeSizes: son katman kalınlığı / yerel hücre boyu
    final_layer_thickness: float = Field(0.3, gt=0)
    min_thickness: float = Field(0.1, gt=0)
    max_global_cells: int = Field(2_000_000, gt=0)
    n_cells_between_levels: int = Field(3, ge=1)
    feature_angle_deg: float = Field(150.0, gt=0, le=180)
    #: Gmsh yüzey üçgenlemesinin en büyük kenarı (mm, STEP birimi); boşsa Gmsh varsayılanı.
    stl_size_mm: float | None = Field(None, gt=0)

    @field_validator("surface_level_max")
    @classmethod
    def _levels(cls, v: int, info: Any) -> int:
        lo = info.data.get("surface_level_min", 0)
        if v < lo:
            raise ValueError("surface_level_max, surface_level_min'den küçük olamaz.")
        return v


@dataclass
class SurfaceExport:
    regions: list[str]
    #: (xmin, ymin, zmin, xmax, ymax, zmax) — metre
    bbox_m: tuple[float, float, float, float, float, float]
    triangles: int
    open_edges: int
    triangles_per_region: dict[str, int] = field(default_factory=dict)


# ----------------------------------------------------------------------------- STL


def export_surface_stl(
    cad_file: Path,
    out_stl: Path,
    regions: dict[str, list[int]] | None = None,
    size_mm: float | None = None,
    scale: float = 1e-3,
) -> SurfaceExport:
    """STEP yüzeylerini üçgenleyip çok-katılı ASCII STL yazar.

    ``regions``: bölge adı → yüzey (dim 2) etiketleri. Bölgeye girmeyen yüzeyler
    ``body`` bölgesine gider. Yüzey etiketleri uygulamanın açtığı sırayla aynıdır
    (FEA tarafıyla aynı import ayarı).
    """
    import gmsh

    from app.mesh.gmsh_adapter import _gmsh_lock

    regions = regions or {}
    for name in regions:
        if not _NAME.match(name) or name in TUNNEL_PATCHES:
            raise ValueError(f"Bölge adı '{name}' CFD yaması olamaz (harf/rakam/_, tünel adları hariç).")
    if not _gmsh_lock.acquire(timeout=180):
        raise RuntimeError("Gmsh kilidi alınamadı.")
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        if size_mm is not None:
            gmsh.option.setNumber("Mesh.MeshSizeMax", size_mm)
            gmsh.option.setNumber("Mesh.MeshSizeMin", size_mm / 10.0)
        # Önce dikişsiz (uygulamanın yüz numaraları); yüzey açık kalırsa
        # dikişli okuma denenir ve daha kapalı olan seçilir. Dikişli okuma
        # periyodik yüzeylerde (küre) mesh'lenemeyebiliyor — o zaman ilki kalır.
        xyz, tris = _mesh_surface(cad_file, regions, scale, sew=False)
        open_edges = _merge_and_count(xyz, tris)
        if open_edges > 0:
            try:
                xyz2, tris2 = _mesh_surface(cad_file, regions, scale, sew=True)
            except Exception:  # noqa: BLE001 — dikişli yol isteğe bağlı
                xyz2 = None
            if xyz2 is not None:
                open2 = _merge_and_count(xyz2, tris2)
                if open2 < open_edges:
                    xyz, tris, open_edges = xyz2, tris2, open2
    finally:
        gmsh.finalize()
        _gmsh_lock.release()

    out_stl.parent.mkdir(parents=True, exist_ok=True)
    pts = [xyz[n] for lst in tris.values() for tri in lst for n in tri]
    if not pts:
        raise ValueError("Geometriden yüzey üçgeni üretilemedi.")
    bbox = (
        min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts),
        max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts),
    )
    with out_stl.open("w", encoding="ascii", newline="\n") as fh:
        for name, lst in tris.items():
            fh.write(f"solid {name}\n")
            for a, b, c in lst:
                pa, pb, pc = xyz[a], xyz[b], xyz[c]
                u = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
                v = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
                n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
                ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
                fh.write(f"  facet normal {n[0] / ln:.6e} {n[1] / ln:.6e} {n[2] / ln:.6e}\n    outer loop\n")
                for p in (pa, pb, pc):
                    fh.write(f"      vertex {p[0]:.9e} {p[1]:.9e} {p[2]:.9e}\n")
                fh.write("    endloop\n  endfacet\n")
            fh.write(f"endsolid {name}\n")
    return SurfaceExport(
        regions=list(tris),
        bbox_m=bbox,  # type: ignore[arg-type]
        triangles=sum(len(v) for v in tris.values()),
        open_edges=open_edges,
        triangles_per_region={k: len(v) for k, v in tris.items()},
    )


def _mesh_surface(
    cad_file: Path, regions: dict[str, list[int]], scale: float, sew: bool
) -> tuple[dict[int, tuple[float, float, float]], dict[str, list[tuple[int, int, int]]]]:
    """Yüzey üçgenlemesi (gmsh oturumu açık): düğüm koordinatları (m) + bölge → üçgenler."""
    import gmsh

    gmsh.clear()
    if sew:
        face_region = _sewn_face_regions(cad_file, regions)
    else:
        gmsh.option.setNumber("Geometry.OCCSewFaces", 0)
        gmsh.model.add("cfd_surface")
        gmsh.open(str(cad_file))
        gmsh.model.occ.synchronize()
        face_region = {int(t): name for name, tags in regions.items() for t in tags}
    gmsh.model.mesh.generate(2)
    node_tags, coords, _ = gmsh.model.mesh.getNodes()
    xyz = {
        int(t): (float(coords[3 * i]) * scale, float(coords[3 * i + 1]) * scale, float(coords[3 * i + 2]) * scale)
        for i, t in enumerate(node_tags)
    }
    tris: dict[str, list[tuple[int, int, int]]] = {}
    for _, tag in gmsh.model.getEntities(2):
        name = face_region.get(int(tag), BODY)
        etypes, _, enodes = gmsh.model.mesh.getElements(2, tag)
        for et, nodes in zip(etypes, enodes):
            if int(et) != 2:  # yalnız 3 düğümlü üçgen
                continue
            lst = tris.setdefault(name, [])
            for k in range(0, len(nodes), 3):
                lst.append((int(nodes[k]), int(nodes[k + 1]), int(nodes[k + 2])))
    return xyz, tris


def _merge_and_count(
    xyz: dict[int, tuple[float, float, float]], tris: dict[str, list[tuple[int, int, int]]]
) -> int:
    """Aynı noktadaki ikiz düğümleri tek koordinata birleştirir (``xyz`` yerinde), açık kenar sayısını döner.

    Açık kenar KOORDİNATLA sayılır: Gmsh periyodik dikişlerde (döndürülmüş
    yüzeyler) ve dejenere uçlarda aynı noktaya ayrı düğüm koyar; düğüm
    numarasıyla sayınca kapalı yüzey açık görünüyordu (ölçüldü: roket 96).
    1e-13 m'lik farkla duran ikizler STL'ye farklı rakamlarla yazılıp yüzeyi
    açık bırakıyordu (ölçüldü: elips burun 42); 10 nm ızgarada birleştirilir.
    """
    grid = 1e-8
    canon: dict[tuple[int, int, int], tuple[float, float, float]] = {}
    cell_of: dict[int, tuple[int, int, int]] = {}
    for n, (x, y, z) in xyz.items():
        cell = (round(x / grid), round(y / grid), round(z / grid))
        xyz[n] = canon.setdefault(cell, (x, y, z))
        cell_of[n] = cell
    edges: dict[tuple[tuple[int, int, int], tuple[int, int, int]], int] = {}
    for lst in tris.values():
        for a, b, c in lst:
            for e0, e1 in ((a, b), (b, c), (c, a)):
                ka, kb = cell_of[e0], cell_of[e1]
                if ka == kb:
                    continue  # dejenere (uçta çökmüş) kenar
                key = (min(ka, kb), max(ka, kb))
                edges[key] = edges.get(key, 0) + 1
    return sum(1 for n in edges.values() if n == 1)


def _face_key(tag: int) -> tuple[float, ...]:
    import gmsh

    cx, cy, cz = gmsh.model.occ.getCenterOfMass(2, tag)
    return (round(cx, 3), round(cy, 3), round(cz, 3), round(gmsh.model.occ.getMass(2, tag), 3))


def _sewn_face_regions(cad_file: Path, regions: dict[str, list[int]]) -> dict[int, str]:
    """STEP'i DİKİŞLİ açar (gmsh oturumu açık) ve bölgeleri yeni yüz numaralarına taşır.

    Uygulama yüz numaralarını dikişsiz okumadan (OCCSewFaces=0) verir; ama
    dikişsiz okumada döndürülmüş kapalı yüzeylerin ortak çemberi çift eğri
    kalabiliyor ve yüzey açık mesh'leniyordu (ölçüldü: roket von Kármán +
    boat-tail'de 42 açık kenar; dikişli okumada 0). Bölgeler yüzlerin kütle
    merkezi + alanıyla eşlenir. Eşleme tam tutmazsa (dikiş yüzleri birleştirdiyse)
    hata verir; çağıran dikişsiz sonuçla kalır.
    """
    import gmsh

    gmsh.option.setNumber("Geometry.OCCSewFaces", 0)
    gmsh.model.add("cfd_surface_ref")
    gmsh.open(str(cad_file))
    gmsh.model.occ.synchronize()
    plain = {int(t): name for name, tags in regions.items() for t in tags}
    ref_faces = [int(t) for _, t in gmsh.model.getEntities(2)]
    key_region = {_face_key(t): plain.get(t, BODY) for t in ref_faces}

    gmsh.clear()
    gmsh.option.setNumber("Geometry.OCCSewFaces", 1)
    gmsh.model.add("cfd_surface")
    gmsh.open(str(cad_file))
    gmsh.model.occ.synchronize()
    gmsh.option.setNumber("Geometry.OCCSewFaces", 0)
    sewn = [int(t) for _, t in gmsh.model.getEntities(2)]
    mapped = {t: key_region.get(_face_key(t)) for t in sewn}
    if len(sewn) != len(ref_faces) or any(v is None for v in mapped.values()):
        raise ValueError("Dikişli okumada yüzler dikişsizle eşlenemedi.")
    return {t: v for t, v in mapped.items() if v is not None}


# --------------------------------------------------------------------------- tünel


def _n(x: float) -> str:
    return f"{x:.6g}"


def _vec(v: tuple[float, float, float] | list[float]) -> str:
    return f"({_n(v[0])} {_n(v[1])} {_n(v[2])})"


def _header(obj: str) -> str:
    return (
        "/*--------------------------------*- C++ -*----------------------------------*\\\n"
        "  SimSurrogate — CFD mesh (rüzgâr tüneli), otomatik üretildi\n"
        "\\*---------------------------------------------------------------------------*/\n"
        "FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
        f"    class       dictionary;\n    object      {obj};\n}}\n\n"
    )


@dataclass
class TunnelBox:
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]
    cells: tuple[int, int, int]
    body_length_m: float

    @property
    def background_cells(self) -> int:
        return self.cells[0] * self.cells[1] * self.cells[2]


def tunnel_box(bbox_m: tuple[float, ...], t: TunnelParams) -> TunnelBox:
    xmin, ymin, zmin, xmax, ymax, zmax = bbox_m
    length = max(xmax - xmin, 1e-12)
    lat = t.lateral * length
    lo = [xmin - t.upstream * length, ymin - lat, zmin - lat]
    hi = [xmax + t.downstream * length, ymax + lat, zmax + lat]
    if t.ground:
        lo[2] = zmin - t.ground_clearance_m
    cells = tuple(max(1, math.ceil((hi[i] - lo[i]) / t.base_cell_m)) for i in range(3))
    return TunnelBox(lo=tuple(lo), hi=tuple(hi), cells=cells, body_length_m=length)  # type: ignore[arg-type]


def tunnel_block_mesh_dict(box: TunnelBox, ground: bool) -> str:
    (x0, y0, z0), (x1, y1, z1) = box.lo, box.hi
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    vtxt = "\n".join(f"    {_vec(v)}" for v in verts)
    nx, ny, nz = box.cells
    bottom = "(0 3 2 1)"
    side_faces = "(0 1 5 4) (3 7 6 2) (4 5 6 7)" + ("" if ground else f" {bottom}")
    ground_block = f"    ground\n    {{\n        type wall;\n        faces ({bottom});\n    }}\n" if ground else ""
    return _header("blockMeshDict") + (
        "convertToMeters 1;\n\n"
        f"vertices\n(\n{vtxt}\n);\n\n"
        f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)\n);\n\n"
        "edges\n(\n);\n\n"
        "boundary\n(\n"
        "    inlet\n    {\n        type patch;\n        faces ((0 4 7 3));\n    }\n"
        "    outlet\n    {\n        type patch;\n        faces ((1 2 6 5));\n    }\n"
        f"    sides\n    {{\n        type patch;\n        faces ({side_faces});\n    }}\n"
        f"{ground_block}"
        ");\n\nmergePatchPairs\n(\n);\n"
    )


def surface_feature_extract_dict(p: SnappyParams) -> str:
    return _header("surfaceFeatureExtractDict") + (
        f"{BODY}.stl\n{{\n"
        "    extractionMethod    extractFromSurface;\n"
        f"    includedAngle       {_n(p.feature_angle_deg)};\n"
        "    subsetFeatures\n    {\n        nonManifoldEdges no;\n        openEdges        yes;\n    }\n"
        "    writeObj            no;\n}\n"
    )


def location_in_mesh(box: TunnelBox) -> tuple[float, float, float]:
    """Akışkan içinde, gövdeden uzak bir nokta (giriş köşesine yakın, yüz hizasında değil)."""
    return tuple(box.lo[i] + (box.hi[i] - box.lo[i]) * f for i, f in enumerate((0.0731, 0.1137, 0.1379)))  # type: ignore[return-value]


def snappy_dict(box: TunnelBox, bbox_m: tuple[float, ...], regions: list[str], p: SnappyParams) -> str:
    xmin, ymin, zmin, xmax, ymax, zmax = bbox_m
    region_block = "\n".join(f"            {r} {{ name {r}; }}" for r in regions)
    wake_geom = ""
    wake_ref = ""
    if p.wake_level > 0:
        pad = 0.25 * box.body_length_m
        wlo = (xmin - pad, ymin - pad, zmin - pad)
        whi = (xmax + p.wake_length * box.body_length_m, ymax + pad, zmax + pad)
        wake_geom = f"    wake\n    {{\n        type box;\n        min  {_vec(wlo)};\n        max  {_vec(whi)};\n    }}\n"
        wake_ref = f"        wake\n        {{\n            mode inside;\n            levels ((1E15 {p.wake_level}));\n        }}\n"
    layer_regex = "(" + "|".join(regions) + ")"
    return _header("snappyHexMeshDict") + (
        "castellatedMesh true;\nsnap            true;\n"
        f"addLayers       {'true' if p.n_layers > 0 else 'false'};\n\n"
        "geometry\n{\n"
        f"    {BODY}.stl\n    {{\n        type triSurfaceMesh;\n        name {BODY};\n"
        f"        regions\n        {{\n{region_block}\n        }}\n    }}\n"
        f"{wake_geom}"
        "}\n\n"
        "castellatedMeshControls\n{\n"
        "    maxLocalCells 1000000;\n"
        f"    maxGlobalCells {p.max_global_cells};\n"
        "    minRefinementCells 10;\n"
        "    maxLoadUnbalance 0.10;\n"
        f"    nCellsBetweenLevels {p.n_cells_between_levels};\n"
        f'    features\n    (\n        {{\n            file "{BODY}.eMesh";\n            level {p.feature_level};\n        }}\n    );\n'
        "    refinementSurfaces\n    {\n"
        f"        {BODY}\n        {{\n            level ({p.surface_level_min} {p.surface_level_max});\n"
        "            patchInfo\n            {\n                type wall;\n            }\n        }\n    }\n"
        "    resolveFeatureAngle 30;\n"
        f"    refinementRegions\n    {{\n{wake_ref}    }}\n"
        f"    locationInMesh {_vec(location_in_mesh(box))};\n"
        "    allowFreeStandingZoneFaces true;\n}\n\n"
        "snapControls\n{\n"
        "    nSmoothPatch 3;\n    tolerance 2.0;\n    nSolveIter 30;\n    nRelaxIter 5;\n"
        "    nFeatureSnapIter 10;\n    implicitFeatureSnap false;\n    explicitFeatureSnap true;\n"
        "    multiRegionFeatureSnap false;\n}\n\n"
        "addLayersControls\n{\n"
        "    relativeSizes true;\n"
        f'    layers\n    {{\n        "{layer_regex}"\n        {{\n            nSurfaceLayers {p.n_layers};\n        }}\n    }}\n'
        f"    expansionRatio {_n(p.expansion_ratio)};\n"
        f"    finalLayerThickness {_n(p.final_layer_thickness)};\n"
        f"    minThickness {_n(p.min_thickness)};\n"
        "    nGrow 0;\n    featureAngle 60;\n    slipFeatureAngle 30;\n    nRelaxIter 3;\n"
        "    nSmoothSurfaceNormals 1;\n    nSmoothNormals 3;\n    nSmoothThickness 10;\n"
        "    maxFaceThicknessRatio 0.5;\n    maxThicknessToMedialRatio 0.3;\n    minMedialAxisAngle 90;\n"
        "    nBufferCellsNoExtrude 0;\n    nLayerIter 50;\n}\n\n"
        'meshQualityControls\n{\n    #include "meshQualityDict"\n    nSmoothScale 4;\n    errorReduction 0.75;\n}\n\n'
        "mergeTolerance 1e-6;\n"
    )


def mesh_quality_dict() -> str:
    return _header("meshQualityDict") + '#includeEtc "caseDicts/mesh/generation/meshQualityDict.cfg"\n'


def tunnel_patches(regions: list[str], ground: bool) -> list[str]:
    """Snappy sonrası yamalar: tünel + gövde bölgeleri."""
    return ["inlet", "outlet", "sides", *(["ground"] if ground else []), *regions]


MESH_SCRIPT = (
    "set -o pipefail; "
    "blockMesh > log.blockMesh 2>&1 && "
    "surfaceFeatureExtract > log.surfaceFeatureExtract 2>&1 && "
    "snappyHexMesh -overwrite > log.snappyHexMesh 2>&1 && "
    "checkMesh -constant > log.checkMesh 2>&1; "
    "echo \"MESH_EXIT=$?\""
)


def write_tunnel_case(
    case_dir: Path,
    stl: SurfaceExport,
    tunnel: TunnelParams,
    snappy: SnappyParams,
) -> TunnelBox:
    """Mesh sözlüklerini case klasörüne yazar (STL ``constant/triSurface/body.stl`` hazır olmalı)."""
    box = tunnel_box(stl.bbox_m, tunnel)
    files = {
        "system/blockMeshDict": tunnel_block_mesh_dict(box, tunnel.ground),
        "system/surfaceFeatureExtractDict": surface_feature_extract_dict(snappy),
        "system/snappyHexMeshDict": snappy_dict(box, stl.bbox_m, stl.regions, snappy),
        "system/meshQualityDict": mesh_quality_dict(),
    }
    for rel, text in files.items():
        path = Path(case_dir) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return box


# ------------------------------------------------------------------------ checkMesh

_NUM = r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"


def parse_check_mesh(text: str) -> dict[str, Any]:
    """``checkMesh`` çıktısı → sayılar (veri; eşik yorumu yok)."""
    out: dict[str, Any] = {}
    for key in ("points", "faces", "internal faces", "cells"):
        m = re.search(rf"^\s*{key}:\s+(\d+)", text, re.M)
        if m:
            out[key.replace(" ", "_")] = int(m.group(1))
    m = re.search(rf"Mesh non-orthogonality Max:\s*{_NUM}\s+average:\s*{_NUM}", text)
    if m:
        out["non_orthogonality_max"] = float(m.group(1))
        out["non_orthogonality_avg"] = float(m.group(2))
    m = re.search(rf"Max skewness = {_NUM}", text)
    if m:
        out["skewness_max"] = float(m.group(1))
    m = re.search(rf"Max aspect ratio = {_NUM}", text)
    if m:
        out["aspect_ratio_max"] = float(m.group(1))
    m = re.search(rf"Minimum face area = {_NUM}", text)
    if m:
        out["min_face_area"] = float(m.group(1))
    m = re.search(rf"Min volume = {_NUM}\. Max volume = {_NUM}", text)
    if m:
        out["min_volume"] = float(m.group(1))
        out["max_volume"] = float(m.group(2))
    hexa = re.search(r"^\s*hexahedra:\s+(\d+)", text, re.M)
    poly = re.search(r"^\s*polyhedra:\s+(\d+)", text, re.M)
    if hexa:
        out["hexahedra"] = int(hexa.group(1))
    if poly:
        out["polyhedra"] = int(poly.group(1))
    failed = re.search(r"Failed (\d+) mesh checks", text)
    out["failed_checks"] = int(failed.group(1)) if failed else 0
    out["mesh_ok"] = "Mesh OK." in text
    patches = re.findall(r"^\s+(\w+)\s+(\d+)\s+(\d+)\s+ok \(", text, re.M)
    if patches:
        out["patch_faces"] = {name: int(faces) for name, faces, _ in patches}
    return out


_LAYER_ROW = re.compile(r"^(\w+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([-+\d.eE]+)\s+([\d.]+)\s*$")


def parse_snappy_log(text: str) -> dict[str, Any]:
    """``snappyHexMesh`` günlüğü → aşama hücre sayıları, seviye dağılımı, katman kapsaması (veri)."""
    out: dict[str, Any] = {}
    for key, label in (("background_cells", "Initial mesh"), ("snapped_cells", "Snapped mesh"), ("layer_cells", "Layer mesh")):
        m = re.search(rf"{label} : cells:(\d+)", text)
        if m:
            out[key] = int(m.group(1))
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "Cells per refinement level:":
            levels: dict[int, int] = {}
            for row in lines[i + 1 :]:
                m = re.match(r"^\s+(\d+)\s+(\d+)\s*$", row)
                if not m:
                    break
                levels[int(m.group(1))] = int(m.group(2))
            out["cells_per_level"] = levels
        if "overall thickness" in line:
            layers: dict[str, dict[str, float]] = {}
            for row in lines[i + 3 :]:
                m = _LAYER_ROW.match(row.strip())
                if not m:
                    break
                name, faces, target, got, thick, pct = m.groups()
                layers[name] = {
                    "faces": int(faces),
                    "target_layers": float(target),
                    "layers": float(got),
                    "thickness_m": float(thick),
                    "thickness_percent": float(pct),
                }
            out["layers"] = layers
    m = re.search(rf"Finished meshing in = {_NUM} s", text)
    if m:
        out["seconds"] = float(m.group(1))
    out["finished"] = "Finished meshing without any errors" in text
    return out



# ---------------------------------------------------------------- cfMesh (2.5b)

#: Kullanıcı 2026-10-09 ("ikisini de yap"): cfMesh, snappyHexMesh'e seçilebilir
#: ikinci mesh'leyici. Resmi ESI imajında yok; ``backend/docker/openfoam``
#: (ESI cfMesh modülü derlenmiş imaj) gerekir.
CFMESH_SCRIPT = (
    "set -o pipefail; "
    "cartesianMesh > log.cartesianMesh 2>&1 && "
    "checkMesh -constant > log.checkMesh 2>&1; "
    "echo \"MESH_EXIT=$?\""
)


def _box_faces(box: TunnelBox, ground: bool) -> dict[str, list[tuple[tuple[float, float, float], ...]]]:
    """Tünel kutusunun dış yüzleri (dışa bakan normallerle iki üçgen) → yama adı."""
    (x0, y0, z0), (x1, y1, z1) = box.lo, box.hi
    quads = {
        "inlet": [((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0))],
        "outlet": [((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1))],
        "sides": [
            ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)),
            ((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)),
            ((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)),
        ],
    }
    bottom = ((x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0))
    if ground:
        quads["ground"] = [bottom]
    else:
        quads["sides"].append(bottom)
    return {name: [t for a, b, c, d in qs for t in ((a, b, c), (a, c, d))] for name, qs in quads.items()}


def domain_stl(box: TunnelBox, ground: bool, body_stl_text: str) -> str:
    """cfMesh yüzey dosyası: tünel kutusu + gövde tek STL'de (her biri ayrı solid)."""
    out = []
    for name, tris in _box_faces(box, ground).items():
        out.append(f"solid {name}\n")
        for a, b, c in tris:
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
            out.append(f"  facet normal {n[0] / ln:.6e} {n[1] / ln:.6e} {n[2] / ln:.6e}\n    outer loop\n")
            for p in (a, b, c):
                out.append(f"      vertex {p[0]:.9e} {p[1]:.9e} {p[2]:.9e}\n")
            out.append("    endloop\n  endfacet\n")
        out.append(f"endsolid {name}\n")
    return "".join(out) + body_stl_text


def cfmesh_dict(box: TunnelBox, bbox_m: tuple[float, ...], regions: list[str], ground: bool, base_cell_m: float, p: SnappyParams) -> str:
    """cartesianMesh ``meshDict``. snappy ayarlarıyla aynı anlamda eşleme:
    gövde hücresi = taban / 2^surface_level_max, iz kutusu = taban / 2^wake_level,
    sınır tabakası katman sayısı ve büyüme oranı aynı."""
    xmin, ymin, zmin, xmax, ymax, zmax = bbox_m
    body_cell = base_cell_m / 2**p.surface_level_max
    regex = "(" + "|".join(regions) + ")"
    wake = ""
    if p.wake_level > 0:
        pad = 0.25 * box.body_length_m
        lo = (xmin - pad, ymin - pad, zmin - pad)
        hi = (xmax + p.wake_length * box.body_length_m, ymax + pad, zmax + pad)
        centre = tuple((lo[i] + hi[i]) / 2 for i in range(3))
        wake = (
            "objectRefinements\n{\n    wake\n    {\n        type        box;\n"
            f"        cellSize    {_n(base_cell_m / 2**p.wake_level)};\n"
            f"        centre      {_vec(centre)};\n"
            f"        lengthX     {_n(hi[0] - lo[0])};\n        lengthY     {_n(hi[1] - lo[1])};\n        lengthZ     {_n(hi[2] - lo[2])};\n"
            "    }\n}\n\n"
        )
    layers = ""
    if p.n_layers > 0:
        layers = (
            "boundaryLayers\n{\n    patchBoundaryLayers\n    {\n"
            f'        "{regex}"\n        {{\n            nLayers {p.n_layers};\n            thicknessRatio {_n(p.expansion_ratio)};\n        }}\n'
            "    }\n    optimiseLayer 1;\n}\n\n"
        )
    names = [("inlet", "patch"), ("outlet", "patch"), ("sides", "patch")]
    if ground:
        names.append(("ground", "wall"))
    names += [(r, "wall") for r in regions]
    rename = "".join(f"        {n}\n        {{\n            type    {t};\n            newName {n};\n        }}\n" for n, t in names)
    return _header("meshDict") + (
        'surfaceFile "constant/triSurface/domain.stl";\n\n'
        f"maxCellSize {_n(base_cell_m)};\n\n"
        f'localRefinement\n{{\n    "{regex}"\n    {{\n        cellSize {_n(body_cell)};\n    }}\n}}\n\n'
        f"{wake}{layers}"
        f"renameBoundary\n{{\n    defaultName body;\n    defaultType wall;\n    newPatchNames\n    {{\n{rename}    }}\n}}\n"
    )


def write_cfmesh_case(case_dir: Path, stl: SurfaceExport, tunnel: TunnelParams, p: SnappyParams) -> TunnelBox:
    """cfMesh sözlüklerini yazar (``constant/triSurface/body.stl`` hazır olmalı)."""
    box = tunnel_box(stl.bbox_m, tunnel)
    tri = Path(case_dir) / "constant" / "triSurface"
    (tri / "domain.stl").write_text(
        domain_stl(box, tunnel.ground, (tri / "body.stl").read_text(encoding="ascii")), encoding="ascii", newline="\n"
    )
    path = Path(case_dir) / "system" / "meshDict"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cfmesh_dict(box, stl.bbox_m, stl.regions, tunnel.ground, tunnel.base_cell_m, p), encoding="utf-8", newline="\n")
    return box
