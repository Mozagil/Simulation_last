"""OpenRadioss engine listing satırından crash ilerleme yüzdesi."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedCrashProgress:
    cycle: int | None
    time_ms: float | None
    percent: float
    state: str
    message: str = ""


def parse_progress_line(line: str, t_end_ms: float) -> ParsedCrashProgress | None:
    raw = line.strip()
    if not raw:
        return None
    up = raw.upper()
    if "ERROR TERMINATION" in up or up.startswith("** ERROR"):
        return ParsedCrashProgress(None, None, 0.0, "failed", raw[:200])
    if "NORMAL TERMINATION" in up:
        return ParsedCrashProgress(None, t_end_ms, 100.0, "running", "normal termination")
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
    denom = t_end_ms if t_end_ms > 0 else 1.0
    percent = min(100.0, 100.0 * time_ms / denom)
    return ParsedCrashProgress(cycle, time_ms, percent, "running")


def parse_progress_chunk(text: str, t_end_ms: float) -> ParsedCrashProgress | None:
    last: ParsedCrashProgress | None = None
    for line in text.splitlines():
        parsed = parse_progress_line(line, t_end_ms)
        if parsed is not None:
            last = parsed
    return last
