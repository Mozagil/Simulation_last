"""Katman gerilmesi (Faz 3.11): ccx `.dat` → eleman × ply × IP tensörü.

Kaynak `.frd` değil, `*EL PRINT, ELSET=…  S` çıktısıdır: `.frd` düğüm
değerleri katmanlar arasında ortalanır, ply sınırındaki süreksizliği
taşıyamaz. ccx 2.23 kompozit kabuğu (S8R → C3D20R) katman başına 2×2×2
integrasyon noktasıyla yazar; satırlar alt → üst katman sıralı, gerilme
**ply eksenlerinde** (1 lif, 2 dik, 3 normal) ve satır sonunda katmanın
orientation adı vardır (`OR_0_1_shell_…`). V-P1 düzeninde CLT ile ölçüldü
(`docs/COMPOSITE_VALIDATION.md`).

Bileşen sırası: s11, s22, s33, s12, s13, s23 (MPa). Araç yorum yapmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

COMPONENTS = ("s11", "s22", "s33", "s12", "s13", "s23")
_HEADER = "stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz)"


@dataclass(frozen=True)
class PlyStress:
    element_ids: np.ndarray  # (n_elem,)
    values: np.ndarray  # (n_elem, n_ply, n_ip, 6) MPa, ply eksenleri

    @property
    def n_plies(self) -> int:
        return int(self.values.shape[1])

    def ply_mean(self) -> np.ndarray:
        """(n_elem, n_ply, 6): katman içi IP ortalaması."""
        return self.values.mean(axis=2)

    def extremes(self) -> dict[str, float]:
        """Katman başına min/max (tüm eleman ve IP'ler): `ply{k}_{bileşen}_{min|max}`."""
        out: dict[str, float] = {"n_plies": float(self.n_plies)}
        for k in range(self.n_plies):
            layer = self.values[:, k, :, :]
            for c, name in enumerate(COMPONENTS):
                if name in ("s33", "s13", "s23"):
                    continue
                out[f"ply{k + 1}_{name}_min"] = float(layer[..., c].min())
                out[f"ply{k + 1}_{name}_max"] = float(layer[..., c].max())
        return out


def parse_ply_stress(text: str, plies_by_set: dict[str, int]) -> dict[str, PlyStress]:
    """`*EL PRINT` S bloklarını ELSET başına okur: {ELSET: PlyStress}.

    `plies_by_set`: ELSET adı → katman sayısı (büyük/küçük harf duyarsız; ccx
    adları büyük harfle yazar). Listede olmayan setler atlanır. IP sayısı
    katman sayısına tam bölünmeli.
    """
    wanted = {k.upper(): int(v) for k, v in plies_by_set.items()}
    if any(v < 1 for v in wanted.values()):
        raise ValueError("Katman sayısı pozitif olmalı.")
    rows: dict[str, dict[int, dict[int, list[float]]]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(_HEADER):
            tail = line[len(_HEADER):].split()
            name = tail[2].upper() if len(tail) > 2 and tail[:2] == ["for", "set"] else ""
            current = name if name in wanted else None
            continue
        if current is None:
            continue
        parts = line.split()
        try:
            eid, ip = int(parts[0]), int(parts[1])
            vals = [float(v) for v in parts[2:8]]
        except (ValueError, IndexError):
            current = None
            continue
        rows.setdefault(current, {}).setdefault(eid, {})[ip] = vals
    return {name: _to_array(by_elem, wanted[name]) for name, by_elem in rows.items()}


def _to_array(rows: dict[int, dict[int, list[float]]], n_plies: int) -> PlyStress:
    eids = sorted(rows)
    n_ip_total = len(rows[eids[0]])
    if n_ip_total % n_plies:
        raise ValueError(
            f"IP sayısı ({n_ip_total}) katman sayısına ({n_plies}) bölünmüyor."
        )
    n_ip = n_ip_total // n_plies
    arr = np.zeros((len(eids), n_plies, n_ip, 6), dtype=float)
    for i, eid in enumerate(eids):
        ips = rows[eid]
        if len(ips) != n_ip_total:
            raise ValueError(f"Eleman {eid}: {len(ips)} IP, beklenen {n_ip_total}.")
        for j, ip in enumerate(sorted(ips)):
            arr[i, j // n_ip, j % n_ip, :] = ips[ip]
    return PlyStress(element_ids=np.array(eids, dtype=int), values=arr)


def read_ply_stress(dat_path: Path, plies_by_set: dict[str, int]) -> dict[str, PlyStress]:
    if not dat_path.is_file():
        return {}
    return parse_ply_stress(
        dat_path.read_text(encoding="utf-8", errors="replace"), plies_by_set
    )


def ply_stress_scalars(by_set: dict[str, PlyStress]) -> dict[str, float]:
    """ResultSet.scalars: tek set → `ply{k}_…`; birden çok → `{set}_ply{k}_…`."""
    out: dict[str, float] = {}
    single = len(by_set) == 1
    for name, ps in sorted(by_set.items()):
        prefix = "" if single else f"{name.lower()}_"
        out.update({f"{prefix}{k}": v for k, v in ps.extremes().items()})
    return out


def el_print_block(elsets: list[str]) -> str:
    """Kompozit ELSET'ler için integrasyon noktası gerilme isteği (adım içi)."""
    return "".join(f"*EL PRINT, ELSET={name}\nS\n" for name in elsets)


@dataclass(frozen=True)
class DeckPly:
    material: str
    orientation: str
    angle_deg: float | None


def parse_composite_deck(
    text: str,
) -> tuple[dict[str, list[DeckPly]], dict[str, list[float]]]:
    """Desteden kompozit kesitler ve dayanım yorumları.

    Döner: ({ELSET: [DeckPly alt → üst]}, {MALZEME: [Xt, Xc, Yt, Yc, S12(, S23)] MPa}).
    Ply açısı `*ORIENTATION` bloğunun `3, θ` satırından (yoksa None).
    """
    sets: dict[str, list[DeckPly]] = {}
    raw_plies: dict[str, list[tuple[str, str]]] = {}
    angles: dict[str, float] = {}
    strengths: dict[str, list[float]] = {}
    current: str | None = None
    orient: str | None = None
    orient_line = 0
    for raw in text.splitlines():
        line = raw.strip()
        up = line.upper().replace(" ", "")
        if line.startswith("**"):
            if up.startswith("**PLY_STRENGTH_MPA,NAME="):
                fields = [f.strip() for f in line.split(",")]
                name = fields[1].split("=", 1)[1].strip().upper()
                strengths[name] = [float(v) for v in fields[2:]]
            continue
        if line.startswith("*"):
            current = None
            orient = None
            if up.startswith("*SHELLSECTION") and ",COMPOSITE" in up:
                for field in up.split(","):
                    if field.startswith("ELSET="):
                        current = field[len("ELSET="):]
                        raw_plies[current] = []
            elif up.startswith("*ORIENTATION"):
                for field in up.split(","):
                    if field.startswith("NAME="):
                        orient = field[len("NAME="):]
                        orient_line = 0
            continue
        if not line:
            continue
        if current is not None:
            parts = [f.strip().upper() for f in line.split(",")]
            raw_plies[current].append((parts[2], parts[3] if len(parts) > 3 else ""))
        elif orient is not None:
            orient_line += 1
            if orient_line == 2:
                parts = [f.strip() for f in line.split(",")]
                if parts and parts[0] == "3" and len(parts) > 1:
                    angles[orient] = float(parts[1])
    for elset, plies in raw_plies.items():
        if plies:
            sets[elset] = [DeckPly(m, o, angles.get(o)) for m, o in plies]
    return sets, strengths


def plies_by_set_from_inp(text: str) -> dict[str, int]:
    """Desteden `*SHELL SECTION, ELSET=…, COMPOSITE` → {ELSET: katman sayısı}."""
    sets, _ = parse_composite_deck(text)
    return {k: len(v) for k, v in sets.items()}
