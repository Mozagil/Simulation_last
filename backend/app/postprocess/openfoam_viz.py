"""Alan görselleştirme verisi — Faz 2.8.

Çözüm sonunda ``vizSurfaces`` (raw) ve ``vizStreamLines`` (düz metin VTK)
fonksiyonlarının yazdığı dosyalar → arayüz için sade JSON:

- ``body``: gövde yüz merkezleri + p + Cp
- ``slice``: kesit düzlemi yüz merkezleri + |U| (+ düzlem içi iki eksen)
- ``streamlines``: çizgi başına noktalar + |U|

Cp = (p − p∞) / (½·ρ∞·U∞²). Sıkıştırılamazda p kinematik (p/ρ) olduğu için
Cp = p / (½·U∞²) (çıkış basıncı 0 referans). Nokta sayıları ``max_points`` ile
seyreltilir (eşit adım). Yalnız veri.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any


def _latest(dir_: Path) -> Path | None:
    if not dir_.is_dir():
        return None
    times = []
    for d in dir_.iterdir():
        try:
            times.append((float(d.name), d))
        except ValueError:
            continue
    return max(times)[1] if times else None


def read_raw(path: Path) -> list[list[float]]:
    """raw yüzey dosyası → satırlar (x y z değer…)."""
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        try:
            rows.append([float(t) for t in line.split()])
        except ValueError:
            continue
    return rows


def read_vtk_lines(path: Path) -> tuple[list[list[int]], list[tuple[float, float, float]], list[float]]:
    """Düz metin eski VTK POLYDATA → (çizgi başına nokta indisleri, noktalar, |U|)."""
    tokens = path.read_text(encoding="utf-8", errors="replace").split()
    i = tokens.index("POINTS")
    n = int(tokens[i + 1])
    vals = [float(t) for t in tokens[i + 3 : i + 3 + 3 * n]]
    pts = [(vals[3 * k], vals[3 * k + 1], vals[3 * k + 2]) for k in range(n)]
    lines: list[list[int]] = []
    if "LINES" in tokens:
        j = tokens.index("LINES")
        nl = int(tokens[j + 1])
        k = j + 3
        for _ in range(nl):
            cnt = int(tokens[k])
            lines.append([int(t) for t in tokens[k + 1 : k + 1 + cnt]])
            k += 1 + cnt
    speed = [0.0] * n
    for k in range(len(tokens) - 3):
        if tokens[k] == "U" and tokens[k + 1] == "3" and tokens[k + 2] == str(n):
            u = [float(t) for t in tokens[k + 4 : k + 4 + 3 * n]]
            speed = [math.sqrt(u[3 * m] ** 2 + u[3 * m + 1] ** 2 + u[3 * m + 2] ** 2) for m in range(n)]
            break
    return lines, pts, speed


def _thin(seq: list, max_n: int) -> list:
    if len(seq) <= max_n:
        return seq
    step = len(seq) / max_n
    return [seq[int(i * step)] for i in range(max_n)]


def build_fields(
    case_dir: Path,
    *,
    u_ref: float,
    p_ref: float,
    rho_ref: float,
    compressible: bool,
    max_points: int = 20000,
    max_track_points: int = 400,
) -> dict[str, Any]:
    root = Path(case_dir) / "postProcessing"
    out: dict[str, Any] = {"u_ref_m_s": u_ref, "p_ref": p_ref, "compressible": compressible}
    q = 0.5 * u_ref * u_ref * (rho_ref if compressible else 1.0)
    surf = _latest(root / "vizSurfaces")
    if surf is not None:
        if (surf / "p_body.raw").is_file():
            rows = _thin(read_raw(surf / "p_body.raw"), max_points)
            out["body"] = {
                "points": [[r[0], r[1], r[2]] for r in rows],
                "p": [r[3] for r in rows],
                "cp": [(r[3] - p_ref) / q if q > 0 else 0.0 for r in rows],
            }
        if (surf / "U_slice.raw").is_file():
            rows = _thin(read_raw(surf / "U_slice.raw"), max_points)
            out["slice"] = {
                "points": [[r[0], r[1], r[2]] for r in rows],
                "speed": [math.sqrt(r[3] ** 2 + r[4] ** 2 + r[5] ** 2) for r in rows],
            }
    tracks_dir = _latest(root / "sets" / "vizStreamLines")
    if tracks_dir is not None:
        lines_out = []
        for f in sorted(tracks_dir.glob("*.vtk")):
            lines, pts, speed = read_vtk_lines(f)
            for idx in lines:
                idx = _thin(idx, max_track_points)
                lines_out.append({"points": [list(pts[k]) for k in idx], "speed": [speed[k] for k in idx]})
        out["streamlines"] = lines_out
    return out
