"""Crash job ilerleme (in-memory). Durability `/solve` kuyruğuna bağlanmaz.

1.7 `submit` bu hub'a yazar; 1.6 websocket/GET buradan okur.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import asdict, dataclass


@dataclass
class JobProgress:
    job_id: str
    kind: str = "crash"
    state: str = "pending"  # pending | running | done | failed
    percent: float = 0.0
    cycle: int | None = None
    time_ms: float | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ProgressHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobProgress] = {}
        self._events: dict[str, list[asyncio.Event]] = {}

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._events.clear()

    def create(self, job_id: str) -> JobProgress:
        with self._lock:
            job = JobProgress(job_id=job_id)
            self._jobs[job_id] = job
            return job

    def get(self, job_id: str) -> JobProgress | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return JobProgress(**asdict(job)) if job else None

    def update(
        self,
        job_id: str,
        *,
        state: str | None = None,
        percent: float | None = None,
        cycle: int | None = None,
        time_ms: float | None = None,
        message: str | None = None,
    ) -> JobProgress:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                job = JobProgress(job_id=job_id)
                self._jobs[job_id] = job
            if state is not None:
                job.state = state
            if percent is not None:
                job.percent = max(0.0, min(100.0, float(percent)))
            if cycle is not None:
                job.cycle = cycle
            if time_ms is not None:
                job.time_ms = time_ms
            if message is not None:
                job.message = message
            snapshot = JobProgress(**asdict(job))
            waiters = list(self._events.get(job_id, ()))
        for ev in waiters:
            ev.set()
        return snapshot

    async def wait(self, job_id: str, timeout: float = 1.0) -> None:
        ev = asyncio.Event()
        with self._lock:
            self._events.setdefault(job_id, []).append(ev)
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
        except TimeoutError:
            pass
        finally:
            with self._lock:
                lst = self._events.get(job_id, [])
                if ev in lst:
                    lst.remove(ev)


_HUB = ProgressHub()


def get_hub() -> ProgressHub:
    return _HUB
