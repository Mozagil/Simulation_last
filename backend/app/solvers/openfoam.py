"""OpenFOAM (ESI, openfoam.com) çalışma ortamı — Faz 2.0 altyapısı.

Kullanıcı kararı (2026-10-08): dağıtım ESI; resmi Docker imajı
``opencfd/openfoam-default`` (GPL). OpenFOAM yalnız sunucu tarafında, bir
Docker imajında koşar; kullanıcının makinesinde kurulu olduğu varsayılmaz.

Bu modül şimdilik yalnız çalışma ortamını içerir: imaj çözümü, ``docker run``
komutu ve solver log'undan iterasyon / başlangıç residual'ları. ``OpenFoamAdapter.build_input`` (2.1) case klasörünü
``app.solvers.openfoam_case`` ile yazar; koşu 2.2'de, sonuç okuma 2.4'te gelir.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.solvers.base import (
    InputArtifact,
    JobHandle,
    JobStatus,
    ResultSet,
    SolverAdapter,
    SolverError,
)

DEFAULT_IMAGE = "opencfd/openfoam-default:2412"
WORK_DIR = "/work"


def resolve_openfoam_image() -> str | None:
    """OPENFOAM_DOCKER_IMAGE; boşsa None (OpenFOAM yapılandırılmamış)."""
    image = (os.environ.get("OPENFOAM_DOCKER_IMAGE") or "").strip()
    return image or None


def docker_command(image: str, case_dir: Path, script: str) -> list[str]:
    """Case klasörünü /work'e bağlayıp imajda bir kabuk betiği koşturur.

    ESI imajının giriş noktası (``/openfoam/run``) OpenFOAM ortamını
    (``etc/bashrc``) yükler; komutlar ``bash -c`` ile verilir.
    """
    docker = shutil.which("docker") or "docker"
    return [
        docker,
        "run",
        "--rm",
        "-v",
        f"{Path(case_dir).resolve()}:{WORK_DIR}",
        "-w",
        WORK_DIR,
        image,
        "bash",
        "-c",
        f"cd {WORK_DIR} && {script}",
    ]


@dataclass
class SolverLog:
    """Bir OpenFOAM solver log'unun özeti (ör. simpleFoam)."""

    iterations: list[int] = field(default_factory=list)
    #: alan adı → her iterasyondaki ilk "Initial residual" değeri
    initial_residuals: dict[str, list[float]] = field(default_factory=dict)
    converged: bool = False
    finished: bool = False
    fatal_error: str | None = None

    @property
    def last_iteration(self) -> int | None:
        return self.iterations[-1] if self.iterations else None


_TIME = re.compile(r"^Time = (\S+)\s*$")
_RESIDUAL = re.compile(
    r"Solving for (\w+), Initial residual = ([0-9.eE+-]+), Final residual = ([0-9.eE+-]+), No Iterations (\d+)"
)
_CONVERGED = re.compile(r"(solution converged|reached convergence) in \d+ iterations")


def parse_solver_log(text: str) -> SolverLog:
    """Log metninden iterasyonlar ve alan başına başlangıç residual'ları.

    Bir iterasyonda aynı alan birden çok kez çözülürse (ör. p'nin
    düzeltici adımları) yalnız ilki alınır — residual grafiğinin olağan
    tanımı.
    """
    log = SolverLog()
    seen: set[str] = set()
    fatal: list[str] = []
    in_fatal = False
    for raw in text.splitlines():
        line = raw.strip()
        m = _TIME.match(line)
        if m:
            try:
                log.iterations.append(int(float(m.group(1))))
            except ValueError:
                continue
            seen = set()
            continue
        m = _RESIDUAL.search(line)
        if m and log.iterations:
            name = m.group(1)
            if name not in seen:
                seen.add(name)
                log.initial_residuals.setdefault(name, []).append(float(m.group(2)))
            continue
        if _CONVERGED.search(line):
            log.converged = True
        elif line == "End":
            log.finished = True
        elif "FOAM FATAL" in line:
            in_fatal = True
        if in_fatal:
            if line:
                fatal.append(line)
            elif len(fatal) > 1:
                in_fatal = False
    if fatal:
        log.fatal_error = " ".join(fatal)[:500]
    return log


class OpenFoamAdapter(SolverAdapter):
    """CFD solver (ESI OpenFOAM). ``InputArtifact`` bir case klasörüdür.

    2.1: ``build_input`` — parametrelerden ``0/``, ``constant/``, ``system/``.
    Koşu (``submit`` / ``poll_status``) 2.2'de, sonuç okuma 2.4'te gelir.
    """

    def build_input(self, params: dict[str, Any]) -> InputArtifact:
        from app.solvers.openfoam_case import CfdCaseParams, write_case

        case_dir = Path(params["output_dir"])
        try:
            case = CfdCaseParams.model_validate(params.get("case") or {})
        except ValidationError as exc:
            raise SolverError(f"OpenFOAM case parametreleri geçersiz: {exc}") from exc
        case_dir.mkdir(parents=True, exist_ok=True)
        write_case(case, case_dir)
        return InputArtifact(path=case_dir, kind="directory")

    def submit(self, artifact: InputArtifact) -> JobHandle:
        raise SolverError("OpenFOAM koşusu Faz 2.2'de eklenecek.")

    def poll_status(self, job: JobHandle) -> JobStatus:
        raise SolverError("OpenFOAM koşusu Faz 2.2'de eklenecek.")

    def parse_results(self, job: JobHandle) -> ResultSet:
        raise SolverError("OpenFOAM sonuç okuma Faz 2.4'te eklenecek.")
