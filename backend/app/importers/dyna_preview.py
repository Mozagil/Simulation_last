"""İçe aktarılan crash mesh'inin web önizlemesi — 1.21e-2a.

Adaptör parametrelerinden (import.json) three.js'in çizeceği yüzeyi üretir:
kabuklar olduğu gibi, katılar yalnız dış yüzleriyle (tek elemana ait yüz).
Koordinatlar mm. Çıktı `CrashAnimationViewer` ile aynı biçim: `nodes`
(x, y, z listesi), `faces` (nodes indeksleri, 3 / 4 köşe), `face_part`
(her yüzün dosyadaki PID'i).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

# Katı yüzleri, yerel düğüm sırasına göre (LS-DYNA / Radioss 8 düğüm sırası).
_HEX_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
_TET_FACES = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2))


def _collapse(face: Sequence[int]) -> tuple[int, ...]:
    """Ardışık / kapanıştaki tekrar düğümleri at (dejenere hex yüzü → üçgen)."""
    out: list[int] = []
    for n in face:
        if not out or out[-1] != n:
            out.append(n)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return tuple(out)


def _solid_faces(
    elements: Iterable[Sequence[int]], local: Sequence[Sequence[int]], parts: dict[int, int]
) -> Iterable[tuple[tuple[int, ...], int]]:
    for elem in elements:
        eid, conn = int(elem[0]), elem[1:]
        for lf in local:
            face = _collapse([int(conn[i]) for i in lf])
            if len(face) >= 3:
                yield face, parts[eid]


def surface_preview(params: dict[str, Any]) -> dict[str, Any]:
    """Adaptör mesh parametrelerinden önizleme yüzeyi (PID = part_id + 1)."""
    # JSON'dan gelince anahtarlar str olur.
    elem_part = {int(k): int(v) for k, v in params["element_parts"].items()}

    faces: list[tuple[tuple[int, ...], int]] = []
    for elem in list(params.get("shells", [])) + list(params.get("sh3n", [])):
        face = _collapse([int(n) for n in elem[1:]])
        if len(face) >= 3:
            faces.append((face, elem_part[int(elem[0])]))

    solid: dict[frozenset[int], list[tuple[tuple[int, ...], int]]] = {}
    for face, pid in [
        *_solid_faces(params.get("bricks", []), _HEX_FACES, elem_part),
        *_solid_faces(params.get("tets", []), _TET_FACES, elem_part),
    ]:
        solid.setdefault(frozenset(face), []).append((face, pid))
    faces.extend(found[0] for found in solid.values() if len(found) == 1)

    coords = {int(n[0]): (float(n[1]), float(n[2]), float(n[3])) for n in params["nodes"]}
    index: dict[int, int] = {}
    nodes: list[tuple[float, float, float]] = []
    out_faces: list[list[int]] = []
    face_part: list[int] = []
    counts: dict[int, int] = {}
    for face, part_id in faces:
        row = []
        for nid in face:
            if nid not in index:
                index[nid] = len(nodes)
                nodes.append(coords[nid])
            row.append(index[nid])
        out_faces.append(row)
        face_part.append(part_id + 1)
        counts[part_id + 1] = counts.get(part_id + 1, 0) + 1

    if nodes:
        lo = [min(c[i] for c in nodes) for i in range(3)]
        hi = [max(c[i] for c in nodes) for i in range(3)]
    else:
        lo = hi = [0.0, 0.0, 0.0]
    return {
        "nodes": [list(c) for c in nodes],
        "faces": out_faces,
        "face_part": face_part,
        "part_faces": {str(pid): n for pid, n in sorted(counts.items())},
        "bbox_mm": {"min": lo, "max": hi},
    }
