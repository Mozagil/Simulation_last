"""OpenRadioss zaman geçmişi → ResultSet (enerji, RWALL, temas, ivme, HIC).

RWALL / INTER FN* sütunları birikimli impulstur (N·s); kuvvet türevle gelir.

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


def impulse_components_to_force(
    time: list[float], components: list[list[float]]
) -> tuple[list[float], list[float]]:
    """/TH/RWALL ve /TH/INTER FN* bileşenleri birikimli impuls (kN·ms = N·s).

    Kuvvet bileşen bileşen türevlenir, sonra bileşke alınır (bileşke impulsun
    türevi değil). Dönüş: (|F| kN, |I| N·s). Son |I| = momentum değişimi.
    """
    n = min([len(time)] + [len(c) for c in components])
    derivs = [impulse_to_force(time[:n], c[:n]) for c in components]
    force = [math.sqrt(sum(d[i] ** 2 for d in derivs)) for i in range(n)]
    impulse = [math.sqrt(sum(c[i] ** 2 for c in components)) for i in range(n)]
    return force, impulse


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


_CYCLE_RE = re.compile(r"^\s+\d+\s+([-+0-9.Ee]+)\s+[-+0-9.Ee]+\s+[A-Z]")
_RUPTURE_RE = re.compile(r"RUPTURE\s*\(([^)]*)\)\s+OF\s+(\w+)\s+ELEMENT\s+NUMBER\s+(\d+)")
_MSG_RE = re.compile(r"^(ERROR|WARNING) ID :\s+(\d+)")


def parse_ruptures(path: Path) -> list[dict[str, Any]]:
    """Engine .out "-- RUPTURE (KRİTER) OF SHELL ELEMENT NUMBER n" satırları.

    Listing kopma anını yazmaz; `time` kopmadan sonra basılan ilk cycle
    satırının zamanıdır (üst sınır, çözünürlük = listing basma aralığı).
    Kopma sonrası cycle satırı yoksa `time` None.
    """
    out: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    in_table = False
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "CYCLE" in raw and "TIME" in raw and "TIME-STEP" in raw:
            in_table = True
            continue
        m = _RUPTURE_RE.search(raw)
        if m:
            rec = {"criterion": m.group(1).strip(), "kind": m.group(2).lower(),
                   "element": int(m.group(3)), "time": None}
            out.append(rec)
            waiting.append(rec)
            continue
        if in_table and waiting:
            c = _CYCLE_RE.match(raw)
            if c:
                try:
                    t = float(c.group(1))
                except ValueError:
                    continue
                for rec in waiting:
                    rec["time"] = t
                waiting = []
    return out


def parse_cycle_table(path: Path) -> dict[str, list[float]]:
    """Engine listing cycle satırları: CYCLE TIME TIME-STEP ELEMENT … TOTAL MASS
    MASS ADDED (1.15a). Basma aralığındaki satırlar; ara cycle'lar listing'de yok."""
    out: dict[str, list[float]] = {"time": [], "dt": [], "total_mass": [], "mass_added": [], "nan_time": []}
    in_table = False
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "CYCLE" in raw and "TIME-STEP" in raw:
            in_table = "MASS ADDED" in raw
            continue
        if not in_table or not _CYCLE_RE.match(raw):
            continue
        tok = raw.split()
        # Iraksama: enerji sütunları NaN (Radioss yine "NORMAL TERMINATION" yazabilir;
        # kullanıcı 2026-10-13, 1000 m/s koşusu). İlk NaN satırının zamanı.
        if "NaN" in tok:
            try:
                out["nan_time"].append(float(tok[1]))
            except (ValueError, IndexError):
                pass
            continue
        try:
            vals = (float(tok[1]), float(tok[2]), float(tok[-2]), float(tok[-1]))
        except (ValueError, IndexError):
            continue
        for k, v in zip(("time", "dt", "total_mass", "mass_added"), vals):
            out[k].append(v)
    return out


def parse_starter_messages(path: Path) -> dict[str, dict[str, int]]:
    """Starter .out "ERROR ID : n" / "WARNING ID : n" → {"errors": {id: adet}, "warnings": …}.

    Özet tablodaki ("|--- 1 WARNING ID : …") satırlar sayılmaz.
    """
    res: dict[str, dict[str, int]] = {"errors": {}, "warnings": {}}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _MSG_RE.match(raw)
        if m:
            bucket = res["errors" if m.group(1) == "ERROR" else "warnings"]
            bucket[m.group(2)] = bucket.get(m.group(2), 0) + 1
    return res


def starter_message_blocks(text: str, max_lines: int = 30) -> list[dict[str, Any]]:
    """1.22c — starter .out mesaj blokları, aynen: "ERROR ID : n" satırından ilk
    boş satıra kadar (en çok `max_lines`). Özet tablo satırları alınmaz.

    Döner: [{"kind": "error"|"warning", "id": "79", "lines": [...]}] (dosya sırası).
    """
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        m = _MSG_RE.match(raw)
        if m:
            current = {"kind": m.group(1).lower(), "id": m.group(2), "lines": [raw.rstrip()]}
            blocks.append(current)
            continue
        if current is not None:
            if not raw.strip() or len(current["lines"]) >= max_lines:
                current = None
            else:
                current["lines"].append(raw.rstrip())
    return blocks


def _diagnostics(work_dir: Path, engine_out: Path | None) -> tuple[dict[str, Any], dict[str, float]]:
    diag: dict[str, Any] = {}
    scalars: dict[str, float] = {}
    starter = sorted(work_dir.glob("*_0000.out"))
    if starter:
        msgs = parse_starter_messages(starter[0])
        diag["starter_errors"] = msgs["errors"]
        diag["starter_warnings"] = msgs["warnings"]
        scalars["starter_error_count"] = float(sum(msgs["errors"].values()))
        scalars["starter_warning_count"] = float(sum(msgs["warnings"].values()))
    if engine_out is not None and engine_out.name.endswith("_0001.out"):
        cyc = parse_cycle_table(engine_out)
        if cyc["nan_time"]:
            scalars["diverged_at_ms"] = float(min(cyc["nan_time"]))
            diag["diverged"] = (
                f"Çözüm ıraksadı: t = {min(cyc['nan_time']):.4g} ms'den sonra enerji NaN "
                "(listing). Bu andan sonraki sonuçlar geçersiz."
            )
        if cyc["dt"]:
            # listing basılan cycle'lardaki değerler (ara adımlar görünmez)
            scalars["timestep_min"] = float(min(cyc["dt"]))
            scalars["timestep_final"] = float(cyc["dt"][-1])
            scalars["mass_added_final"] = float(cyc["mass_added"][-1])
            # TOTAL MASS eklenen kütleyi içerir; oran modelin kendi kütlesine göre
            m0 = cyc["total_mass"][0] - cyc["mass_added"][0]
            if m0 > 0:
                scalars["mass_model"] = float(m0)
                scalars["mass_added_rel"] = float(cyc["mass_added"][-1]) / m0
        rup = parse_ruptures(engine_out)
        diag["deleted_elements"] = rup
        scalars["elements_deleted"] = float(len({(r["kind"], r["element"]) for r in rup}))
        times = [r["time"] for r in rup if r["time"] is not None]
        if times:
            scalars["deletion_time_first"] = float(min(times))
            scalars["deletion_time_last"] = float(max(times))
    return diag, scalars


def _th_group_columns(headers: list[str], titles: tuple[str, ...]) -> list[str]:
    """Başlığında TH grubu adı geçen ve 'var N' ile biten sütunlar, dosya sırasıyla."""
    out: list[str] = []
    for h in headers:
        hl = h.lower()
        if any(t in hl for t in titles) and re.search(r"\bvar\s*\d+\s*$", hl):
            out.append(h)
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

    # 1.17b — th_to_csv global enerji sütunları (tüm model: rijit gövde ana
    # düğümü, ek kütle dahil) varsa onlar; yoksa eski ad araması (parça TH'si
    # rijit gövde ana düğümünün kütlesini içermez — kızaklı koşuda KE 71 J
    # okunuyordu, global 2559 J).
    def exact(name: str) -> list[float] | None:
        return next((cols[h] for h in headers if h.strip().upper() == name), None)

    packed["ie"] = exact("INTERNAL ENERGY") or col("IE", "IENERGY", "internal")
    packed["ke"] = exact("KINETIC ENERGY") or col("KE", "KENERGY", "kinetic")
    packed["hg"] = exact("HOURGLASS ENERGY") or col("HOURGLASS", "HG")
    packed["rot"] = exact("ROTATION ENERGY")
    packed["ext"] = exact("EXTERNAL WORK")
    # Duvar FN* adla aranırken temas grubunun (contact_th) FN* sütunları hariç.
    wall_headers = [h for h in headers if "contact_th" not in h.lower()]

    def wall_col(*needles: str) -> list[float] | None:
        idx = _pick_column(wall_headers, *needles)
        return None if idx is None else cols[wall_headers[idx]]

    packed["fnx"] = wall_col("FNX", "RWALLFNX")
    packed["fny"] = wall_col("FNY", "RWALLFNY")
    packed["fnz"] = wall_col("FNZ", "RWALLFNZ")
    packed["imp"] = col("IMP", "IMPULSE")
    packed["ax"] = col("ACCX", "AX")
    packed["ay"] = col("ACCY", "AY")
    packed["az"] = col("ACCZ", "AZ")
    # th_to_csv (OpenRadioss 2026 ikilisi) TH/RWALL ve TH/NODE değişkenlerini
    # adsız yazıyor: "<grup başlığı> <id> <nesne başlığı> var 25". Deck'teki
    # sıra (FNX FNY FNZ · ACCX ACCY ACCZ) korunur; grup başlığından sırayla al.
    if not (packed["fnx"] and packed["fny"] and packed["fnz"]):
        g = _th_group_columns(headers, ("barrier_th", "rwall"))
        if len(g) >= 3:
            packed["fnx"], packed["fny"], packed["fnz"] = (cols[g[0]], cols[g[1]], cols[g[2]])
    if not (packed["ax"] and packed["ay"] and packed["az"]):
        g = _th_group_columns(headers, ("hic_nodes",))
        if len(g) >= 3:
            packed["ax"], packed["ay"], packed["az"] = (cols[g[0]], cols[g[1]], cols[g[2]])
    # /TH/INTER "contact_th": arayüz başına FNX FNY FNZ FTX FTY FTZ (deck sırası).
    contact_cols = [h for h in headers if "contact_th" in h.lower()]
    packed["contacts"] = [
        [cols[h] for h in contact_cols[i : i + 6]]
        for i in range(0, len(contact_cols) - len(contact_cols) % 6, 6)
    ]
    packed["acc_g"] = None
    for h in headers:
        nh = _norm_header(h)
        if nh in ("accg", "ag", "resultantg") or "acc_g" in h.lower():
            packed["acc_g"] = cols[h]
            packed["acc_g_header"] = h
            break
    return packed


def named_th_curves(
    cols: dict[str, list[float]], spec: dict[str, Any]
) -> tuple[dict[str, list[float]], list[str]]:
    """th_spec.json (deck) → `th_<tür>_<nesne>_<DEĞİŞKEN>` eğrileri (1.15b).

    PART sütunları adlı ("<parça adı> IE"); RWALL / INTER / NODE adsız "var N"
    — grup başlığındaki sütunlar dosya sırasıyla nesne × değişken. Sütun sayısı
    tutmazsa grup adlandırılmaz, adı ikinci listede döner (yanlış etiket yok).
    """
    headers = list(cols.keys())
    out: dict[str, list[float]] = {}
    unmapped: list[str] = []
    for g in spec.get("groups") or []:
        kind, title, objs, names = g["kind"], g["title"], g["objects"], g["vars"]
        if kind == "part":
            ok = True
            for pname, mesh_id in zip(g.get("names") or [], g.get("mesh_ids") or objs):
                for v in names:
                    h = next((h for h in headers if h.strip().startswith(pname) and h.split()[-1] == v), None)
                    if h is None:
                        ok = False
                        continue
                    out[f"th_part_{mesh_id}_{v}"] = cols[h]
            if not ok:
                unmapped.append(title)
            continue
        gcols = [h for h in headers if h.strip().lower().startswith(title.lower())]
        if len(gcols) != len(objs) * len(names):
            unmapped.append(title)
            continue
        k = 0
        for idx, obj in enumerate(objs, start=1):
            for v in names:
                key = {
                    "rwall": f"th_rwall_{v}",
                    "inter": f"th_inter_{idx}_{v}",
                    "sect": f"th_sect_{idx}_{v}",
                }.get(kind, f"th_node_{obj}_{v}")
                out[key] = cols[gcols[k]]
                k += 1
    return out, unmapped


def _apply_cfc(
    work_dir: Path,
    time: list[float],
    time_header: str,
    curves: dict[str, Any],
    scalars: dict[str, float],
    acc_comp: tuple[list[float], list[float], list[float]] | None,
    filters_override: dict[str, Any] | None = None,
) -> None:
    """1.17e — postprocess.json'daki CFC sınıflarıyla süzülmüş eğri / skaler
    ekler; ham olanlar değişmez. Zaman ms (deck birimi). `filters_override`
    verilirse dosya yerine o kullanılır (koşu sonrası yeniden süzme)."""
    import json

    from app.postprocess.cfc import cfc_filter, sample_ratio

    if not time:
        return
    if filters_override is not None:
        flt = filters_override
    else:
        p = work_dir / "postprocess.json"
        if not p.is_file():
            return
        try:
            flt = json.loads(p.read_text(encoding="utf-8")).get("filters") or {}
        except ValueError:
            return
    fc, ac = flt.get("force_cfc"), flt.get("acc_cfc")
    if fc:
        for key in [k for k in curves if re.fullmatch(r"(rwall|contact_\d+|section_\d+)_force", k)]:
            f = cfc_filter(time, curves[key], int(fc))
            curves[f"{key}_cfc{fc}"] = f
            scalars[f"{key}_max_cfc{fc}"] = float(max(abs(v) for v in f))
        scalars[f"sample_ratio_cfc{fc}"] = sample_ratio(time, int(fc))
    if ac:
        for key in [k for k in list(curves) if re.fullmatch(r"th_node_\d+_A[XYZ]", k)]:
            curves[f"{key}_cfc{ac}"] = cfc_filter(time, curves[key], int(ac))
        if acc_comp is not None:
            # J211: kanallar (bileşenler) süzülür, bileşke sonra
            comps = [_acc_to_g(cfc_filter(time, c, int(ac)), "ACCX") for c in acc_comp]
            acc_f = resultant_g(*comps)
            ts = _time_to_seconds(time, time_header)
            curves[f"acc_g_cfc{ac}"] = acc_f
            scalars[f"acc_peak_g_cfc{ac}"] = float(max(abs(v) for v in acc_f))
            scalars[f"hic15_cfc{ac}"] = hic15(ts, acc_f)
            scalars[f"hic36_cfc{ac}"] = hic36(ts, acc_f)
        scalars[f"sample_ratio_cfc{ac}"] = sample_ratio(time, int(ac))


def _read_th_spec(work_dir: Path) -> dict[str, Any] | None:
    p = work_dir / "th_spec.json"
    if not p.is_file():
        return None
    import json

    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def parse_openradioss_dir(work_dir: Path, filters_override: dict[str, Any] | None = None) -> ResultSet:
    work_dir = Path(work_dir)
    csv_path = _find_csv(work_dir)
    out_path = _find_listing(work_dir)
    cols: dict[str, list[float]] = {}
    if csv_path is not None:
        cols = parse_th_csv(csv_path)
    listing = parse_energy_listing(out_path) if out_path is not None else {}

    time: list[float] = []
    acc_comp: tuple[list[float], list[float], list[float]] | None = None
    hg_e: list[float] | None = None
    rot_e: list[float] | None = None
    ext_w: list[float] | None = None
    ie: list[float] = []
    ke: list[float] = []
    force: list[float] = []
    impulse: list[float] = []
    acc_g: list[float] = []
    contact_fn: list[tuple[list[float], list[float]]] = []
    time_header = "TIME"

    spec = _read_th_spec(work_dir)
    named: dict[str, list[float]] = {}
    unmapped: list[str] = []
    if cols and spec is not None:
        named, unmapped = named_th_curves(cols, spec)

    if cols:
        packed = _series_from_csv_cols(cols)
        if spec is not None:
            # Deck spec'i varsa duvar / temas / ivme sütunları adla seçilir
            # (sıra tahmini yerine). Değişken seçilmemişse ilgili skaler yok.
            packed["fnx"], packed["fny"], packed["fnz"] = (
                named.get("th_rwall_FNX"), named.get("th_rwall_FNY"), named.get("th_rwall_FNZ")
            )
            packed["contacts"] = []
            k = 1
            while all(f"th_inter_{k}_{v}" in named for v in ("FNX", "FNY", "FNZ")):
                packed["contacts"].append([named[f"th_inter_{k}_{v}"] for v in ("FNX", "FNY", "FNZ")])
                k += 1
            node_ids = next((g["objects"] for g in spec.get("groups") or [] if g["kind"] == "node"), [])
            first = node_ids[0] if node_ids else None
            packed["ax"] = named.get(f"th_node_{first}_AX")
            packed["ay"] = named.get(f"th_node_{first}_AY")
            packed["az"] = named.get(f"th_node_{first}_AZ")
        time = packed["time"]
        time_header = packed["time_header"]
        ie = packed["ie"] or ie
        ke = packed["ke"] or ke
        hg_e, rot_e, ext_w = packed["hg"], packed["rot"], packed["ext"]
        fnx, fny, fnz = packed["fnx"], packed["fny"], packed["fnz"]
        # FN* impuls (Radioss TH): kuvvet = dI/dt. 1.10–1.12a arası impuls
        # yanlışlıkla kuvvet diye raporlanıyordu (düz plato = momentum değişimi).
        if fnx and fny and fnz:
            force, impulse = impulse_components_to_force(time, [fnx, fny, fnz])
        elif packed["imp"]:
            force = [abs(v) for v in impulse_to_force(time, packed["imp"])]
        elif fnz:
            force, impulse = impulse_components_to_force(time, [fnz])
        for fx, fy, fz, *_ft in packed["contacts"]:
            contact_fn.append(impulse_components_to_force(time, [fx, fy, fz]))
        if packed["acc_g"] is not None:
            acc_g = list(packed["acc_g"])
        elif packed["ax"] and packed["ay"] and packed["az"]:
            acc_comp = (packed["ax"], packed["ay"], packed["az"])
            ax_g = _acc_to_g(packed["ax"], "ACCX")
            ay_g = _acc_to_g(packed["ay"], "ACCY")
            az_g = _acc_to_g(packed["az"], "ACCZ")
            acc_g = resultant_g(ax_g, ay_g, az_g)

    if listing.get("TIME") and not ie:
        time = listing["TIME"]
        ie = listing.get("IE") or []
        ke = listing.get("KE") or []

    diag, diag_scalars = _diagnostics(work_dir, out_path)
    if not time and not ie:
        return ResultSet(
            scalars=diag_scalars, curves={}, raw_result_path=work_dir, diagnostics=diag
        )

    time_s = _time_to_seconds(time, time_header) if time else []
    scalars: dict[str, float] = dict(diag_scalars)
    curves_extra: dict[str, list[float]] = {}
    if ie:
        scalars["internal_energy_final"] = float(ie[-1])
        scalars["internal_energy_max"] = float(max(ie))
    if ke:
        scalars["kinetic_energy_final"] = float(ke[-1])
        scalars["kinetic_energy_max"] = float(max(ke))
        if ie:
            # Toplam = IE + KE (+ dönme + hourglass − dış iş, sütun varsa).
            def total(i: int) -> float:
                e = ie[i] + ke[i]
                for extra, sign in ((rot_e, 1.0), (hg_e, 1.0), (ext_w, -1.0)):
                    if extra and len(extra) == len(ie):
                        e += sign * extra[i]
                return e

            e0, e1 = total(0), total(-1)
            # K4 — zorlanmış hızla sürülen koşuda KE₀ ≈ 0, e0 ≈ e1 ≈ 0: payda
            # sorunun enerji ölçeği (en büyük IE / KE / |dış iş|) — aksi halde
            # oran hep ~1 çıkıyordu (ROPS #85). Çarpma koşularında payda KE₀ kalır.
            scale = [abs(e0), abs(e1), max(ie), max(ke)]
            if ext_w and len(ext_w) == len(ie):
                scale.append(max(abs(v) for v in ext_w))
            denom = max(*scale, 1e-30)
            scalars["energy_balance_rel"] = abs(e1 - e0) / denom
    if hg_e and ie:
        scalars["hourglass_energy_final"] = float(hg_e[-1])
        if abs(ie[-1]) > 1e-30:
            scalars["hourglass_ratio"] = float(hg_e[-1]) / float(ie[-1])
    if force:
        scalars["rwall_force_max"] = float(max(abs(f) for f in force))
    if impulse:
        scalars["rwall_impulse_final"] = float(impulse[-1])
    for k, (fn, imp) in enumerate(contact_fn, start=1):
        if fn:
            scalars[f"contact_{k}_force_max"] = float(max(fn))
            scalars[f"contact_{k}_impulse_final"] = float(imp[-1])
    # 1.15c — kesit: TH birikimli impuls (RWALL gibi); global bileşen = FN + FT
    # (normal ayrımından bağımsız). Altısı da seçiliyse kuvvet = bileşen dI/dt.
    k = 1
    while f"th_sect_{k}_FNX" in named or f"th_sect_{k}_FTX" in named:
        comps = []
        for ax in ("X", "Y", "Z"):
            fn, ft = named.get(f"th_sect_{k}_FN{ax}"), named.get(f"th_sect_{k}_FT{ax}")
            comps.append([a + b for a, b in zip(fn, ft)] if fn and ft else None)
        if all(c is not None for c in comps) and time:
            sf, si = impulse_components_to_force(time, comps)
            curves_extra[f"section_{k}_force"] = sf
            curves_extra[f"section_{k}_impulse"] = si
            scalars[f"section_{k}_force_max"] = float(max(sf)) if sf else 0.0
            scalars[f"section_{k}_impulse_final"] = float(si[-1]) if si else 0.0
        k += 1
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
    if impulse:
        curves["rwall_impulse"] = impulse
    if acc_g:
        curves["acc_g"] = acc_g
    for k, (fn, imp) in enumerate(contact_fn, start=1):
        if fn:
            curves[f"contact_{k}_force"] = fn
            curves[f"contact_{k}_impulse"] = imp

    curves.update(named)
    curves.update(curves_extra)
    # 1.17h — hourglass enerjisi eğrisi (global sütun), grafikte IE / KE yanında
    if hg_e and len(hg_e) == len(time):
        curves["hourglass_energy"] = hg_e
    _apply_cfc(work_dir, time, time_header, curves, scalars, acc_comp, filters_override)
    if unmapped:
        diag["th_unmapped_groups"] = unmapped
    raw = csv_path or out_path or work_dir
    return ResultSet(scalars=scalars, curves=curves, raw_result_path=raw, diagnostics=diag)


def _find_csv(work_dir: Path) -> Path | None:
    hits = sorted(work_dir.glob("*T01*.csv")) + sorted(work_dir.glob("T01.csv"))
    if hits:
        return hits[0]
    return None


def _find_listing(work_dir: Path) -> Path | None:
    hits = sorted(work_dir.glob("*_0001.out")) + sorted(work_dir.glob("*.out"))
    return hits[0] if hits else None
