"""OpenRadioss solver adaptörü — Faz 1 crash (CalculiX'ten bağımsız).

Starter (`_0000.rad`) + engine (`_0001.rad`). Mesh: `params["nodes"]`/`tets`
veya mevcut Gmsh `.msh` (`mesh_path`). Bariyer: `params["barrier"]`
(`CrashBarrierParams`) → `/INIVEL` + `/RWALL`. `generate_mesh` / `/solve`
dokunulmaz. `submit` ikili yoksa SolverError.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
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
from app.solvers.crash_params import CrashModelParams

# Codespace Dockerfile bu etiketi indirir (reproducible). Kaynak derlenmez.
OPENRADIOSS_RELEASE = "latest-20260728"
OPENRADIOSS_LINUX_ZIP = (
    "https://github.com/OpenRadioss/OpenRadioss/releases/download/"
    f"{OPENRADIOSS_RELEASE}/OpenRadioss_linux64.zip"
)

_ENGINE_NAMES = (
    "engine_linux64_gf",
    "engine_win64.exe",
    "engine_win64",
    "engine_openradioss",
    "engine_openradioss.exe",
)
_STARTER_NAMES = (
    "starter_linux64_gf",
    "starter_win64.exe",
    "starter_win64",
    "starter_openradioss",
    "starter_openradioss.exe",
)


@dataclass(frozen=True)
class OpenRadiossBins:
    engine: Path
    starter: Path | None
    home: Path | None


def _install_roots() -> list[Path]:
    roots: list[Path] = []
    home_env = os.environ.get("OPENRADIOSS_HOME")
    if home_env:
        roots.append(Path(home_env))
    path_env = os.environ.get("OPENRADIOSS_PATH")
    if path_env:
        p = Path(path_env)
        roots.append(p if p.is_dir() else p.parent)
    roots.append(Path("/opt/openradioss"))
    vendor = Path(__file__).resolve().parent.parent.parent / "vendor" / "openradioss"
    roots.append(vendor)
    return roots


def _first_named(directory: Path, names: tuple[str, ...]) -> Path | None:
    if not directory.is_dir():
        return None
    for name in names:
        cand = directory / name
        if cand.is_file():
            return cand
    exec_dir = directory / "exec"
    if exec_dir.is_dir() and exec_dir != directory:
        return _first_named(exec_dir, names)
    return None


def _home_from_engine(engine: Path) -> Path | None:
    parent = engine.parent
    if parent.name == "exec":
        return parent.parent
    cfg = parent / "hm_cfg_files"
    if cfg.is_dir():
        return parent
    return parent


def resolve_openradioss() -> OpenRadiossBins | None:
    """OPENRADIOSS_PATH dosya veya kök dizin olabilir (resmi değişken = kök)."""
    explicit = os.environ.get("OPENRADIOSS_PATH")
    engine: Path | None = None
    if explicit:
        p = Path(explicit)
        if p.is_file():
            engine = p
        elif p.is_dir():
            engine = _first_named(p, _ENGINE_NAMES)
    if engine is None:
        for name in _ENGINE_NAMES:
            found = shutil.which(name)
            if found:
                engine = Path(found)
                break
    if engine is None:
        for root in _install_roots():
            engine = _first_named(root, _ENGINE_NAMES)
            if engine is not None:
                break
    if engine is None:
        return None
    home = _home_from_engine(engine)
    starter = _first_named(engine.parent, _STARTER_NAMES)
    if starter is None and home is not None:
        starter = _first_named(home, _STARTER_NAMES)
    return OpenRadiossBins(engine=engine, starter=starter, home=home)


def _engine_executable() -> str | None:
    bins = resolve_openradioss()
    return None if bins is None else str(bins.engine)


def runtime_env(bins: OpenRadiossBins) -> dict[str, str]:
    """RAD_CFG_PATH / LD_LIBRARY_PATH — resmi OpenRadioss INSTALL.md."""
    env = os.environ.copy()
    home = bins.home
    if home is None:
        env.setdefault("OMP_STACKSIZE", "400m")
        return env
    env["RAD_CFG_PATH"] = str(home / "hm_cfg_files")
    linux_hm = home / "extlib" / "hm_reader" / "linux64"
    win_hm = home / "extlib" / "hm_reader" / "win64"
    if linux_hm.is_dir():
        env["RAD_H3D_PATH"] = str(home / "extlib" / "h3d" / "lib" / "linux64")
        extra = os.pathsep.join(
            str(p)
            for p in (
                linux_hm,
                home / "extlib" / "h3d" / "lib" / "linux64",
            )
            if p.is_dir()
        )
        env["LD_LIBRARY_PATH"] = extra + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    elif win_hm.is_dir():
        env["RAD_H3D_PATH"] = str(home / "extlib" / "h3d" / "lib" / "win64")
        extra = os.pathsep.join(
            str(p)
            for p in (
                win_hm,
                home / "extlib" / "h3d" / "lib" / "win64",
                home / "extlib" / "intelOneAPI_runtime" / "win64",
            )
            if p.is_dir()
        )
        env["PATH"] = extra + os.pathsep + env.get("PATH", "")
    env.setdefault("OMP_STACKSIZE", "400m")
    return env


def _f(value: float) -> str:
    return f"{float(value):20.8g}"


def _i(value: int, width: int = 10) -> str:
    return f"{int(value):{width}d}"


def _crash_model(params: dict[str, Any]) -> CrashModelParams:
    raw = params.get("model")
    if raw is None:
        return CrashModelParams()
    if isinstance(raw, CrashModelParams):
        return raw
    try:
        return CrashModelParams.model_validate(raw)
    except ValidationError as exc:
        raise SolverError(f"OpenRadioss model geçersiz: {exc}") from exc


def _mat_prop_cards(mat: dict[str, Any], model: CrashModelParams) -> list[str]:
    # mm–ms–ton: rho [kg/m³] → ton/mm³ = kg/m³ * 1e-12
    rho = float(mat.get("density") or 7850.0) * 1e-12
    e_mpa = float(mat.get("youngs_modulus") or 210e9) / 1e6
    nu = float(mat.get("poisson_ratio") or 0.3)
    title = str(mat.get("name") or "STEEL")[:80]
    if model.law == "plastic":
        sy = model.sigma_y_pa
        if sy is None:
            raw_y = mat.get("yield_strength")
            sy = float(raw_y) if raw_y is not None else None
        if sy is None or sy <= 0:
            raise SolverError(
                "LAW2 için σy gerekli: malzeme yield_strength veya model.sigma_y_pa."
            )
        a_mpa = float(sy) / 1e6
        mat_lines = [
            "/MAT/LAW2/1",
            title,
            _f(rho),
            f"{_f(e_mpa)}{_f(nu)}",
            f"{_f(a_mpa)}{_f(model.harden_b_mpa)}{_f(model.harden_n)}",
        ]
    else:
        mat_lines = [
            "/MAT/LAW1/1",
            title,
            _f(rho),
            f"{_f(e_mpa)}{_f(nu)}",
        ]
    prop_lines = [
        "/PROP/TYPE14/1",
        "solid",
        f"{_i(model.isolid)}{_i(model.ismstr)}{_i(0)}{_i(0)}{_i(model.nip)}",
    ]
    return mat_lines + prop_lines


def _write_starter(path: Path, params: dict[str, Any]) -> None:
    title = str(params.get("title") or "crash")[:80]
    nodes = params.get("nodes") or []
    tets = params.get("tets") or []
    bricks = params.get("bricks") or []
    mats = params.get("materials") or [
        {
            "name": "STEEL",
            "density": 7850.0,
            "youngs_modulus": 210e9,
            "poisson_ratio": 0.3,
        }
    ]
    vel = params.get("initial_velocity") or {"vx": 0.0, "vy": 0.0, "vz": -5000.0}
    wall = params.get("rigid_wall") or {
        "point": [0.0, 0.0, 0.0],
        "normal": [0.0, 0.0, 1.0],
    }
    mat = mats[0]
    model = _crash_model(params)

    lines: list[str] = [
        "#RADIOSS STARTER",
        "/BEGIN",
        title,
        f"{_i(2022)}{_i(0)}",
        f"{_i(0)}{_i(0)}",
        "/UNIT/LENGTH",
        "mm",
        "/UNIT/MASS",
        "kg",
        "/UNIT/TIME",
        "ms",
        "/NODE",
    ]
    for n in nodes:
        nid = int(n["id"] if isinstance(n, dict) else n[0])
        x, y, z = (
            (float(n["x"]), float(n["y"]), float(n["z"]))
            if isinstance(n, dict)
            else (float(n[1]), float(n[2]), float(n[3]))
        )
        lines.append(f"{_i(nid)}{_f(x)}{_f(y)}{_f(z)}")

    if tets:
        lines.append("/TETRA4/1/1")
        for el in tets:
            eid, n1, n2, n3, n4 = (int(v) for v in el)
            lines.append(f"{_i(eid)}{_i(n1)}{_i(n2)}{_i(n3)}{_i(n4)}")
    if bricks:
        lines.append("/BRICK/1/1")
        for el in bricks:
            vals = [int(v) for v in el]
            lines.append("".join(_i(v) for v in vals))

    lines.extend(_mat_prop_cards(mat, model))
    lines.extend(
        [
            "/PART/1",
            "part",
            f"{_i(1)}{_i(1)}",
            "/GRNOD/NODE/1",
            "all_nodes",
        ]
    )
    ids = [int(n["id"] if isinstance(n, dict) else n[0]) for n in nodes]
    for i in range(0, max(len(ids), 1), 10):
        chunk = ids[i : i + 10]
        row = "".join(_i(v) for v in chunk)
        if len(chunk) < 10:
            row += _i(0)  # liste sonu
        lines.append(row)

    vx = float(vel.get("vx") or 0.0)
    vy = float(vel.get("vy") or 0.0)
    vz = float(vel.get("vz") or 0.0)
    lines.extend(
        [
            "/INIVEL/TRA/1",
            "impact_vel",
            f"{_f(vx)}{_f(vy)}{_f(vz)}",
            f"{_i(1)}{_i(0)}{_i(0)}{_i(0)}{_i(0)}{_i(0)}{_i(0)}{_i(0)}",
        ]
    )
    px, py, pz = (float(v) for v in wall["point"])
    nx, ny, nz = (float(v) for v in wall["normal"])
    lines.extend(
        [
            "/RWALL/PLANE/1",
            "barrier",
            f"{_i(1)}{_i(0)}{_i(0)}{_i(0)}",
            f"{_f(px)}{_f(py)}{_f(pz)}",
            f"{_f(nx)}{_f(ny)}{_f(nz)}",
            "/TH/RWALL/1",
            "barrier_th",
            "FNX FNY FNZ",
            _i(1),
            "/TH/PART/1",
            "part_energy",
            "IE KE",
            _i(1),
        ]
    )
    th_nodes = params.get("th_nodes") or []
    if th_nodes:
        lines.extend(["/TH/NODE/1", "hic_nodes", "ACCX ACCY ACCZ"])
        ids_th = [int(n) for n in th_nodes]
        for i in range(0, len(ids_th), 10):
            chunk = ids_th[i : i + 10]
            row = "".join(_i(v) for v in chunk)
            if len(chunk) < 10:
                row += _i(0)
            lines.append(row)
    lines.extend(["/END", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_engine(path: Path, params: dict[str, Any], run_name: str) -> None:
    t_end = float(params.get("t_end_ms") or 10.0)
    dt_anim = float(params.get("dt_anim_ms") or max(t_end / 20.0, 0.1))
    lines = [
        "#RADIOSS ENGINE",
        f"/RUN/{run_name}/1",
        _i(10000),
        "/TFILE",
        _f(dt_anim),
        "/ANIM/DT",
        f"{_f(0.0)}{_f(dt_anim)}",
        "/ANIM/VECT/DISP",
        "/ANIM/VECT/VEL",
        "/ANIM/ELEM/ENER",
        "/TH/TITLE",
        "/STOP",
        f"{_f(t_end)}{_f(0.0)}{_f(0.0)}",
        "/END",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


class OpenRadiossAdapter(SolverAdapter):
    """Crash solver. Durability `/solve` bu sınıfı kullanmaz."""

    def build_input(self, params: dict[str, Any]) -> InputArtifact:
        params = dict(params)
        output_dir = Path(params["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        job_name = str(params.get("job_name") or "crash")
        starter = output_dir / f"{job_name}_0000.rad"
        engine = output_dir / f"{job_name}_0001.rad"
        if params.get("barrier") is not None:
            from app.solvers.crash_params import CrashBarrierParams, apply_barrier

            try:
                barrier = CrashBarrierParams.model_validate(params["barrier"])
            except ValidationError as exc:
                raise SolverError(f"OpenRadioss barrier geçersiz: {exc}") from exc
            apply_barrier(params, barrier)
        if params.get("model") is not None:
            _crash_model(params)
        if not (params.get("nodes") or []):
            mesh_path = params.get("mesh_path")
            if mesh_path:
                from app.mesh.openradioss_export import gmsh_msh_to_radioss

                exported = gmsh_msh_to_radioss(Path(mesh_path))
                params["nodes"] = exported.nodes
                params["tets"] = exported.tets
                if exported.bricks:
                    params["bricks"] = exported.bricks
            else:
                raise SolverError("OpenRadioss: nodes listesi boş.")
        _write_starter(starter, params)
        _write_engine(engine, params, job_name)
        return InputArtifact(path=starter, kind="file")

    def submit(
        self,
        artifact: InputArtifact,
        *,
        t_end_ms: float = 10.0,
        progress_cb: Any | None = None,
    ) -> JobHandle:
        bins = resolve_openradioss()
        if bins is None:
            raise SolverError(
                "OpenRadioss bulunamadı. OPENRADIOSS_PATH kök dizin veya engine "
                "ikilisi olmalı (Codespace: /opt/openradioss). "
                f"Starter hazır: {artifact.path}"
            )
        if bins.starter is None:
            raise SolverError(
                "OpenRadioss starter ikilisi yok (starter_linux64_gf / starter_win64.exe). "
                f"Engine: {bins.engine}"
            )
        work_dir = artifact.path.parent
        engine_input = artifact.path.with_name(
            artifact.path.name.replace("_0000.rad", "_0001.rad")
        )
        if not engine_input.is_file():
            raise SolverError(f"Engine dosyası yok: {engine_input}")
        job_id = str(uuid.uuid4())
        log_path = work_dir / "openradioss.log"
        env = runtime_env(bins)
        chunks: list[str] = []
        try:
            starter_proc = subprocess.run(
                [str(bins.starter), "-i", artifact.path.name, "-np", "1"],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
                env=env,
            )
            chunks.append(
                "=== starter ===\n" + (starter_proc.stdout or "") + (starter_proc.stderr or "")
            )
            if starter_proc.returncode != 0:
                log_path.write_text("\n".join(chunks), encoding="utf-8")
                raise SolverError(
                    f"OpenRadioss starter hata (exit={starter_proc.returncode}). Log: {log_path}"
                )
            if progress_cb is None:
                proc = subprocess.run(
                    [str(bins.engine), "-i", engine_input.name],
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                    env=env,
                )
                chunks.append(
                    "=== engine ===\n" + (proc.stdout or "") + (proc.stderr or "")
                )
                exit_code = proc.returncode
            else:
                from app.solvers.openradioss_progress import parse_progress_line

                proc = subprocess.Popen(
                    [str(bins.engine), "-i", engine_input.name],
                    cwd=str(work_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                )
                engine_out: list[str] = []
                try:
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        engine_out.append(line)
                        parsed = parse_progress_line(line, t_end_ms)
                        if parsed is not None:
                            progress_cb(parsed)
                    exit_code = proc.wait(timeout=600)
                except subprocess.TimeoutExpired as exc:
                    proc.kill()
                    raise SolverError("OpenRadioss zaman aşımı (600s).") from exc
                chunks.append("=== engine ===\n" + "".join(engine_out))
        except subprocess.TimeoutExpired as exc:
            raise SolverError("OpenRadioss zaman aşımı (600s).") from exc
        log_path.write_text("\n".join(chunks), encoding="utf-8")
        handle = JobHandle(job_id=job_id, work_dir=work_dir, artifact=artifact)
        handle._exit_code = exit_code  # type: ignore[attr-defined]
        handle._log_path = log_path  # type: ignore[attr-defined]
        if exit_code != 0:
            raise SolverError(f"OpenRadioss hata (exit={exit_code}). Log: {log_path}")
        return handle

    def poll_status(self, job: JobHandle) -> JobStatus:
        exit_code = getattr(job, "_exit_code", None)
        if exit_code is None:
            return JobStatus(state="pending")
        if exit_code == 0:
            return JobStatus(state="done", exit_code=0)
        return JobStatus(state="failed", exit_code=exit_code, message="OpenRadioss hata")

    def parse_results(self, job: JobHandle) -> ResultSet:
        from app.postprocess.openradioss_th import parse_openradioss_dir

        return parse_openradioss_dir(job.work_dir)
