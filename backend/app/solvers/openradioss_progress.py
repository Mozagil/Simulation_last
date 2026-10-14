"""OpenRadioss engine çıktısından crash ilerlemesi.

Engine stdout'u (1.23 D3, gerçek koşu çıktısı):
    NC=   37000 T= 1.9980E+01 DT= 5.3986E-04 ERR= -0.5% DM/M= 0.0000E+00
    ELAPSED TIME=         15.57 s  REMAINING TIME=          0.02 s
Eski / listing biçimi (`*_0001.out`): `CYCLE TIME TIME-STEP …` sütunları. Bitişteki CPU
zaman tablosu (`1  .2512E+02 .1815E+01 …`, baştaki sıfırsız Fortran sayıları) ilerleme
sayılmaz (eskiden "cycle 1 · Δt 1.8 ms" okunuyordu).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][-+]?\d+)?"
_NC_RE = re.compile(
    rf"NC=\s*(\d+)\s+T=\s*({_NUM})\s+DT=\s*({_NUM})(?:\s+ERR=\s*({_NUM})\s*%)?(?:\s+DM/M=\s*({_NUM}))?",
    re.IGNORECASE,
)
_TIMES_RE = re.compile(rf"ELAPSED TIME=\s*({_NUM})\s*s\s+REMAINING TIME=\s*({_NUM})\s*s", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedCrashProgress:
    cycle: int | None
    time_ms: float | None
    # None: bu satır yüzde taşımıyor (ör. ELAPSED / REMAINING satırı) — hub'daki değer kalır
    percent: float | None
    state: str
    message: str = ""
    # 1.23 D3: anlık zaman adımı (ms; deck birimi kg–mm–ms)
    dt_ms: float | None = None
    # 1.23 D3: eklenen kütle oranı DM/M (kütle ölçekleme)
    mass_added_rel: float | None = None
    # 1.23 D3: Radioss'un kendi yazdığı geçen / kalan süre (s)
    elapsed_s: float | None = None
    remaining_s: float | None = None


def _f(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        v = float(s.replace("D", "E").replace("d", "e"))
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _pct(time_ms: float, t_end_ms: float) -> float:
    return min(100.0, 100.0 * time_ms / (t_end_ms if t_end_ms > 0 else 1.0))


def parse_progress_line(line: str, t_end_ms: float) -> ParsedCrashProgress | None:
    raw = line.strip()
    if not raw:
        return None
    up = raw.upper()
    if "ERROR TERMINATION" in up or up.startswith("** ERROR"):
        return ParsedCrashProgress(None, None, 0.0, "failed", raw[:200])
    if "NORMAL TERMINATION" in up:
        return ParsedCrashProgress(None, t_end_ms, 100.0, "running", "normal termination")

    m = _NC_RE.search(raw)
    if m:
        time_ms = _f(m.group(2))
        if time_ms is None or time_ms < 0:
            return None
        dt = _f(m.group(3))
        return ParsedCrashProgress(
            int(m.group(1)),
            time_ms,
            _pct(time_ms, t_end_ms),
            "running",
            dt_ms=dt if dt is not None and dt > 0 else None,
            mass_added_rel=_f(m.group(5)),
        )

    m = _TIMES_RE.search(raw)
    if m:
        return ParsedCrashProgress(None, None, None, "running", elapsed_s=_f(m.group(1)), remaining_s=_f(m.group(2)))

    # listing sütun biçimi: CYCLE TIME TIME-STEP ELEMENT(tip) …
    parts = raw.split()
    if len(parts) < 2:
        return None
    try:
        cycle = int(parts[0])
        time_ms = float(parts[1])
    except ValueError:
        return None
    if cycle < 0 or time_ms < 0:
        return None
    if parts[1].startswith("."):
        return None  # CPU zaman tablosu (Fortran ".2512E+02" biçimi), ilerleme değil
    dt = _f(parts[2]) if len(parts) >= 3 else None
    return ParsedCrashProgress(
        cycle, time_ms, _pct(time_ms, t_end_ms), "running", dt_ms=dt if dt is not None and dt > 0 else None
    )


class ProgressStream:
    """Satır satır ilerleme; NORMAL / ERROR TERMINATION'dan sonraki satırlar yok sayılır."""

    def __init__(self, t_end_ms: float) -> None:
        self.t_end_ms = t_end_ms
        self.finished = False

    def feed(self, line: str) -> ParsedCrashProgress | None:
        if self.finished:
            return None
        parsed = parse_progress_line(line, self.t_end_ms)
        if parsed is not None and (parsed.state == "failed" or (parsed.cycle is None and parsed.percent == 100.0)):
            self.finished = True
        return parsed


def parse_progress_chunk(text: str, t_end_ms: float) -> ParsedCrashProgress | None:
    stream = ProgressStream(t_end_ms)
    last: ParsedCrashProgress | None = None
    for line in text.splitlines():
        parsed = stream.feed(line)
        if parsed is not None:
            last = parsed
    return last
