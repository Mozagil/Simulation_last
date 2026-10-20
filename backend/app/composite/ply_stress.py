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


def plies_by_set_from_inp(text: str) -> dict[str, int]:
    """Desteden `*SHELL SECTION, ELSET=…, COMPOSITE` → {ELSET: katman sayısı}."""
    out: dict[str, int] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("*"):
            current = None
            up = line.upper().replace(" ", "")
            if up.startswith("*SHELLSECTION") and ",COMPOSITE" in up:
                for field in up.split(","):
                    if field.startswith("ELSET="):
                        current = field[len("ELSET="):]
                        out[current] = 0
            continue
        if current is not None and line and not line.startswith("**"):
            out[current] += 1
    return {k: v for k, v in out.items() if v > 0}
