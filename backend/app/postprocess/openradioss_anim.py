"""OpenRadioss animasyonu (A001…) → web deforme şekil verisi (1.17d).

`anim_to_vtk` (OpenRadioss resmi dönüştürücüsü) her animasyon dosyasını ASCII
VTK'ya çevirir: POINTS (deforme koordinatlar), CELLS, POINT_DATA
(Displacement, Velocity), CELL_DATA (PART_ID, EROSION_STATUS, istenen eleman
skalerleri). Burada yüzey üçgenleri bir kez (ilk kare) çıkarılır; kare başına
koordinatlar ve skalerler saklanır. Çıktı iş klasöründe `anim.json` (önbellek).

Yüzey: kabuk (VTK 5 üçgen, 9 dörtgen) doğrudan; solid (10 tet, 12 hex) dış
yüzleri (tek kez görülen yüz). Kiriş / yay / rijit duvar hücreleri atlanır.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

_TRI, _QUAD, _TET, _HEX = 5, 9, 10, 12
_TET_FACES = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2))
_HEX_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


def parse_vtk_ascii(text: str) -> dict[str, Any]:
    """anim_to_vtk ASCII çıktısı → {time, points, cells, cell_types, point_data, cell_data}."""
    lines = text.splitlines()
    out: dict[str, Any] = {"time": None, "points": [], "cells": [], "cell_types": [],
                           "point_data": {}, "cell_data": {}}
    i, n = 0, len(lines)
    section = None
    while i < n:
        ln = lines[i].strip()
        if ln.startswith("TIME "):
            out["time"] = float(lines[i + 1].split()[0])
            i += 2
            continue
        m = re.match(r"POINTS (\d+)", ln)
        if m:
            cnt = int(m.group(1))
            vals: list[float] = []
            i += 1
            while len(vals) < 3 * cnt:
                vals.extend(float(v) for v in lines[i].split())
                i += 1
            out["points"] = [vals[k : k + 3] for k in range(0, 3 * cnt, 3)]
            continue
        m = re.match(r"CELLS (\d+)", ln)
        if m:
            cnt = int(m.group(1))
            for k in range(cnt):
                row = [int(v) for v in lines[i + 1 + k].split()]
                out["cells"].append(row[1 : 1 + row[0]])
            i += 1 + cnt
            continue
        m = re.match(r"CELL_TYPES (\d+)", ln)
        if m:
            cnt = int(m.group(1))
            out["cell_types"] = [int(lines[i + 1 + k]) for k in range(cnt)]
            i += 1 + cnt
            continue
        if ln.startswith("POINT_DATA"):
            section, size = "point_data", int(ln.split()[1])
            i += 1
            continue
        if ln.startswith("CELL_DATA"):
            section, size = "cell_data", int(ln.split()[1])
            i += 1
            continue
        m = re.match(r"(SCALARS|VECTORS) (\S+) \S+", ln)
        if m and section:
            kind, name = m.group(1), m.group(2)
            i += 1
            if kind == "SCALARS" and i < n and lines[i].strip().startswith("LOOKUP_TABLE"):
                i += 1
            width = 3 if kind == "VECTORS" else 1
            vals = []
            while len(vals) < width * size and i < n:
                vals.extend(float(v) for v in lines[i].split())
                i += 1
            out[section][name] = vals if width == 1 else [vals[k : k + 3] for k in range(0, 3 * size, 3)]
            continue
        i += 1
    return out


def surface_faces(cells: list[list[int]], types: list[int]) -> tuple[list[list[int]], list[int]]:
    """Görünür yüzler (nokta indeksleri) + her yüzün kaynak hücresi."""
    faces: list[list[int]] = []
    owner: list[int] = []
    solid: dict[tuple[int, ...], tuple[list[int], int, int]] = {}
    for ci, (conn, t) in enumerate(zip(cells, types)):
        if t in (_TRI, _QUAD):
            faces.append(list(conn))
            owner.append(ci)
        elif t in (_TET, _HEX):
            for f in _TET_FACES if t == _TET else _HEX_FACES:
                face = [conn[k] for k in f]
                key = tuple(sorted(face))
                if key in solid:
                    solid[key] = (face, ci, solid[key][2] + 1)
                else:
                    solid[key] = (face, ci, 1)
    for face, ci, count in solid.values():
        if count == 1:
            faces.append(face)
            owner.append(ci)
    return faces, owner


def build_animation(vtk_texts: list[str], max_frames: int = 60) -> dict[str, Any]:
    """Kare VTK metinleri → web verisi. Topoloji ilk kareden (hücre sırası sabit)."""
    frames = [parse_vtk_ascii(t) for t in vtk_texts]
    frames = [f for f in frames if f["points"]]
    if not frames:
        return {"frames": [], "faces": [], "face_part": [], "scalars": {}}
    if len(frames) > max_frames:
        step = math.ceil(len(frames) / max_frames)
        frames = frames[::step] + ([frames[-1]] if (len(frames) - 1) % step else [])
    first = frames[0]
    faces, owner = surface_faces(first["cells"], first["cell_types"])
    # anim_to_vtk rijit duvarı NODE_ID = 0 olan sentetik noktalarla dörtgen
    # çizer, rijit gövde ana düğümüne dejenere dörtgen ekler (1.17d gerçek
    # koşu); ikisi de model yüzeyi değil — atlanır.
    nid = first["point_data"].get("NODE_ID")
    keep = [
        k for k, f in enumerate(faces)
        if len(set(f)) >= 3 and not (nid and any(int(nid[v]) == 0 for v in f))
    ]
    faces = [faces[k] for k in keep]
    owner = [owner[k] for k in keep]
    part = first["cell_data"].get("PART_ID") or [0] * len(first["cells"])
    out_frames = []
    node_scalars = ("Displacement",)
    cell_names = [k for k in first["cell_data"] if k not in ("ELEMENT_ID", "PART_ID", "EROSION_STATUS")]
    scal_range: dict[str, list[float]] = {}
    for f in frames:
        pts = f["points"]
        fr: dict[str, Any] = {
            "time": f["time"],
            "positions": [round(c, 4) for p in pts for c in p],
        }
        disp = f["point_data"].get("Displacement")
        if disp:
            mag = [round(math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2), 4) for d in disp]
            fr["node"] = {"disp_mag": mag}
            r = scal_range.setdefault("disp_mag", [math.inf, -math.inf])
            r[0], r[1] = min(r[0], min(mag)), max(r[1], max(mag))
        er = f["cell_data"].get("EROSION_STATUS")
        if er:
            fr["face_alive"] = [1 if er[c] else 0 for c in owner]
        cd: dict[str, list[float]] = {}
        for name in cell_names:
            vals = f["cell_data"][name]
            if len(vals) != len(f["cells"]):
                continue
            cd[name] = [round(float(vals[c]), 6) for c in owner]
            r = scal_range.setdefault(name, [math.inf, -math.inf])
            r[0], r[1] = min(r[0], min(cd[name])), max(r[1], max(cd[name]))
        fr["face"] = cd
        out_frames.append(fr)
    return {
        "faces": faces,
        "face_part": [int(part[c]) for c in owner],
        # Hep sıfır olan skaler (ör. 1D eleman yokken 1DELEM_*) gösterilmez.
        "scalars": {
            k: {"location": "node" if k in ("disp_mag",) else "face", "min": v[0], "max": v[1]}
            for k, v in scal_range.items()
            if not (v[0] == 0 and v[1] == 0)
        },
        "frames": out_frames,
        "node_scalars": list(node_scalars),
    }


def write_animation_cache(work_dir: Path, data: dict[str, Any]) -> Path:
    p = Path(work_dir) / "anim.json"
    p.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return p
