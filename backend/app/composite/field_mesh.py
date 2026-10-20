"""Kompozit sonuç arayüzü (Faz 3.13): ply alanı + eleman köşe geometrisi.

`<job>_ply.json` eleman id'leri taşır, koordinat taşımaz. Kontur için deste
`*NODE` / `*ELEMENT` bloklarından her elemanın köşe düğümleri okunur
(S3/S6 → 3, S4/S8/S8R → 4 köşe; ara düğümler atılır). Çıktı set başına
sıkıştırılmış düğüm listesi ve eleman sırasıyla aynı köşe indeksleri.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _corner_count(etype: str) -> int:
    etype = etype.upper()
    return 3 if etype.startswith(("S3", "CPS3", "M3D3", "S6", "CPS6", "M3D6")) else 4


def parse_shell_mesh(
    text: str,
) -> tuple[dict[int, tuple[float, float, float]], dict[int, list[int]]]:
    """Deste → ({düğüm id: xyz}, {eleman id: köşe düğüm id'leri})."""
    nodes: dict[int, tuple[float, float, float]] = {}
    elems: dict[int, list[int]] = {}
    block: str | None = None
    corners = 4
    pending = ""
    for raw in text.splitlines():
        line = (pending + raw.strip()) if pending else raw.strip()
        pending = ""
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            upper = line.upper()
            block = None
            if upper.startswith("*NODE") and not upper.startswith(("*NODE FILE", "*NODE PRINT", "*NODE OUTPUT")):
                block = "node"
            elif upper.startswith("*ELEMENT") and "OUTPUT" not in upper:
                block = "elem"
                corners = 4
                for part in line.split(",")[1:]:
                    key, _, value = part.partition("=")
                    if key.strip().upper() == "TYPE":
                        corners = _corner_count(value.strip())
            continue
        if block is None:
            continue
        if block == "elem" and line.endswith(","):
            pending = line
            continue
        parts = [p.strip() for p in line.split(",") if p.strip()]
        try:
            if block == "node" and len(parts) >= 4:
                nodes[int(parts[0])] = (float(parts[1]), float(parts[2]), float(parts[3]))
            elif block == "elem" and len(parts) > corners:
                elems[int(parts[0])] = [int(v) for v in parts[1 : 1 + corners]]
        except ValueError:
            continue
    return nodes, elems


def ply_field_with_mesh(inp_path: Path, ply_path: Path) -> dict[str, Any]:
    """Ply alanına set başına `nodes` ([[x,y,z]]) ve `faces` (yerel köşe indeksleri) ekler."""
    field = json.loads(ply_path.read_text(encoding="utf-8"))
    nodes, elems = parse_shell_mesh(inp_path.read_text(encoding="utf-8", errors="replace"))
    for data in field.get("sets", {}).values():
        local: dict[int, int] = {}
        xyz: list[list[float]] = []
        faces: list[list[int]] = []
        for eid in data["element_ids"]:
            face: list[int] = []
            for nid in elems.get(int(eid), []):
                if nid not in nodes:
                    face = []
                    break
                if nid not in local:
                    local[nid] = len(xyz)
                    xyz.append(list(nodes[nid]))
                face.append(local[nid])
            faces.append(face)
        data["nodes"] = xyz
        data["faces"] = faces
    return field
