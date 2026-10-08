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
import subprocess
import time
import uuid
from collections.abc import Callable
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


class SolverLogStream:
    """Satır satır beslenen log okuyucu — canlı ilerleme (2.2) ve dosya için ortak.

    Bir iterasyonda aynı alan birden çok kez çözülürse (ör. p'nin
    düzeltici adımları) yalnız ilki alınır — residual grafiğinin olağan
    tanımı.
    """

    def __init__(self) -> None:
        self.log = SolverLog()
        self._seen: set[str] = set()
        self._fatal: list[str] = []
        self._in_fatal = False

    def feed(self, raw: str) -> bool:
        """Bir satır işler; yeni bir iterasyon başladıysa True döner."""
        log = self.log
        line = raw.strip()
        m = _TIME.match(line)
        if m:
            try:
                value = float(m.group(1))
            except ValueError:
                return False
            log.iterations.append(int(value) if value.is_integer() else value)
            self._seen = set()
            return True
        m = _RESIDUAL.search(line)
        if m and log.iterations:
            name = m.group(1)
            if name not in self._seen:
                self._seen.add(name)
                log.initial_residuals.setdefault(name, []).append(float(m.group(2)))
            return False
        if _CONVERGED.search(line):
            log.converged = True
        elif line == "End":
            log.finished = True
        elif "FOAM FATAL" in line:
            self._in_fatal = True
        if self._in_fatal:
            if line:
                self._fatal.append(line)
            elif len(self._fatal) > 1:
                self._in_fatal = False
            log.fatal_error = " ".join(self._fatal)[:500]
        return False


def parse_solver_log(text: str) -> SolverLog:
    """Log metninden iterasyonlar ve alan başına başlangıç residual'ları."""
    stream = SolverLogStream()
    for raw in text.splitlines():
        stream.feed(raw)
    return stream.log


class OpenFoamAdapter(SolverAdapter):
    """CFD solver (ESI OpenFOAM). ``InputArtifact`` bir case klasörüdür.

    2.1: ``build_input`` — parametrelerden ``0/``, ``constant/``, ``system/``.
    2.2: ``submit`` Docker'da koşturur, canlı residual ilerlemesi verir;
    ``parse_results`` residual geçmişi döner (kuvvet / Δp 2.4'te).
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

    def submit(
        self,
        artifact: InputArtifact,
        *,
        progress_cb: Callable[[SolverLog], None] | None = None,
        timeout_s: float | None = None,
    ) -> JobHandle:
        """Case'i Docker imajında koşturur (senkron; arka plan işi çağırır).

        ``system/blockMeshDict`` varsa önce ``blockMesh``; ardından
        ``controlDict``'teki ``application`` (ör. simpleFoam). Solver çıktısı
        satır satır okunur, her yeni iterasyonda ``progress_cb`` çağrılır ve
        ``log.<application>`` dosyasına yazılır.
        """
        image = resolve_openfoam_image()
        if image is None:
            raise SolverError("OpenFOAM yapılandırılmamış: OPENFOAM_DOCKER_IMAGE boş (bkz. .env.example).")
        case_dir = Path(artifact.path)
        app = case_application(case_dir)
        timeout = timeout_s if timeout_s is not None else float(os.environ.get("CFD_TIMEOUT_S") or 3600)
        script = (
            "set -o pipefail; "
            "if [ -f system/blockMeshDict ]; then blockMesh > log.blockMesh 2>&1 || "
            "{ echo 'FOAM FATAL ERROR: blockMesh başarısız (log.blockMesh)'; exit 3; }; fi; "
            f"{app} 2>&1 | tee log.{app}"
        )
        stream = SolverLogStream()
        proc = subprocess.Popen(
            docker_command(image, case_dir, script),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        deadline = time.monotonic() + timeout
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if stream.feed(line) and progress_cb is not None:
                    progress_cb(stream.log)
                if time.monotonic() > deadline:
                    proc.kill()
                    raise SolverError(f"OpenFOAM zaman aşımı ({timeout:.0f} s).")
            exit_code = proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
        if progress_cb is not None:
            progress_cb(stream.log)
        handle = JobHandle(job_id=str(uuid.uuid4()), work_dir=case_dir, artifact=artifact)
        handle._exit_code = exit_code  # type: ignore[attr-defined]
        handle._application = app  # type: ignore[attr-defined]
        if exit_code != 0:
            detail = stream.log.fatal_error or f"çıkış kodu {exit_code}"
            raise SolverError(f"OpenFOAM {app} hata: {detail}")
        return handle

    def poll_status(self, job: JobHandle) -> JobStatus:
        exit_code = getattr(job, "_exit_code", None)
        if exit_code is None:
            return JobStatus(state="pending")
        if exit_code == 0:
            return JobStatus(state="done", exit_code=0)
        return JobStatus(state="failed", exit_code=exit_code, message="OpenFOAM hata")

    def parse_results(self, job: JobHandle) -> ResultSet:
        """2.2: yalnız residual geçmişi ve yakınsama; kuvvet / Δp 2.4'te."""
        app = getattr(job, "_application", None) or case_application(job.work_dir)
        log_path = Path(job.work_dir) / f"log.{app}"
        if not log_path.is_file():
            raise SolverError(f"Solver log'u yok: {log_path}")
        res = residual_result(parse_solver_log(log_path.read_text(encoding="utf-8", errors="replace")), log_path)
        res.scalars.update(read_monitors(job.work_dir))
        return res


def _last_data_row(path: Path) -> list[str] | None:
    rows = [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip() and not ln.startswith("#")]
    return rows[-1].split("	") if rows else None


def read_monitors(case_dir: Path) -> dict[str, float]:
    """İzleme fonksiyonlarının son değerleri (case yazıcının ``functions`` bloğu).

    ``pAvg_<yama>`` → ``p_avg_<yama>`` (kinematik, m²/s²); ``uMax`` → ``u_max``.
    Yeniden başlatmada birden çok zaman klasörü olursa en sonuncusu okunur.
    """
    out: dict[str, float] = {}
    root = Path(case_dir) / "postProcessing"
    if not root.is_dir():
        return out
    for fo in sorted(root.iterdir()):
        times = sorted((d for d in fo.iterdir() if d.is_dir()), key=lambda d: float(d.name) if _is_float(d.name) else -1.0)
        if not times:
            continue
        latest = times[-1]
        if fo.name.startswith("pAvg_"):
            f = latest / "surfaceFieldValue.dat"
            row = _last_data_row(f) if f.is_file() else None
            if row and len(row) >= 2:
                out[f"p_avg_{fo.name[5:]}"] = float(row[1])
        elif fo.name == "uMax":
            f = latest / "fieldMinMax.dat"
            row = _last_data_row(f) if f.is_file() else None
            if row and len(row) >= 5:
                out["u_max"] = float(row[4])
    return out


def _is_float(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def case_application(case_dir: Path) -> str:
    """``system/controlDict`` → ``application`` (ör. simpleFoam)."""
    path = Path(case_dir) / "system" / "controlDict"
    if not path.is_file():
        raise SolverError(f"controlDict yok: {path}")
    m = re.search(r"^\s*application\s+(\w+)\s*;", path.read_text(encoding="utf-8", errors="replace"), re.M)
    if not m:
        raise SolverError("controlDict'te application tanımı yok.")
    return m.group(1)


def residual_result(log: SolverLog, log_path: Path | None = None) -> ResultSet:
    """Log özeti → ResultSet (skalerler: iterasyon, yakınsama, son residual'lar)."""
    scalars: dict[str, float] = {
        "iterations": float(log.last_iteration or 0),
        "converged": 1.0 if log.converged else 0.0,
    }
    for name, values in log.initial_residuals.items():
        if values:
            scalars[f"residual_final_{name}"] = values[-1]
    return ResultSet(
        scalars=scalars,
        curves={"iteration": list(log.iterations), "residuals": {k: list(v) for k, v in log.initial_residuals.items()}},
        raw_result_path=log_path,
        diagnostics={"finished": log.finished, "fatal_error": log.fatal_error},
    )
