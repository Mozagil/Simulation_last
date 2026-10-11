"""LS-DYNA temas / BC / yük → crash kurulum parametreleri — 1.21d.

Çıktı adaptörün zaten okuduğu alanlar: contacts, region_nodes,
boundary_conditions, initial_velocities, gravity, rigid_wall /
use_rigid_wall, initial_velocity, t_end_ms, parts[].role. Kart yazılmaz.

Yalnız dosyada olan uygulanır: adaptörün varsayılanları (bariyer hızı
−5 m/s, orijinde duvar) açıkça kapatılır. Tüm part'lar "moving" rolünde
(BCS yok; rijit duvarın ikincil grubu = tüm part düğümleri, *RIGIDWALL
NSID = 0 ile aynı) ve bariyer hızı sıfır; ilk hız yalnız dosyadaki
*INITIAL_VELOCITY kartlarından gelir.

Eşleme tablosu (raporda her satırda kaynak keyword ve hedef kart):
- *CONTACT_..._NODES_TO_SURFACE   → /INTER/TYPE7 (slave düğüm → master yüzey)
- *CONTACT_..._SURFACE_TO_SURFACE → /INTER/TYPE24 (simetrik)
- *CONTACT_..._SINGLE_SURFACE     → /INTER/TYPE7 öz temas (tek part)
  Part / part kümesi (SSTYP/MSTYP 3 / 2) çevrilir; segment, düğüm, eleman
  kümeleri ve çok part'lı tek yüzey teması çevrilmez. FS → sürtünme.
- *BOUNDARY_SPC_NODE / _SET → /BCS (bölge düğümleri), yalnız global (CID 0)
- *INITIAL_VELOCITY(_NODE / _GENERATION) → /INIVEL/TRA (part ya da bölge)
- *RIGIDWALL_PLANAR (NSID 0) → /RWALL/PLANE, M = taban, normal = baş − taban
- *LOAD_BODY_X/Y/Z (sabit eğri) → /GRAV; işaret LS-DYNA ataletsel
  tanımıyla ters (pozitif değer −eksen yönünde yerçekimi)
- *CONTROL_TERMINATION → t_end_ms
Varsayılandan farklı, karşılığı olmayan alanlar uyarıya düşer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.importers.dyna_k import DynaModel, contact_kind
from app.importers.dyna_material import DynaUnits
from app.importers.dyna_mesh import DynaCrashMesh
from app.solvers.crash_params import (
    CrashBcParams,
    CrashContactParams,
    CrashGravityParams,
    CrashInitVelParams,
)

_CONTACT_TYPE = {"NODES_TO_SURFACE": 7, "SURFACE_TO_SURFACE": 24, "SINGLE_SURFACE": 7}


@dataclass
class DynaSetupMap:
    contacts: list[dict[str, Any]] = field(default_factory=list)
    region_nodes: dict[str, list[int]] = field(default_factory=dict)
    boundary_conditions: list[dict[str, Any]] = field(default_factory=list)
    initial_velocities: list[dict[str, Any]] = field(default_factory=list)
    gravity: dict[str, Any] | None = None
    rigid_wall: dict[str, Any] | None = None
    t_end_ms: float | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)  # rapor
    warnings: list[str] = field(default_factory=list)

    def apply(self, params: dict[str, Any]) -> dict[str, Any]:
        params["contacts"] = [dict(c) for c in self.contacts]
        params.setdefault("region_nodes", {}).update(
            {k: list(v) for k, v in self.region_nodes.items()}
        )
        params.setdefault("boundary_conditions", []).extend(
            dict(b) for b in self.boundary_conditions
        )
        params["initial_velocities"] = [dict(v) for v in self.initial_velocities]
        params["initial_velocity"] = {"vx": 0.0, "vy": 0.0, "vz": 0.0}
        params["use_rigid_wall"] = self.rigid_wall is not None
        if self.rigid_wall is not None:
            params["rigid_wall"] = dict(self.rigid_wall)
        if self.gravity is not None:
            params["gravity"] = dict(self.gravity)
        if self.t_end_ms is not None:
            params["t_end_ms"] = self.t_end_ms
        for spec in params.setdefault("parts", []):
            spec["role"] = "moving"
        return params

    def report(self) -> dict[str, Any]:
        return {"rows": [dict(r) for r in self.rows], "warnings": list(self.warnings)}


def _row(out: DynaSetupMap, source: str, where: str, target: str | None, detail: str) -> None:
    out.rows.append(
        {
            "source": f"*{source}",
            "where": where,
            "target": target,
            "status": "çevrildi" if target else "atlandı",
            "detail": detail,
        }
    )


def _extras_note(extras: dict[str, float]) -> str:
    return ", ".join(f"{k}={v:g}" for k, v in extras.items())


def _parts_of(
    model: DynaModel, mesh_pids: set[int], sid: int, typ: int, single: bool
) -> list[int] | str:
    """Temas tarafı → PID listesi; çevrilemezse neden (str)."""
    if typ == 3:
        return [sid] if sid in mesh_pids else f"part {sid} mesh'te yok"
    if typ == 2:
        if sid not in model.part_sets:
            return f"part kümesi {sid} yok"
        pids = [p for p in model.part_sets[sid] if p in mesh_pids]
        return pids or f"part kümesi {sid} mesh'te boş"
    if single and (typ == 5 or sid == 0):
        return sorted(mesh_pids)
    return f"SSTYP/MSTYP {typ} (segment / düğüm / eleman kümesi) desteklenmiyor"


def _contacts(out: DynaSetupMap, model: DynaModel, mesh_pids: set[int]) -> None:
    for c in model.contacts:
        kind = contact_kind(c.keyword) or ""
        ctype = _CONTACT_TYPE[kind]
        single = kind == "SINGLE_SURFACE"
        slaves = _parts_of(model, mesh_pids, c.ssid, c.sstyp, single)
        masters = slaves if single else _parts_of(model, mesh_pids, c.msid, c.mstyp, False)
        if isinstance(slaves, str) or isinstance(masters, str):
            _row(out, c.keyword, c.where, None, slaves if isinstance(slaves, str) else str(masters))
            continue
        if single and len(slaves) > 1:
            _row(out, c.keyword, c.where, None,
                 f"çok part'lı tek yüzey teması ({len(slaves)} part) — temas part çifti başına")
            continue
        pairs = [(s, m) for s in slaves for m in masters]
        try:
            built = [
                CrashContactParams(type=ctype, slave_part=s - 1, master_part=m - 1, fric=c.fs)
                for s, m in pairs
            ]
        except ValidationError as exc:
            _row(out, c.keyword, c.where, None, exc.errors()[0]["msg"])
            continue
        out.contacts += [b.model_dump(include={"type", "slave_part", "master_part", "fric"}) for b in built]
        detail = ", ".join(f"slave {s} → master {m}" for s, m in pairs) + f", sürtünme {c.fs:g}"
        _row(out, c.keyword, c.where, f"/INTER/TYPE{ctype}", detail)
        notes = dict(c.extras)
        if c.fd and c.fd != c.fs:
            notes["FD"] = c.fd
        if c.dc:
            notes["DC"] = c.dc
        if notes:
            out.warnings.append(f"{c.where}: *{c.keyword} çevrilmedi — {_extras_note(notes)}")


def _region(out: DynaSetupMap, prefix: str, nodes: list[int]) -> str:
    name = f"{prefix}_{len(out.region_nodes) + 1}"
    out.region_nodes[name] = nodes
    return name


def _node_target(
    model: DynaModel, mesh_nodes: set[int], kind: str, target: int
) -> list[int] | str:
    if kind == "all":
        return sorted(mesh_nodes)
    if kind in ("node_set", "BOUNDARY_SPC_SET"):
        if target not in model.node_sets:
            return f"düğüm kümesi {target} yok"
        ids = [n for n in model.node_sets[target] if n in mesh_nodes]
        return ids or f"düğüm kümesi {target} mesh'te boş"
    return [target] if target in mesh_nodes else f"düğüm {target} mesh'te yok"


def _spcs(out: DynaSetupMap, model: DynaModel, mesh_nodes: set[int]) -> None:
    # Aynı keyword + aynı serbestlik → tek bölge (tek /BCS)
    groups: dict[tuple[str, str], list[tuple[str, list[int]]]] = {}
    for s in model.spcs:
        if s.cid:
            _row(out, s.keyword, s.where, None, f"yerel sistem CID {s.cid} desteklenmiyor")
            continue
        if "1" not in s.dofs:
            _row(out, s.keyword, s.where, None, "kilitli serbestlik yok")
            continue
        ids = _node_target(model, mesh_nodes, s.keyword, s.target)
        if isinstance(ids, str):
            _row(out, s.keyword, s.where, None, ids)
            continue
        groups.setdefault((s.keyword, s.dofs), []).append((s.where, ids))
    for (keyword, dofs), items in groups.items():
        nodes = sorted({n for _, ids in items for n in ids})
        region = _region(out, "spc", nodes)
        bc = CrashBcParams(name=region, region=region, dofs=dofs)
        out.boundary_conditions.append(bc.model_dump(include={"name", "region", "dofs"}))
        _row(out, keyword, items[0][0], "/BCS",
             f"{len(nodes)} düğüm, Tx Ty Tz Rx Ry Rz = {dofs} ({len(items)} satır)")


def _velocity(
    out: DynaSetupMap, units: DynaUnits, name: str, v: tuple[float, float, float], **target: Any
) -> str | None:
    speed = math.sqrt(sum(c * c for c in v))
    if speed == 0:
        return "hız sıfır"
    factor = units.length_to_mm * 1e-3 / units.time_to_s
    iv = CrashInitVelParams(
        name=name, speed_m_s=speed * factor, direction=tuple(c / speed for c in v), **target
    )
    out.initial_velocities.append(iv.model_dump(exclude_none=True))
    return None


def _init_vels(
    out: DynaSetupMap, model: DynaModel, mesh_pids: set[int], mesh_nodes: set[int], units: DynaUnits
) -> None:
    by_vector: dict[tuple[float, float, float], list[tuple[str, int]]] = {}
    for iv in model.init_vels:
        if iv.extras:
            out.warnings.append(f"{iv.where}: *{iv.keyword} çevrilmedi — {_extras_note(iv.extras)}")
        name = f"inivel_{len(out.initial_velocities) + 1}"
        if iv.styp == "node":
            if iv.target not in mesh_nodes:
                _row(out, iv.keyword, iv.where, None, f"düğüm {iv.target} mesh'te yok")
            else:
                by_vector.setdefault(iv.v, []).append((iv.where, iv.target))
            continue
        if iv.styp in ("part", "part_set"):
            pids = _parts_of(model, mesh_pids, iv.target, 3 if iv.styp == "part" else 2, False)
            if isinstance(pids, str):
                _row(out, iv.keyword, iv.where, None, pids)
                continue
            for pid in pids:
                why = _velocity(out, units, f"inivel_part_{pid}", iv.v, part_id=pid - 1)
                _row(out, iv.keyword, iv.where, None if why else "/INIVEL/TRA",
                     why or f"part {pid}, v = {iv.v}")
            continue
        if iv.styp not in ("node_set", "all"):
            _row(out, iv.keyword, iv.where, None, f"{iv.styp} desteklenmiyor")
            continue
        ids = _node_target(model, mesh_nodes, iv.styp, iv.target)
        if isinstance(ids, str):
            _row(out, iv.keyword, iv.where, None, ids)
            continue
        region = _region(out, "inivel", ids)
        why = _velocity(out, units, name, iv.v, region=region)
        if why:
            del out.region_nodes[region]
        _row(out, iv.keyword, iv.where, None if why else "/INIVEL/TRA",
             why or f"{len(ids)} düğüm, v = {iv.v}")
    for v, items in by_vector.items():
        region = _region(out, "inivel", sorted({n for _, n in items}))
        why = _velocity(out, units, f"inivel_{len(out.initial_velocities) + 1}", v, region=region)
        if why:
            del out.region_nodes[region]
        _row(out, "INITIAL_VELOCITY_NODE", items[0][0], None if why else "/INIVEL/TRA",
             why or f"{len(items)} düğüm, v = {v}")


def _rigid_wall(out: DynaSetupMap, model: DynaModel, units: DynaUnits) -> None:
    for k, w in enumerate(model.rigid_walls):
        if k > 0:
            _row(out, "RIGIDWALL_PLANAR", w.where, None, "adaptör tek duvar destekliyor")
            continue
        if w.nsid:
            _row(out, "RIGIDWALL_PLANAR", w.where, None,
                 f"NSID {w.nsid}: duvar tüm hareketli part düğümlerine uygulanır, küme desteklenmiyor")
            continue
        normal = tuple(h - t for h, t in zip(w.head, w.tail))
        if not any(normal):
            _row(out, "RIGIDWALL_PLANAR", w.where, None, "taban = baş (normal sıfır)")
            continue
        point = [c * units.length_to_mm for c in w.tail]
        out.rigid_wall = {"point": point, "normal": list(normal)}
        _row(out, "RIGIDWALL_PLANAR", w.where, "/RWALL/PLANE",
             f"M = {tuple(round(c, 6) for c in point)} mm, n = {normal}")
        if w.extras:
            out.warnings.append(f"{w.where}: *RIGIDWALL_PLANAR çevrilmedi — {_extras_note(w.extras)}")


def _gravity(out: DynaSetupMap, model: DynaModel, units: DynaUnits) -> None:
    for b in model.body_loads:
        src = f"LOAD_BODY_{b.axis}"
        curve = model.curves.get(b.lcid)
        if curve is None or not curve.points:
            _row(out, src, b.where, None, f"eğri {b.lcid} yok")
            continue
        ys = {y for _, y in curve.points}
        if len(ys) != 1:
            _row(out, src, b.where, None, "zamana bağlı ivme (eğri sabit değil) desteklenmiyor")
            continue
        if out.gravity is not None:
            _row(out, src, b.where, None, "adaptör tek yönde yerçekimi destekliyor")
            continue
        value = b.sf * ys.pop()
        if value == 0:
            _row(out, src, b.where, None, "ivme sıfır")
            continue
        accel = -value * units.length_to_mm * 1e-3 / units.time_to_s**2
        out.gravity = CrashGravityParams(accel_m_s2=accel, direction=b.axis).model_dump()
        _row(out, src, b.where, "/GRAV", f"{accel:.6g} m/s², eksen {b.axis}")
        if b.extras:
            out.warnings.append(f"{b.where}: *{src} çevrilmedi — {_extras_note(b.extras)}")


def to_crash_setup(model: DynaModel, mesh: DynaCrashMesh, units: DynaUnits) -> DynaSetupMap:
    """Temas, SPC, ilk hız, rijit duvar, yerçekimi ve bitiş zamanını çevirir."""
    out = DynaSetupMap()
    mesh_pids = {p.pid for p in mesh.parts}
    mesh_nodes = {n[0] for n in mesh.nodes}
    _contacts(out, model, mesh_pids)
    _spcs(out, model, mesh_nodes)
    _init_vels(out, model, mesh_pids, mesh_nodes, units)
    _rigid_wall(out, model, units)
    _gravity(out, model, units)
    if model.end_time:
        out.t_end_ms = model.end_time * units.time_to_s * 1e3
    return out
