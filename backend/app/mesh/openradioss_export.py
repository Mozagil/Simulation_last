"""Gmsh .msh → OpenRadioss düğüm / /TETRA4 (ve isteğe bağlı /BRICK) listesi.

Faz 1.2: CalculiX `generate_mesh` çıktısını (.msh, tet10) değiştirmez. Explicit
crash /TETRA4 ister — tet10'un ilk 4 köşesi alınır, kenar-ortası düğümler
yazılmaz. Hex8/hex20 köşeleri /BRICK olur.

1.13: hacim elemanı olmayan (2D) mesh kabuk olarak okunur — tri3/tri6 → /SH3N,
quad4/quad8/quad9 → /SHELL (köşe düğümleri). Parça = kenar paylaşan kabuk
bileşeni (CalculiX 2D yolu ve önizleme ile aynı eşleme).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import gmsh

from app.mesh.base import MeshError
from app.mesh.gmsh_adapter import _gmsh_lock

# Gmsh eleman tipleri (volume).
_TET4 = 4
_TET10 = 11
_HEX8 = 5
_HEX20 = 17
# Gmsh eleman tipleri (yüzey / kabuk).
_TRI3 = 2
_TRI6 = 9
_QUAD4 = 3
_QUAD8 = 16
_QUAD9 = 10


@dataclass
class RadiossMesh:
    """OpenRadiossAdapter.build_input'un beklediği düğüm/eleman listeleri."""

    nodes: list[dict[str, float | int]]
    tets: list[tuple[int, int, int, int, int]] = field(default_factory=list)
    bricks: list[tuple[int, ...]] = field(default_factory=list)
    # 1.13 kabuk: (eid, n1..n4) /SHELL ve (eid, n1..n3) /SH3N.
    shells: list[tuple[int, int, int, int, int]] = field(default_factory=list)
    sh3n: list[tuple[int, int, int, int]] = field(default_factory=list)
    # eleman id → parça (0 tabanlı; mesh katmanının part_id'si = hacim sırası,
    # bkz. gmsh_adapter._compute_face_to_part). Deck parça başına /PART yazar.
    element_parts: dict[int, int] = field(default_factory=dict)


def _tet_signed_volume(
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
    p3: tuple[float, float, float],
    p4: tuple[float, float, float],
) -> float:
    ax, ay, az = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
    bx, by, bz = p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]
    cx, cy, cz = p4[0] - p1[0], p4[1] - p1[1], p4[2] - p1[2]
    return (
        ax * (by * cz - bz * cy)
        + ay * (bz * cx - bx * cz)
        + az * (bx * cy - by * cx)
    ) / 6.0


def gmsh_msh_to_radioss(mesh_path: Path) -> RadiossMesh:
    """Kayıtlı Gmsh .msh dosyasını OpenRadioss solid listesine çevirir.

    `.msh` üzerine yazmaz. Volume elemanı yoksa MeshError.
    """
    mesh_path = Path(mesh_path)
    if not mesh_path.exists():
        raise MeshError(f"Mesh dosyası yok: {mesh_path.name}")

    _gmsh_lock.acquire()
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(mesh_path))

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        xyz: dict[int, tuple[float, float, float]] = {}
        for i, tag in enumerate(node_tags):
            xyz[int(tag)] = (
                float(coords[3 * i]),
                float(coords[3 * i + 1]),
                float(coords[3 * i + 2]),
            )

        tets: list[tuple[int, int, int, int, int]] = []
        bricks: list[tuple[int, ...]] = []
        element_parts: dict[int, int] = {}
        eid = 1

        entities = gmsh.model.getEntities(dim=3)
        if not entities:
            entities = [(-1, -1)]

        for part_index, (edim, etag) in enumerate(entities):
            kwargs: dict = {"dim": 3}
            if etag != -1:
                kwargs["tag"] = etag
            etypes, tag_lists, node_lists = gmsh.model.mesh.getElements(**kwargs)
            for etype, tags, enodes in zip(etypes, tag_lists, node_lists):
                n_per = len(enodes) // max(len(tags), 1) if len(tags) else 0
                if n_per == 0 or len(tags) == 0:
                    continue
                gtype = int(etype)
                for ei, _etag_i in enumerate(tags):
                    conn = [int(enodes[ei * n_per + k]) for k in range(n_per)]
                    if gtype in (_TET4, _TET10) and len(conn) >= 4:
                        n1, n2, n3, n4 = conn[0], conn[1], conn[2], conn[3]
                        vol = _tet_signed_volume(xyz[n1], xyz[n2], xyz[n3], xyz[n4])
                        if vol < 0:
                            n3, n4 = n4, n3
                        tets.append((eid, n1, n2, n3, n4))
                        element_parts[eid] = part_index
                        eid += 1
                    elif gtype in (_HEX8, _HEX20) and len(conn) >= 8:
                        bricks.append((eid, *conn[:8]))
                        element_parts[eid] = part_index
                        eid += 1

        shells: list[tuple[int, int, int, int, int]] = []
        sh3n: list[tuple[int, int, int, int]] = []
        if not tets and not bricks:
            from app.mesh.gmsh_adapter import _surface_parts_by_coincident_nodes

            face_to_part = _surface_parts_by_coincident_nodes()
            for _edim, ftag in gmsh.model.getEntities(dim=2):
                pid = face_to_part.get(int(ftag), 0)
                etypes, tag_lists, node_lists = gmsh.model.mesh.getElements(dim=2, tag=ftag)
                for etype, tags, enodes in zip(etypes, tag_lists, node_lists):
                    if len(tags) == 0:
                        continue
                    n_per = len(enodes) // len(tags)
                    gtype = int(etype)
                    for ei in range(len(tags)):
                        conn = [int(enodes[ei * n_per + k]) for k in range(n_per)]
                        if gtype in (_TRI3, _TRI6):
                            sh3n.append((eid, conn[0], conn[1], conn[2]))
                        elif gtype in (_QUAD4, _QUAD8, _QUAD9):
                            shells.append((eid, conn[0], conn[1], conn[2], conn[3]))
                        else:
                            continue
                        element_parts[eid] = pid
                        eid += 1
    finally:
        gmsh.finalize()
        _gmsh_lock.release()

    if not tets and not bricks and not shells and not sh3n:
        raise MeshError(
            f"OpenRadioss export için solid (tet/hex) ya da kabuk (tri/quad) eleman yok "
            f"({mesh_path.name})."
        )

    used: set[int] = set()
    for _e, n1, n2, n3, n4 in tets:
        used.update((n1, n2, n3, n4))
    for brick in bricks:
        used.update(brick[1:])
    for el in [*shells, *sh3n]:
        used.update(el[1:])

    nodes = [
        {"id": nid, "x": xyz[nid][0], "y": xyz[nid][1], "z": xyz[nid][2]}
        for nid in sorted(used)
        if nid in xyz
    ]
    return RadiossMesh(
        nodes=nodes,
        tets=tets,
        bricks=bricks,
        shells=shells,
        sh3n=sh3n,
        element_parts=element_parts,
    )
