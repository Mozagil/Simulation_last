"""Project Chrono (PyChrono) MBD adaptörü — Faz 5.0 iskelet.

Kullanıcı kararı (2026-10-22): MBD katmanı Project Chrono; conda bağımlılığı
nedeniyle **ayrı worker ortamında** koşar. Bu süreç (FastAPI) PyChrono'yu import
etmez; `CHRONO_PYTHON` (conda env python'u) ile subprocess ya da
`CHRONO_DOCKER_IMAGE` ile `docker run` kullanır. Worker betiği
`backend/scripts/chrono_run.py`.

İlk senaryo: çeyrek araç tümsek geçişi (sprung kütle + yay/sönüm + tekerlek
kütlesi + lastik rijitliği, yol profili). Çıktı `results.csv` zaman serileri →
`ResultSet` (eğriler + tepe / RMS skalerler). Öneri / kabul eşiği yok.
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.solvers.base import (
    InputArtifact,
    JobHandle,
    JobStatus,
    ResultSet,
    SolverAdapter,
    SolverError,
)

CASE_FILE = "chrono_case.json"
RESULTS_FILE = "results.csv"
SUMMARY_FILE = "summary.json"
LOG_FILE = "chrono.log"
WORK_DIR = "/work"
RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "chrono_run.py"


class RoadBump(BaseModel):
    """Yol profili: tek tümsek (kosinüs). mm / m cinsinden."""

    kind: str = Field(default="cosine_bump", description="cosine_bump | step")
    height_mm: float = Field(default=50.0, ge=0)
    length_m: float = Field(default=1.0, gt=0)
    start_m: float = Field(default=2.0, ge=0)


class ChronoQuarterCarParams(BaseModel):
    """Çeyrek araç (2 serbestlik): sprung kütle m_s, tekerlek kütlesi m_u, süspansiyon k_s / c_s,
    lastik k_t; sabit hız v ile yol profili. Birimler SI (kg, N/m, N·s/m, m/s)."""

    scenario: str = Field(default="quarter_car_bump")
    sprung_mass_kg: float = Field(default=400.0, gt=0)
    unsprung_mass_kg: float = Field(default=40.0, gt=0)
    suspension_k_n_per_m: float = Field(default=20000.0, gt=0)
    suspension_c_n_s_per_m: float = Field(default=1500.0, ge=0)
    tire_k_n_per_m: float = Field(default=180000.0, gt=0)
    speed_m_s: float = Field(default=10.0, gt=0)
    road: RoadBump = Field(default_factory=RoadBump)
    t_end_s: float = Field(default=3.0, gt=0, le=60)
    dt_s: float = Field(default=1e-3, gt=0, le=0.1)
    output_every: int = Field(default=1, ge=1, description="her n adımda bir satır")

    @model_validator(mode="after")
    def _finite(self) -> "ChronoQuarterCarParams":
        for name in ("sprung_mass_kg", "unsprung_mass_kg", "suspension_k_n_per_m", "suspension_c_n_s_per_m",
                     "tire_k_n_per_m", "speed_m_s", "t_end_s", "dt_s"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} sonlu olmalı")
        if self.scenario != "quarter_car_bump":
            raise ValueError("5.0'da yalnız quarter_car_bump senaryosu var.")
        return self


def resolve_chrono_runtime() -> tuple[str, str] | None:
    """("python", yol) | ("docker", imaj) | None (Chrono yapılandırılmamış)."""
    py = (os.environ.get("CHRONO_PYTHON") or "").strip()
    if py:
        return ("python", py)
    image = (os.environ.get("CHRONO_DOCKER_IMAGE") or "").strip()
    if image:
        return ("docker", image)
    return None


def run_command(runtime: tuple[str, str], case_dir: Path) -> list[str]:
    kind, target = runtime
    if kind == "python":
        return [target, str(RUNNER), str(Path(case_dir).resolve())]
    docker = shutil.which("docker") or "docker"
    return [
        docker, "run", "--rm",
        "-v", f"{Path(case_dir).resolve()}:{WORK_DIR}",
        "-v", f"{RUNNER.resolve()}:/runner/chrono_run.py:ro",
        target, "python", "/runner/chrono_run.py", WORK_DIR,
    ]


class ChronoAdapter(SolverAdapter):
    def __init__(self, work_root: Path | None = None) -> None:
        self.work_root = Path(work_root) if work_root else Path("uploads") / "chrono_jobs"

    # --- girdi ---------------------------------------------------------
    def build_input(self, params: dict[str, Any]) -> InputArtifact:
        try:
            p = ChronoQuarterCarParams.model_validate(params)
        except ValidationError as e:
            raise SolverError(f"Chrono parametreleri geçersiz: {e}") from e
        job_id = params.get("job_id") or uuid.uuid4().hex[:12]
        case_dir = self.work_root / str(job_id)
        case_dir.mkdir(parents=True, exist_ok=True)
        case = {"schema": "chrono_case/1", "job_id": str(job_id), "params": p.model_dump(),
                "outputs": {"csv": RESULTS_FILE, "summary": SUMMARY_FILE}}
        (case_dir / CASE_FILE).write_text(json.dumps(case, indent=2), encoding="utf-8")
        return InputArtifact(path=case_dir, kind="directory")

    # --- koşu ----------------------------------------------------------
    def submit(self, artifact: InputArtifact, *, timeout_s: float = 600.0) -> JobHandle:
        case_dir = Path(artifact.path)
        runtime = resolve_chrono_runtime()
        if runtime is None:
            raise SolverError("Chrono yapılandırılmamış: CHRONO_PYTHON ya da CHRONO_DOCKER_IMAGE gerekli (.env.example).")
        cmd = run_command(runtime, case_dir)
        job_id = json.loads((case_dir / CASE_FILE).read_text(encoding="utf-8"))["job_id"]
        log = case_dir / LOG_FILE
        try:
            with log.open("w", encoding="utf-8") as fh:
                proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired as e:
            raise SolverError(f"Chrono zaman aşımı ({timeout_s:.0f} s)") from e
        except FileNotFoundError as e:
            raise SolverError(f"Chrono komutu bulunamadı: {cmd[0]}") from e
        (case_dir / "exit_code").write_text(str(proc.returncode), encoding="utf-8")
        return JobHandle(job_id=str(job_id), work_dir=case_dir, artifact=artifact)

    def poll_status(self, job: JobHandle) -> JobStatus:
        ec = job.work_dir / "exit_code"
        if not ec.exists():
            return JobStatus(state="pending")
        code = int(ec.read_text(encoding="utf-8").strip() or "1")
        if code == 0 and (job.work_dir / RESULTS_FILE).exists():
            return JobStatus(state="done", exit_code=0)
        tail = ""
        logp = job.work_dir / LOG_FILE
        if logp.exists():
            tail = "\n".join(logp.read_text(encoding="utf-8", errors="replace").splitlines()[-20:])
        return JobStatus(state="failed", message=tail, exit_code=code)

    # --- sonuç ---------------------------------------------------------
    def parse_results(self, job: JobHandle) -> ResultSet:
        return parse_results_csv(job.work_dir / RESULTS_FILE, job.work_dir / SUMMARY_FILE)


def parse_results_csv(csv_path: Path, summary_path: Path | None = None) -> ResultSet:
    """`results.csv` (ilk sütun time_s) → eğriler + skalerler.

    Skalerler sütun adından türetilir: `<ad>_max`, `<ad>_min`, `<ad>_rms`. Yorum yok.
    """
    if not csv_path.exists():
        raise SolverError(f"Chrono sonucu yok: {csv_path}")
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 2 or not rows[0] or rows[0][0] != "time_s":
        raise SolverError("results.csv: başlık 'time_s' ile başlamalı ve en az bir satır olmalı.")
    header = rows[0]
    cols: dict[str, list[float]] = {h: [] for h in header}
    for r in rows[1:]:
        if len(r) != len(header):
            continue
        for h, v in zip(header, r):
            cols[h].append(float(v))
    curves: dict[str, Any] = {"time": cols["time_s"]}
    scalars: dict[str, float] = {}
    for h, vals in cols.items():
        if h == "time_s" or not vals:
            continue
        curves[h] = vals
        arr = [v for v in vals if math.isfinite(v)]
        if not arr:
            continue
        scalars[f"{h}_max"] = max(arr)
        scalars[f"{h}_min"] = min(arr)
        scalars[f"{h}_rms"] = math.sqrt(sum(v * v for v in arr) / len(arr))
    diagnostics: dict[str, Any] = {"n_rows": len(cols["time_s"]), "columns": [h for h in header if h != "time_s"]}
    if summary_path is not None and summary_path.exists():
        try:
            diagnostics["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            diagnostics["summary_error"] = "summary.json okunamadı"
    return ResultSet(scalars=scalars, curves=curves, raw_result_path=csv_path, diagnostics=diagnostics)
