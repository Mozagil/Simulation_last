"""OpenRadioss zaman geçmişi → ResultSet (enerji, RWALL, ivme, HIC).

Binary T01 parse edilmez (th_to_csv resmi dönüştürücü). Bu modül:
- engine listing (`*_0001.out`)
- th_to_csv CSV (`*T01.csv`)
- isteğe bağlı ASCII kolon dosyası

Birimler: zaman varsayılanı model (mm-ms → ms). İvme AX/AY/AZ → mm/ms²
(= 1000 m/s²) → g. `acc_g` sütunu olduğu gibi g.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any

from app.postprocess.hic import hic15, hic36, resultant_g
from app.solvers.base import ResultSet

# 1 mm/ms² = 1000 m/s²
_G = 9.80665
_MM_MS2_TO_G = 1000.0 / _G


def impulse_to_force(time: list[float], impulse: list[float]) -> list[float]:
    """RWALL T01 ham çıktısı impuls; kuvvet = dI/dt."""
    n = min(len(time), len(impulse))
    if n == 0:
        return []
    force = [0.0] * n
    for i in range(1, n):
        dt = time[i] - time[i - 1]
        if abs(dt) < 1e-30:
            force[i] = force[i - 1]
        else:
            force[i] = (impulse[i] - impulse[i - 1]) / dt
    force[0] = force[1] if n > 1 else 0.0
    return force


def _norm_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _time_to_seconds(time: list[float], header: str) -> list[float]:
    h = header.lower()
    if "[s]" in h or "(s)" in h or h.endswith("_s") or "sec" in h:
        return list(time)
    if "[ms]" in h or "(ms)" in h or "millis" in h:
        return [t * 1e-3 for t in time]
    if not time:
        return []
    tmax = max(abs(t) for t in time)
    if tmax <= 2.0:
        return list(time)
    return [t * 1e-3 for t in time]


def _acc_to_g(values: list[float], header: str) -> list[float]:
    h = _norm_header(header)
    if "accg" in h or h in ("ag", "resultantg"):
        return list(values)
    return [v * _MM_MS2_TO_G for v in values]


def _pick_column(headers: list[str], *needles: str) -> int | None:
    norms = [_norm_header(h) for h in headers]
    for needle in needles:
        n = _norm_header(needle)
        for i, h in enumerate(norms):
            if n == h or n in h:
                return i
    return None


def parse_th_csv(path: Path) -> dict[str, list[float]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return {}
    reader = csv.reader(lines)
    rows = list(reader)
    if len(rows) < 2:
        return {}
    headers = [c.strip() for c in rows[0]]
    data: list[list[float]] = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        try:
            data.append([float(c) for c in row[: len(headers)]])
        except ValueError:
            continue
    if not data:
        return {}
    cols = {headers[i]: [r[i] for r in data if i < len(r)] for i in range(len(headers))}
    return cols


def parse_energy_listing(path: Path) -> dict[str, list[float]]:
    """Engine .out içinde IENERGY/KENERGY satırları."""
    text = path.read_text(encoding="utf-8", errors="replace")
    header_idx = None
    headers: list[str] = []
    for i, raw in enumerate(text.splitlines()):
        up = raw.upper()
        if "IENERGY" in up or "INTERNAL ENERGY" in up.replace(" ", ""):
            headers = raw.split()
            header_idx = i
            break
        if "IENERGY" in up and "KENERGY" in up:
            headers = raw.split()
            header_idx = i
            break
    if header_idx is None:
        return {}
    # kolon adlarını sadeleştir
    names = [_norm_header(h) for h in headers]
    time_i = next((i for i, n in enumerate(names) if n in ("time", "t")), None)
    ie_i = next((i for i, n in enumerate(names) if "ienergy" in n or n == "ie"), None)
    ke_i = next((i for i, n in enumerate(names) if "kenergy" in n or n == "ke"), None)
    hg_i = next((i for i, n in enumerate(names) if "hourglass" in n or n in ("hg", "hgenergy")), None)
    if time_i is None or ie_i is None:
        # bazen CYCLE TIME TIMESTP IENERGY ...
        for i, n in enumerate(names):
            if n == "time":
                time_i = i
            if "ienergy" in n:
                ie_i = i
            if "kenergy" in n:
                ke_i = i
    if time_i is None or ie_i is None:
        return {}
    times: list[float] = []
    ie: list[float] = []
    ke: list[float] = []
    hg: list[float] = []
    for raw in text.splitlines()[header_idx + 1 :]:
        parts = raw.split()
        if len(parts) <= max(time_i, ie_i):
            continue
        try:
            # İlk alan CYCLE (int) olabilir
            t = float(parts[time_i])
            times.append(t)
            ie.append(float(parts[ie_i]))
            if ke_i is not None and ke_i < len(parts):
                ke.append(float(parts[ke_i]))
            if hg_i is not None and hg_i < len(parts):
                hg.append(float(parts[hg_i]))
        except ValueError:
            continue
    out: dict[str, list[float]] = {}
    if times:
        out["TIME"] = times
        out["IE"] = ie
        if ke:
            out["KE"] = ke
        if hg:
            out["HOURGLASS"] = hg
    return out


def _series_from_csv_cols(cols: dict[str, list[float]]) -> dict[str, Any]:
    headers = list(cols.keys())
    t_key = None
    for h in headers:
        if _norm_header(h) in ("time", "t", "times", "timems", "timesec"):
            t_key = h
            break
    if t_key is None:
        t_key = headers[0]
    time = cols[t_key]
    packed: dict[str, Any] = {"time": time, "time_header": t_key}

    def col(*needles: str) -> list[float] | None:
        idx = _pick_column(headers, *needles)
        if idx is None:
            return None
        return cols[headers[idx]]

    packed["ie"] = col("IE", "IENERGY", "internal")
    packed["ke"] = col("KE", "KENERGY", "kinetic")
    packed["hg"] = col("HOURGLASS", "HG")
    packed["fnx"] = col("FNX", "RWALLFNX")
    packed["fny"] = col("FNY", "RWALLFNY")
    packed["fnz"] = col("FNZ", "RWALLFNZ")
    packed["imp"] = col("IMP", "IMPULSE")
    packed["ax"] = col("ACCX", "AX")
    packed["ay"] = col("ACCY", "AY")
    packed["az"] = col("ACCZ", "AZ")
    packed["acc_g"] = None
    for h in headers:
        nh = _norm_header(h)
        if nh in ("accg", "ag", "resultantg") or "acc_g" in h.lower():
            packed["acc_g"] = cols[h]
            packed["acc_g_header"] = h
            break
    return packed


def parse_openradioss_dir(work_dir: Path) -> ResultSet:
    work_dir = Path(work_dir)
    csv_path = _find_csv(work_dir)
    out_path = _find_listing(work_dir)
    cols: dict[str, list[float]] = {}
    if csv_path is not None:
        cols = parse_th_csv(csv_path)
    listing = parse_energy_listing(out_path) if out_path is not None else {}

    time: list[float] = []
    ie: list[float] = []
    ke: list[float] = []
    force: list[float] = []
    acc_g: list[float] = []
    time_header = "TIME"

    if cols:
        packed = _series_from_csv_cols(cols)
        time = packed["time"]
        time_header = packed["time_header"]
        ie = packed["ie"] or ie
        ke = packed["ke"] or ke
        fnx, fny, fnz = packed["fnx"], packed["fny"], packed["fnz"]
        if fnx and fny and fnz:
            force = [
                math.sqrt(fnx[i] ** 2 + fny[i] ** 2 + fnz[i] ** 2)
                for i in range(min(len(fnx), len(fny), len(fnz)))
            ]
        elif packed["imp"]:
            force = [abs(v) for v in impulse_to_force(time, packed["imp"])]
        elif fnz:
            force = [abs(v) for v in fnz]
        if packed["acc_g"] is not None:
            acc_g = list(packed["acc_g"])
        elif packed["ax"] and packed["ay"] and packed["az"]:
            ax_g = _acc_to_g(packed["ax"], "ACCX")
            ay_g = _acc_to_g(packed["ay"], "ACCY")
            az_g = _acc_to_g(packed["az"], "ACCZ")
            acc_g = resultant_g(ax_g, ay_g, az_g)

    if listing.get("TIME") and not ie:
        time = listing["TIME"]
        ie = listing.get("IE") or []
        ke = listing.get("KE") or []

    if not time and not ie:
        return ResultSet(scalars={}, curves={}, raw_result_path=work_dir)

    time_s = _time_to_seconds(time, time_header) if time else []
    scalars: dict[str, float] = {}
    if ie:
        scalars["internal_energy_final"] = float(ie[-1])
        scalars["internal_energy_max"] = float(max(ie))
    if ke:
        scalars["kinetic_energy_final"] = float(ke[-1])
        scalars["kinetic_energy_max"] = float(max(ke))
        if ie:
            e0 = ie[0] + ke[0]
            e1 = ie[-1] + ke[-1]
            denom = max(abs(e0), abs(e1), 1e-30)
            scalars["energy_balance_rel"] = abs(e1 - e0) / denom
    if force:
        scalars["rwall_force_max"] = float(max(abs(f) for f in force))
    if acc_g and time_s:
        scalars["acc_peak_g"] = float(max(abs(v) for v in acc_g))
        scalars["hic15"] = hic15(time_s, acc_g)
        scalars["hic36"] = hic36(time_s, acc_g)

    curves: dict[str, Any] = {"time": time}
    if ie:
        curves["internal_energy"] = ie
    if ke:
        curves["kinetic_energy"] = ke
    if force:
        curves["rwall_force"] = force
    if acc_g:
        curves["acc_g"] = acc_g

    raw = csv_path or out_path or work_dir
    return ResultSet(scalars=scalars, curves=curves, raw_result_path=raw)


def _find_csv(work_dir: Path) -> Path | None:
    hits = sorted(work_dir.glob("*T01*.csv")) + sorted(work_dir.glob("T01.csv"))
    if hits:
        return hits[0]
    return None


def _find_listing(work_dir: Path) -> Path | None:
    hits = sorted(work_dir.glob("*_0001.out")) + sorted(work_dir.glob("*.out"))
    return hits[0] if hits else None
