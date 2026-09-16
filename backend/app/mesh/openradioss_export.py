"""Gmsh .msh → OpenRadioss düğüm / /TETRA4 (ve isteğe bağlı /BRICK) listesi.

Faz 1.2: CalculiX `generate_mesh` çıktısını (.msh, tet10) değiştirmez. Explicit
crash /TETRA4 ister — tet10'un ilk 4 köşesi alınır, kenar-ortası düğümler
yazılmaz. Hex8/hex20 köşeleri /BRICK olur.
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


@dataclass
class RadiossMesh:
    """OpenRadiossAdapter.build_input'un beklediği düğüm/eleman listeleri."""

    nodes: list[dict[str, float | int]]
    tets: list[tuple[int, int, int, int, int]] = field(default_factory=list)
    bricks: list[tuple[int, ...]] = field(default_factory=list)


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
        eid = 1

        entities = gmsh.model.getEntities(dim=3)
        if not entities:
            entities = [(-1, -1)]

        for edim, etag in entities:
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
                        eid += 1
                    elif gtype in (_HEX8, _HEX20) and len(conn) >= 8:
                        bricks.append((eid, *conn[:8]))
                        eid += 1
    finally:
        gmsh.finalize()
        _gmsh_lock.release()

    if not tets and not bricks:
        raise MeshError(
            f"OpenRadioss export için 3D tet/hex yok ({mesh_path.name}). "
            "Crash yolu solid mesh ister; 2D shell CalculiX'te kalır."
        )

    used: set[int] = set()
    for _e, n1, n2, n3, n4 in tets:
        used.update((n1, n2, n3, n4))
    for brick in bricks:
        used.update(brick[1:])

    nodes = [
        {"id": nid, "x": xyz[nid][0], "y": xyz[nid][1], "z": xyz[nid][2]}
        for nid in sorted(used)
        if nid in xyz
    ]
    return RadiossMesh(nodes=nodes, tets=tets, bricks=bricks)
