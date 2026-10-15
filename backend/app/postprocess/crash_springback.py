"""1.24c1 — geri sekme (springback) metrikleri, animasyon karelerinden.

Explicit devam yaklaşımı: koşu çarpıcı geri sekip temas kesilene kadar sürdürülür
(süre mühendisin); burada yalnız kareler okunur. `/IMPL/SPRBACK` (implicit) ayrı faz.

İki tanım yan yana (kullanıcı kararı D, 2026-10-15); kare başına:

- mutlak: |u|max(t) — parçaya ait düğümlerin yer değiştirme büyüklüğünün en büyüğü
  (Radioss `Displacement`, ilk konuma göre — rijit öteleme dahil). Tabanı sabit parçada
  doğrudan deformasyon; serbest hareket eden parçada ötelemeyi ölçer.
  Anahtarlar: `model_disp_*`, `springback_mm/_ratio`, `part_<id>_disp_*`, `part_<id>_springback_*`.
- öteleme çıkarılmış: |u − ū|max(t), ū = o karede parçanın düğümlerinin ortalama yer
  değiştirmesi (rijit öteleme gider, rijit dönme kalır). Model değeri parçaların en büyüğü.
  Anahtarlar: `model_def_*`, `springback_def_mm/_ratio`, `part_<id>_def_*`, `part_<id>_springback_def_*`.

Her biri için: tepe ve zamanı, son kare, geri sekme = tepe − son, oranı = geri sekme / tepe
(tepe 0 ise oran yok). Rijit duvarın sentetik noktaları (NODE_ID = 0) ve hiçbir hücreye ait
olmayan düğümler (ör. rijit gövde ana düğümü) sayılmaz. Yorum yok, veri.
"""

from __future__ import annotations

import math
from typing import Any

from app.postprocess.openradioss_anim import parse_vtk_ascii

_SKIP_TYPES = {1, 2, 3}  # VTK vertex / poly-vertex / line — kiriş, yay, duvar çizgisi


def _node_parts(frame: dict[str, Any]) -> dict[int, set[int]]:
    """Düğüm indeksi → ait olduğu parça no'ları (ilk kareden; topoloji sabit)."""
    part = frame["cell_data"].get("PART_ID") or [0] * len(frame["cells"])
    nid = frame["point_data"].get("NODE_ID")
    out: dict[int, set[int]] = {}
    for ci, (conn, t) in enumerate(zip(frame["cells"], frame["cell_types"])):
        if t in _SKIP_TYPES:
            continue
        if nid and any(int(nid[v]) == 0 for v in conn):
            continue  # rijit duvar dörtgeni
        p = int(part[ci])
        for v in conn:
            out.setdefault(v, set()).add(p)
    return out


def _metrics(series: list[tuple[float, float]], kind: str) -> dict[str, float]:
    """[(t, değer)] → `<kind>_peak_mm`, `_peak_t_ms`, `_final_mm`; `springback(_def)_mm/_ratio`."""
    fin = [(t, u) for t, u in series if math.isfinite(u)]
    if not fin:
        return {}
    t_peak, peak = max(fin, key=lambda p: p[1])
    final = fin[-1][1]
    sb = "springback" if kind == "disp" else f"springback_{kind}"
    out = {
        f"{kind}_peak_mm": peak,
        f"{kind}_peak_t_ms": t_peak,
        f"{kind}_final_mm": final,
        f"{sb}_mm": peak - final,
    }
    if peak > 0:
        out[f"{sb}_ratio"] = (peak - final) / peak
    return out


def _frame_maxima(disp: list[list[float]], members: dict[int, list[int]]) -> tuple[dict[int, float], dict[int, float]]:
    """Bir kare: parça → (mutlak |u|max, öteleme çıkarılmış |u − ū|max)."""
    absm: dict[int, float] = {}
    defm: dict[int, float] = {}
    for p, nodes in members.items():
        vs = [disp[v] for v in nodes if v < len(disp) and all(math.isfinite(c) for c in disp[v])]
        if not vs:
            absm[p] = defm[p] = -math.inf
            continue
        mean = [sum(d[i] for d in vs) / len(vs) for i in range(3)]
        absm[p] = max(math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2) for d in vs)
        defm[p] = max(
            math.sqrt((d[0] - mean[0]) ** 2 + (d[1] - mean[1]) ** 2 + (d[2] - mean[2]) ** 2) for d in vs
        )
    return absm, defm


def springback_scalars(frames: list[dict[str, Any]]) -> dict[str, float]:
    """Ayrıştırılmış VTK kareleri (`parse_vtk_ascii`) → skalerler (modül açıklamasındaki adlar).

    Kare yoksa ya da `Displacement` yazılmamışsa boş sözlük.
    """
    frames = [f for f in frames if f.get("points") and f["point_data"].get("Displacement")]
    if not frames:
        return {}
    owner = _node_parts(frames[0])
    members: dict[int, list[int]] = {}
    for v, ps in owner.items():
        for p in ps:
            members.setdefault(p, []).append(v)
    parts = sorted(members)
    series: dict[str, dict[int | None, list[tuple[float, float]]]] = {"disp": {}, "def": {}}
    for k, f in enumerate(frames):
        t = f["time"] if f["time"] is not None else float(k)
        absm, defm = _frame_maxima(f["point_data"]["Displacement"], members)
        for kind, m in (("disp", absm), ("def", defm)):
            for p in parts:
                series[kind].setdefault(p, []).append((t, m[p]))
            series[kind].setdefault(None, []).append((t, max(m.values(), default=-math.inf)))

    out: dict[str, float] = {}
    for kind in ("disp", "def"):
        for k, v in _metrics(series[kind][None], kind).items():
            out[k if k.startswith("springback") else f"model_{k}"] = v
        for p in parts:
            for k, v in _metrics(series[kind][p], kind).items():
                out[f"part_{p}_{k}"] = v
    return out


def springback_from_vtk_texts(texts: list[str]) -> dict[str, float]:
    """anim_to_vtk ASCII metinleri (kare sırasıyla) → skalerler."""
    return springback_scalars([parse_vtk_ascii(t) for t in texts])
