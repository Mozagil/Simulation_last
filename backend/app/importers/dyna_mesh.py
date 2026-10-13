"""LS-DYNA ara modeli → crash mesh parametreleri — 1.21b.

`DynaModel` (dyna_k.py) OpenRadioss adaptörünün zaten okuduğu biçime
çevrilir: nodes, shells / sh3n, tets / bricks, element_parts, parts
(kalınlık). Kartları yine `OpenRadiossAdapter.build_input` yazar; burada
kart yazılmaz (adaptör deseni).

Parça numarası: adaptör Radioss part_ID = part_id + 1 kullanır; burada
part_id = PID - 1 verilir, böylece deck'te /PART/<dosyadaki PID> kalır.

Birim: keyword dosyası birim taşımaz. Uzunluk çarpanı (dosya → mm)
mühendisten gelir; düğüm koordinatı ve kabuk kalınlığı bununla çarpılır.

Eleman ayrımı (ham düğümlerden):
- kabuk: N3 == N4 ya da N4 = 0 → /SH3N, değilse /SHELL
- solid: N4..N8 aynı → /TETRA4; diğerleri (dejenere prizma dahil) /BRICK'e
  ham sırayla gider ve raporda sayılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.importers.dyna_k import DynaModel


class DynaMeshError(ValueError):
    """Ara model crash mesh'ine çevrilemedi."""


@dataclass
class DynaPartInfo:
    pid: int  # dosyadaki PID = Radioss part_ID
    part_id: int  # adaptör parça no (PID - 1)
    title: str
    kind: str  # "shell" | "solid"
    secid: int
    mid: int
    elform: int | None
    thickness_mm: float | None
    elements: int


@dataclass
class DynaCrashMesh:
    nodes: list[tuple[int, float, float, float]] = field(default_factory=list)
    shells: list[tuple[int, int, int, int, int]] = field(default_factory=list)
    sh3n: list[tuple[int, int, int, int]] = field(default_factory=list)
    tets: list[tuple[int, int, int, int, int]] = field(default_factory=list)
    bricks: list[tuple[int, ...]] = field(default_factory=list)
    element_parts: dict[int, int] = field(default_factory=dict)
    parts: list[DynaPartInfo] = field(default_factory=list)
    degenerate_bricks: int = 0
    warnings: list[str] = field(default_factory=list)

    def adapter_params(self) -> dict[str, Any]:
        """OpenRadiossAdapter mesh alanları. Malzeme, rol, yük ayrı adımlarda."""
        return {
            "nodes": list(self.nodes),
            "shells": list(self.shells),
            "sh3n": list(self.sh3n),
            "tets": list(self.tets),
            "bricks": list(self.bricks),
            "element_parts": dict(self.element_parts),
            "parts": [
                {"part_id": p.part_id, "thickness_mm": p.thickness_mm}
                if p.thickness_mm is not None
                else {"part_id": p.part_id}
                for p in self.parts
            ],
        }

    def report(self) -> dict[str, Any]:
        return {
            "nodes": len(self.nodes),
            "shells": len(self.shells),
            "sh3n": len(self.sh3n),
            "tets": len(self.tets),
            "bricks": len(self.bricks),
            "degenerate_bricks": self.degenerate_bricks,
            "parts": [p.__dict__.copy() for p in self.parts],
            "warnings": list(self.warnings),
        }


def to_crash_mesh(model: DynaModel, length_to_mm: float) -> DynaCrashMesh:
    """Ara modeli adaptör mesh parametrelerine çevirir; birim çarpanı zorunlu."""
    if not length_to_mm or length_to_mm <= 0:
        raise DynaMeshError("Uzunluk çarpanı (dosya → mm) pozitif olmalı.")
    if not model.shells and not model.solids:
        raise DynaMeshError("Dosyada kabuk ya da solid eleman yok.")

    used_nodes = {n for _, ns in model.shells.values() for n in ns if n} | {
        n for _, ns in model.solids.values() for n in ns if n
    }
    missing = sorted(used_nodes - model.nodes.keys())
    if missing:
        raise DynaMeshError(f"Elemanlarda tanımsız düğüm ({len(missing)}): {missing[:10]}")
    elem_pids = {pid for pid, _ in model.shells.values()} | {
        pid for pid, _ in model.solids.values()
    }
    no_part = sorted(elem_pids - model.parts.keys())
    if no_part:
        raise DynaMeshError(f"Elemanların part'ı tanımsız: {no_part[:10]}")
    bad_pid = sorted(p for p in elem_pids if p < 1)
    if bad_pid:
        raise DynaMeshError(f"PID 1'den küçük olamaz: {bad_pid[:10]}")
    mixed = sorted(
        {pid for pid, _ in model.shells.values()} & {pid for pid, _ in model.solids.values()}
    )
    if mixed:
        raise DynaMeshError(f"Aynı part'ta kabuk ve solid eleman: {mixed[:10]}")

    out = DynaCrashMesh()
    out.nodes = [
        (nid, x * length_to_mm, y * length_to_mm, z * length_to_mm)
        for nid, (x, y, z) in sorted(model.nodes.items())
        if nid in used_nodes
    ]
    unused = len(model.nodes) - len(out.nodes)
    if unused:
        out.warnings.append(f"Elemana bağlı olmayan {unused} düğüm alınmadı")

    counts: dict[int, int] = {}
    for eid, (pid, ns) in sorted(model.shells.items()):
        n1, n2, n3, n4 = ns
        if n4 == 0 or n4 == n3:
            out.sh3n.append((eid, n1, n2, n3))
        else:
            out.shells.append((eid, n1, n2, n3, n4))
        out.element_parts[eid] = pid - 1
        counts[pid] = counts.get(pid, 0) + 1
    for eid, (pid, ns) in sorted(model.solids.items()):
        if len(set(ns[3:])) == 1:
            out.tets.append((eid, *ns[:4]))
        else:
            if len(set(ns)) < 8:
                out.degenerate_bricks += 1
            out.bricks.append((eid, *ns))
        out.element_parts[eid] = pid - 1
        counts[pid] = counts.get(pid, 0) + 1

    shell_pids = {pid for pid, _ in model.shells.values()}
    for pid in sorted(elem_pids):
        part = model.parts[pid]
        kind = "shell" if pid in shell_pids else "solid"
        elform: int | None = None
        thickness: float | None = None
        if kind == "shell":
            sec = model.shell_sections.get(part.secid)
            if sec is None:
                out.warnings.append(f"part {pid}: kabuk kesiti {part.secid} yok; kalınlık boş")
            else:
                elform = sec.elform
                thickness = sec.thickness[0] * length_to_mm
                if len(set(sec.thickness)) > 1:
                    out.warnings.append(
                        f"part {pid}: düğüm kalınlıkları farklı {sec.thickness}; T1 alındı"
                    )
        else:
            ssec = model.solid_sections.get(part.secid)
            if ssec is None:
                out.warnings.append(f"part {pid}: solid kesiti {part.secid} yok")
            else:
                elform = ssec.elform
        out.parts.append(
            DynaPartInfo(
                pid=pid,
                part_id=pid - 1,
                title=part.title,
                kind=kind,
                secid=part.secid,
                mid=part.mid,
                elform=elform,
                thickness_mm=thickness,
                elements=counts[pid],
            )
        )
    empty = sorted(model.parts.keys() - elem_pids)
    if empty:
        out.warnings.append(f"Elemanı olmayan part(lar) alınmadı: {empty[:10]}")
    return out
