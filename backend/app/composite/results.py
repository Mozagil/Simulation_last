"""Kompozit sonuç sonrası işleme (Faz 3.11 + 3.12): deste + `.dat` → scalars + ply alanı.

`CalculiXAdapter.parse_results` yalnız bu fonksiyonu çağırır. Deste
kompozit değilse boş döner (izotrop yol değişmez).

Ply alanı (`<job>_ply.json`, 3.13 arayüzü için): ELSET başına eleman id'leri,
katman (malzeme, açı) ve eleman × katman dizileri — gerilme IP ortalaması
(s11, s22, s12; MPa), IRF katmanın IP'leri içinde en büyük (Tsai-Wu,
Hashin, Hashin kipi 0–3 = `failure.HASHIN_MODES`). Dayanımı olmayan
malzemede IRF null.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from app.composite.failure import HASHIN_MODES, Strength, hashin_irf, tsai_wu_irf
from app.composite.ply_stress import (
    PlyStress,
    parse_composite_deck,
    ply_stress_scalars,
    read_ply_stress,
)


def _strength(vals: list[float] | None) -> Strength | None:
    if not vals or len(vals) < 5:
        return None
    return Strength(*vals[:5], s23=vals[5] if len(vals) > 5 else None)


def _round(arr: np.ndarray) -> list[Any]:
    return np.round(arr, 6).tolist()


def composite_results(
    inp_path: Path,
    dat_path: Path,
    out_path: Path | None = None,
    f12_star: float = -0.5,
) -> dict[str, float]:
    """Katman gerilmesi uç değerleri + IRF scalars; `out_path` verilirse ply alanı."""
    deck = inp_path.read_text(encoding="utf-8", errors="replace")
    sets, strengths = parse_composite_deck(deck)
    if not sets:
        return {}
    by_set = read_ply_stress(dat_path, {k: len(v) for k, v in sets.items()})
    if not by_set:
        return {}
    scalars = ply_stress_scalars(by_set)
    field: dict[str, Any] = {"f12_star": f12_star, "hashin_modes": list(HASHIN_MODES), "sets": {}}
    best: dict[str, tuple[float, str, int, int, int]] = {}
    s23_used: list[bool] = []
    for elset, ps in sorted(by_set.items()):
        plies = sets[elset]
        tw, hs, hm = _set_failure(ps, plies, strengths, s23_used, f12_star)
        mean = ps.ply_mean()
        field["sets"][elset] = {
            "element_ids": ps.element_ids.tolist(),
            "plies": [{"material": p.material, "angle_deg": p.angle_deg} for p in plies],
            "s11": _round(mean[..., 0]),
            "s22": _round(mean[..., 1]),
            "s12": _round(mean[..., 3]),
            "tsai_wu_irf": _irf_list(tw),
            "hashin_irf": _irf_list(hs),
            "hashin_mode": np.where(np.isnan(hm), -1, hm).astype(int).tolist(),
        }
        for key, arr in (("tsai_wu", tw), ("hashin", hs)):
            if np.all(np.isnan(arr)):
                continue
            idx = np.unravel_index(np.nanargmax(arr), arr.shape)
            val = float(arr[idx])
            mode = int(hm[idx]) if key == "hashin" else -1
            if key not in best or val > best[key][0]:
                best[key] = (val, elset, int(ps.element_ids[idx[0]]), int(idx[1]) + 1, mode)
            for k in range(arr.shape[1]):
                col = arr[:, k]
                if not np.all(np.isnan(col)):
                    prefix = "" if len(by_set) == 1 else f"{elset.lower()}_"
                    scalars[f"{prefix}ply{k + 1}_{key}_irf_max"] = float(np.nanmax(col))
    for key, (val, elset, eid, ply, mode) in best.items():
        scalars[f"{key}_irf_max"] = val
        scalars[f"{key}_element"] = float(eid)
        scalars[f"{key}_ply"] = float(ply)
        if key == "hashin":
            scalars["hashin_mode"] = float(mode)
    if s23_used:
        scalars["hashin_mc_s23"] = float(all(s23_used))
    if out_path is not None:
        out_path.write_text(json.dumps(field), encoding="utf-8")
    return scalars


def _irf_list(arr: np.ndarray) -> list[Any]:
    return [[None if np.isnan(v) else round(float(v), 6) for v in row] for row in arr]


def _set_failure(
    ps: PlyStress,
    plies: list,
    strengths: dict[str, list[float]],
    s23_used: list[bool],
    f12_star: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(n_elem, n_ply) Tsai-Wu IRF, Hashin IRF, Hashin kipi (IP'ler içinde en büyük)."""
    n_elem, n_ply = ps.values.shape[:2]
    tw = np.full((n_elem, n_ply), np.nan)
    hs = np.full((n_elem, n_ply), np.nan)
    hm = np.full((n_elem, n_ply), np.nan)
    for k, ply in enumerate(plies):
        st = _strength(strengths.get(ply.material))
        if st is None:
            continue
        s23_used.append(st.s23 is not None)
        v = ps.values[:, k, :, :]
        s1, s2, t12 = v[..., 0], v[..., 1], v[..., 3]
        tw[:, k] = tsai_wu_irf(s1, s2, t12, st, f12_star).max(axis=1)
        modes = hashin_irf(s1, s2, t12, st)  # (n_elem, n_ip, 4)
        per_ip = modes.max(axis=2)
        hs[:, k] = per_ip.max(axis=1)
        ip = per_ip.argmax(axis=1)
        hm[:, k] = modes[np.arange(n_elem), ip, :].argmax(axis=1)
    return tw, hs, hm
