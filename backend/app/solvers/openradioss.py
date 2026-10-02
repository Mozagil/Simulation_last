"""OpenRadioss solver adaptörü — Faz 1 crash (CalculiX'ten bağımsız).

Starter (`_0000.rad`) + engine (`_0001.rad`). Mesh: `params["nodes"]`/`tets`
veya mevcut Gmsh `.msh` (`mesh_path`). Bariyer: `params["barrier"]`
(`CrashBarrierParams`) → `/INIVEL` + `/RWALL`. `generate_mesh` / `/solve`
dokunulmaz. `submit` ikili yoksa SolverError.
"""

from __future__ import annotations

import math

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from app.solvers.base import (
    InputArtifact,
    JobHandle,
    JobStatus,
    ResultSet,
    SolverAdapter,
    SolverError,
)
from app.solvers.crash_params import CrashContactParams, CrashModelParams

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
    # Doluysa ikililer bu Docker imajının İÇİNDE çalışır (Windows geliştirme
    # makinesi: Docker Desktop/WSL2). Yollar imaj içi yollardır.
    docker_image: str | None = None


DOCKER_HOME = Path("/opt/openradioss")
DOCKER_WORK = "/work"


def _docker_home() -> Path:
    """İmaj içindeki OpenRadioss kökü. Resmi betik /opt/openradioss'a kurar;
    topluluk imajları (örn. dheiny/openradioss-solver) /opt/OpenRadioss/OpenRadioss
    kullanır — OPENRADIOSS_DOCKER_HOME ile verilir."""
    raw = (os.environ.get("OPENRADIOSS_DOCKER_HOME") or "").strip()
    return Path(raw) if raw else DOCKER_HOME


def _docker_bins(image: str) -> OpenRadiossBins:
    home = _docker_home()
    return OpenRadiossBins(
        engine=home / "exec" / "engine_linux64_gf",
        starter=home / "exec" / "starter_linux64_gf",
        home=home,
        docker_image=image,
    )


def docker_env_args(home: Path) -> list[str]:
    """Resmi INSTALL.md ortamı, imajın ENV'inden bağımsız olarak verilir:
    hm_reader/h3d kütüphaneleri yoksa starter 'libhm_reader_linux64.so'
    diye düşer (topluluk imajında görüldü)."""
    h = home.as_posix()
    return [
        "-e", f"RAD_CFG_PATH={h}/hm_cfg_files",
        "-e", f"RAD_H3D_PATH={h}/extlib/h3d/lib/linux64",
        "-e", f"LD_LIBRARY_PATH={h}/extlib/hm_reader/linux64:{h}/extlib/h3d/lib/linux64",
        "-e", "OMP_STACKSIZE=400m",
        "-e", f"OMP_NUM_THREADS={os.environ.get('OPENRADIOSS_THREADS', '4')}",
    ]


def _docker_cli() -> str:
    """docker CLI: DOCKER_CLI env → PATH → Docker Desktop'ın bilinen yolları.

    Backend, geliştirme ortamında PATH'inde docker olmayan bir süreçten
    başlatılabiliyor (WinError 2 görüldü); tam yol bulunursa o kullanılır.
    """
    explicit = (os.environ.get("DOCKER_CLI") or "").strip()
    if explicit:
        return explicit
    found = shutil.which("docker")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA") or ""
    for cand in (
        Path(local) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe",
        Path(r"C:/Program Files/Docker/Docker/resources/bin/docker.exe"),
        Path("/usr/local/bin/docker"),
        Path("/usr/bin/docker"),
    ):
        if cand.is_file():
            return str(cand)
    return "docker"


def launch_command(bins: OpenRadiossBins, exe: Path, args: list[str], work_dir: Path) -> list[str]:
    """Çalıştırılacak komut: doğrudan ikili ya da `docker run` sarmalı.

    Docker'da iş klasörü /work olarak bağlanır; ikili zaten cwd=/work ile
    koşar, dosya adları göreli verildiği için iki yolda da aynı deck çalışır.
    Ortam (RAD_CFG_PATH, LD_LIBRARY_PATH) imajın ENV'inde.
    """
    if bins.docker_image is None:
        return [str(exe), *args]
    return [
        _docker_cli(), "run", "--rm",
        "-v", f"{work_dir.resolve()}:{DOCKER_WORK}",
        "-w", DOCKER_WORK,
        *docker_env_args(bins.home or DOCKER_HOME),
        bins.docker_image,
        exe.as_posix(), *args,
    ]


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
    """OPENRADIOSS_PATH dosya veya kök dizin olabilir (resmi değişken = kök).

    OPENRADIOSS_DOCKER_IMAGE doluysa yerel ikili aranmaz: starter/engine o
    imajda koşar (Windows geliştirme makinesi; bkz. backend/docker/openradioss).
    """
    image = (os.environ.get("OPENRADIOSS_DOCKER_IMAGE") or "").strip()
    if image:
        return _docker_bins(image)
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


# Birim sistemi kg–mm–ms (/BEGIN'de bildirilir): yoğunluk kg/mm³, gerilme ve
# E GPa (= kg/(mm·ms²)), hız mm/ms (sayısal olarak m/s), kuvvet kN, enerji J,
# ivme mm/ms². Post-process (openradioss_th) zamanı ms, ivmeyi mm/ms² sayar.
PA_TO_GPA = 1e-9
KGM3_TO_KGMM3 = 1e-9
MPA_TO_GPA = 1e-3


def _mat_prop_cards(
    mat: dict[str, Any],
    model: CrashModelParams,
    card_id: int = 1,
    shell_thickness: float | None = None,
) -> list[str]:
    """/MAT + /PROP. `shell_thickness` verilirse parça kabuk: /PROP/TYPE1."""
    rho = float(mat.get("density") or 7850.0) * KGM3_TO_KGMM3
    e_gpa = float(mat.get("youngs_modulus") or 210e9) * PA_TO_GPA
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
        a_gpa = float(sy) * PA_TO_GPA
        b_gpa = float(model.harden_b_mpa) * MPA_TO_GPA
        # Radioss 2022 /MAT/LAW2 (Johnson–Cook), Iflag=0: beş veri satırı.
        # Sıfır bırakılan alanlar Radioss varsayılanına düşer (EPS_p_max,
        # SIG_max0, T_melt → 1e30; c, m → hız/sıcaklık etkisi kapalı).
        mat_lines = [
            f"/MAT/LAW2/{card_id}",
            title,
            _f(rho),
            f"{_f(e_gpa)}{_f(nu)}{_i(0)}{_i(0)}",
            f"{_f(a_gpa)}{_f(b_gpa)}{_f(model.harden_n)}{_f(0.0)}{_f(0.0)}",
            f"{_f(0.0)}{_f(0.0)}{_i(0)}{_i(0)}{_f(0.0)}{_f(0.0)}",
            f"{_f(0.0)}{_f(0.0)}{_f(0.0)}{_f(0.0)}{_f(0.0)}",
        ]
    else:
        mat_lines = [
            f"/MAT/LAW1/{card_id}",
            title,
            _f(rho),
            f"{_f(e_gpa)}{_f(nu)}",
        ]
    if shell_thickness is not None:
        sh = model.shell
        # /PROP/TYPE1 (SHELL), hm_cfg radioss2020 düzeni: Ishell Ismstr Ish3n
        # Idrill Ipinch · P_Thick_Fail; Hm Hf Hr Dm Dn; N Istrain Thick Ashear ·
        # Ithick Iplas. Sıfırlar /DEF_SHELL varsayılanı.
        prop_lines = [
            f"/PROP/TYPE1/{card_id}",
            "shell",
            f"{_i(sh.ishell)}{_i(sh.ismstr)}{_i(sh.ish3n)}{_i(0)}{_i(0)}{' ' * 10}{_f(0.0)}",
            f"{_f(0.0)}{_f(0.0)}{_f(0.0)}{_f(0.0)}{_f(0.0)}",
            f"{_i(sh.nip)}{_i(0)}{_f(shell_thickness)}{_f(0.0)}{' ' * 10}{_i(0)}{_i(0)}",
        ]
        return mat_lines + prop_lines
    # /PROP/TYPE14 (solid), Radioss 2022: Isolid Ismstr Iale Icpre Itetra10
    # Inpts Itetra4 Iframe Dn · qa qb h Lambda Mu · dT_min Istrain Ihkt.
    # Sıfırlar varsayılan (qa=1.1, qb=0.05, h=0 …).
    prop_lines = [
        f"/PROP/TYPE14/{card_id}",
        "solid",
        f"{_i(model.isolid)}{_i(model.ismstr)}{_i(0)}{_i(0)}{_i(0)}{_i(model.nip)}{_i(0)}{_i(0)}{_f(0.0)}",
        f"{_f(0.0)}{_f(0.0)}{_f(0.0)}{_f(0.0)}{_f(0.0)}",
        f"{_f(0.0)}{_i(0)}{_i(0)}",
    ]
    return mat_lines + prop_lines


def _contacts(params: dict[str, Any]) -> list[CrashContactParams]:
    out: list[CrashContactParams] = []
    for raw in params.get("contacts") or []:
        if isinstance(raw, CrashContactParams):
            out.append(raw)
            continue
        try:
            out.append(CrashContactParams.model_validate(raw))
        except ValidationError as exc:
            raise SolverError(f"OpenRadioss temas geçersiz: {exc}") from exc
    return out


# Temas için yüzey/düğüm grubu kimlikleri parça başına: 1000 + Radioss part_ID
# (GRNOD 1/2 hareketli/sabit gruplarıyla çakışmaz). Aynı parça birden çok
# temasta geçerse kart bir kez yazılır.
_CONTACT_SET_BASE = 1000


def _contact_cards(
    contacts: list[CrashContactParams],
    rid: Callable[[int], int],
    shell_parts: set[int] | None = None,
) -> list[str]:
    if not contacts:
        return []
    set_id = lambda pid: _CONTACT_SET_BASE + rid(pid)  # noqa: E731
    surf_parts: list[int] = []
    grnod_parts: list[int] = []
    for c in contacts:
        for pid in (c.master_part, c.slave_part) if c.type == 24 else (c.master_part,):
            if pid not in surf_parts:
                surf_parts.append(pid)
        if c.type == 7 and c.slave_part not in grnod_parts:
            grnod_parts.append(c.slave_part)

    lines: list[str] = []
    # Solid: /SURF/PART/EXT (dış yüzler). Kabuk: /SURF/PART (kabuk elemanları;
    # EXT solid içindir).
    shell_parts = shell_parts or set()
    for pid in surf_parts:
        card = "/SURF/PART" if pid in shell_parts else "/SURF/PART/EXT"
        lines.extend([f"{card}/{set_id(pid)}", f"skin_part_{pid}", _i(rid(pid))])
    for pid in grnod_parts:
        lines.extend([f"/GRNOD/PART/{set_id(pid)}", f"nodes_part_{pid}", _i(rid(pid))])

    blank = lambda n: " " * n  # noqa: E731
    # IBC alanı: %7s + üç %1d bayrağı (sınır koşulu devre dışı bırakma kapalı).
    ibc = f"{blank(7)}000"
    for k, c in enumerate(contacts, start=1):
        title = f"contact_{k}_p{c.slave_part}_on_p{c.master_part}"
        if c.type == 7:
            # Radioss 2020+ /INTER/TYPE7 (hm_cfg radioss2020): grnod_id surf_id
            # Istf Ithe Igap · Ibag Idel Icurv Iadm; Fscalegap Gap_max Fpenmax
            # Itied; Stmin Stmax %mesh dtmin Irem_gap Irem_i2; Stfac Fric GAPmin
            # Tstart Tstop; IBC Inacti VIS_S VIS_F Bumult; Ifric … fric_ID.
            lines.extend(
                [
                    f"/INTER/TYPE7/{k}",
                    title,
                    f"{_i(set_id(c.slave_part))}{_i(set_id(c.master_part))}{_i(c.istf)}"
                    f"{_i(0)}{_i(0)}{blank(10)}{_i(0)}{_i(0)}{_i(0)}{_i(0)}",
                    f"{_f(0.0)}{_f(0.0)}{_f(0.0)}{blank(20)}{_i(0)}",
                    f"{_f(0.0)}{_f(0.0)}{_f(0.0)}{_f(0.0)}{_i(0)}{_i(0)}",
                    f"{_f(c.stfac)}{_f(c.fric)}{_f(c.gapmin)}{_f(0.0)}{_f(0.0)}",
                    f"{ibc}{blank(20)}{_i(c.inacti)}{_f(0.0)}{_f(0.0)}{_f(0.0)}",
                    f"{_i(0)}{_i(0)}{_f(0.0)}{_i(0)}{_i(0)}{_i(0)}{_f(0.0)}{_i(0)}",
                ]
            )
        else:
            # Radioss 2021+ /INTER/TYPE24 (hm_cfg radioss2021): surf_ID1 (slave)
            # surf_ID2 (master; self-contact'ta 0) Istf · Irem_i2 · Idel;
            # grnd_IDs · Iedge Edge_angle Gap_max_s Gap_max_m; Stmin Stmax Igap0
            # Ipen0 Ipen_max; Stfac Fric · Tstart Tstop; IBC Inacti VISs ·
            # Tpressfit; Ifric Ifiltr Xfreq · sens_ID · fric_ID.
            surf2 = 0 if c.master_part == c.slave_part else set_id(c.master_part)
            lines.extend(
                [
                    f"/INTER/TYPE24/{k}",
                    title,
                    f"{_i(set_id(c.slave_part))}{_i(surf2)}{_i(c.istf)}"
                    f"{blank(20)}{_i(0)}{blank(10)}{_i(0)}",
                    f"{_i(0)}{blank(20)}{_i(c.iedge)}{_f(0.0)}{_f(0.0)}{_f(0.0)}",
                    f"{_f(0.0)}{_f(0.0)}{_i(0)}{_i(0)}{_f(0.0)}",
                    f"{_f(c.stfac)}{_f(c.fric)}{blank(20)}{_f(0.0)}{_f(0.0)}",
                    f"{ibc}{blank(20)}{_i(c.inacti)}{_f(0.0)}{blank(20)}{_f(0.0)}",
                    f"{_i(0)}{_i(0)}{_f(0.0)}{blank(10)}{_i(0)}{blank(30)}{_i(0)}",
                ]
            )
    return lines


def _write_starter(path: Path, params: dict[str, Any]) -> None:
    title = str(params.get("title") or "crash")[:80]
    nodes = params.get("nodes") or []
    tets = params.get("tets") or []
    bricks = params.get("bricks") or []
    shells = params.get("shells") or []
    sh3n = params.get("sh3n") or []
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
    model = _crash_model(params)
    # Parçalar: eleman → parça haritası (export) yoksa her şey parça 0.
    element_parts: dict[int, int] = {
        int(k): int(v) for k, v in (params.get("element_parts") or {}).items()
    }
    part_ids = sorted(set(element_parts.values())) or [0]
    # Rol: hareketli (ilk hız alır) / sabit (/BCS ile tutulur). Verilmeyen
    # parça hareketli — tek parçalı eski davranışla aynı.
    roles: dict[int, str] = {0: "moving"} if part_ids == [0] else {}
    for spec in params.get("parts") or []:
        roles[int(spec["part_id"])] = str(spec.get("role") or "moving")
    for pid in part_ids:
        roles.setdefault(pid, "moving")
    moving = [p for p in part_ids if roles[p] != "fixed"]
    fixed = [p for p in part_ids if roles[p] == "fixed"]
    if not moving:
        raise SolverError("Crash: en az bir hareketli parça gerekli (hepsi sabit).")
    # Parça başına malzeme: atama part_id ile; yoksa ilk malzemeye düşülmez,
    # açık hata (yanlış malzemeyle sessizce çözmek daha kötü).
    mat_by_part: dict[int, dict[str, Any]] = {}
    for m in mats:
        pid = m.get("part_id")
        mat_by_part[int(pid) if pid is not None else 0] = m
    missing = [p for p in part_ids if p not in mat_by_part]
    if missing and len(mats) == 1 and part_ids == [0]:
        mat_by_part[0] = mats[0]
        missing = []
    if missing:
        raise SolverError(
            "Crash: malzeme atanmamış parça(lar): "
            + ", ".join(f"#{p}" for p in missing)
            + " — 3 · Material adımından her parçaya malzeme atayın."
        )

    # Parça tipi: kabuk elemanı olan parça kabuk (/PROP/TYPE1); aynı parçada
    # solid + kabuk desteklenmez (karma model ayrı adım).
    solid_eids = {int(el[0]) for el in [*tets, *bricks]}
    shell_eids = {int(el[0]) for el in [*shells, *sh3n]}
    solid_parts = {element_parts.get(e, 0) for e in solid_eids}
    shell_parts = {element_parts.get(e, 0) for e in shell_eids}
    both = sorted(solid_parts & shell_parts)
    if both:
        raise SolverError(
            "Crash: aynı parçada solid ve kabuk eleman: " + ", ".join(f"#{p}" for p in both)
        )
    # Kalınlık önceliği: parts[].thickness_mm (açık) > ürün ağacı bileşeni
    # (`component_thickness`, API doldurur) > model.shell.thickness_mm; yoksa hata.
    thickness: dict[int, float] = {
        int(k): float(v) for k, v in (params.get("component_thickness") or {}).items()
    }
    for spec in params.get("parts") or []:
        t = spec.get("thickness_mm")
        if t is not None:
            thickness[int(spec["part_id"])] = float(t)
    for pid in sorted(shell_parts):
        if pid not in thickness and model.shell.thickness_mm is not None:
            thickness[pid] = float(model.shell.thickness_mm)
    no_t = [p for p in sorted(shell_parts) if p not in thickness]
    if no_t:
        raise SolverError(
            "Crash: kalınlığı verilmemiş kabuk parça(lar): "
            + ", ".join(f"#{p}" for p in no_t)
            + " — Malzeme adımında ürün ağacından (bileşen kalınlığı) girin."
        )

    # /BEGIN (2022): başlık · Invers Irun · girdi birimleri · çalışma birimleri.
    # Ayrı /UNIT/* kartı yok; starter "Unexpected card" diye atlıyordu.
    units = f"{'kg':>20}{'mm':>20}{'ms':>20}"
    lines: list[str] = ["#RADIOSS STARTER"]
    if params.get("coincident_nodes") is not None:
        # Export ölçümü: aynı koordinatta ayrı düğüm sayısı (bağlantısızlık verisi).
        lines.append(f"# coincident_nodes: {int(params['coincident_nodes'])}")
    lines += [
        "/BEGIN",
        title,
        f"{_i(2022)}{_i(0)}",
        units,
        units,
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

    # Radioss parça/kart kimlikleri 1 tabanlı: part_ID = mesh part_id + 1.
    def _rid(pid: int) -> int:
        return pid + 1

    for pid in part_ids:
        part_tets = [el for el in tets if element_parts.get(int(el[0]), 0) == pid]
        part_bricks = [el for el in bricks if element_parts.get(int(el[0]), 0) == pid]
        if part_tets:
            lines.append(f"/TETRA4/{_rid(pid)}")
            for el in part_tets:
                eid, n1, n2, n3, n4 = (int(v) for v in el)
                lines.append(f"{_i(eid)}{_i(n1)}{_i(n2)}{_i(n3)}{_i(n4)}")
        if part_bricks:
            lines.append(f"/BRICK/{_rid(pid)}")
            for el in part_bricks:
                vals = [int(v) for v in el]
                lines.append("".join(_i(v) for v in vals))
        # /SHELL: shell_ID n1..n4; /SH3N: tria_ID n1..n3. PHI ve Thick boş —
        # kalınlık /PROP/TYPE1'den.
        part_shells = [el for el in shells if element_parts.get(int(el[0]), 0) == pid]
        part_sh3n = [el for el in sh3n if element_parts.get(int(el[0]), 0) == pid]
        if part_shells:
            lines.append(f"/SHELL/{_rid(pid)}")
            lines.extend("".join(_i(int(v)) for v in el) for el in part_shells)
        if part_sh3n:
            lines.append(f"/SH3N/{_rid(pid)}")
            lines.extend("".join(_i(int(v)) for v in el) for el in part_sh3n)

    for pid in part_ids:
        lines.extend(
            _mat_prop_cards(mat_by_part[pid], model, card_id=_rid(pid), shell_thickness=thickness.get(pid))
        )
        lines.extend(
            [
                f"/PART/{_rid(pid)}",
                f"part_{pid}_{roles[pid]}"[:100],
                f"{_i(_rid(pid))}{_i(_rid(pid))}",
            ]
        )

    def _grnod_part(gid: int, title: str, pids: list[int]) -> list[str]:
        out = [f"/GRNOD/PART/{gid}", title]
        rids = [_rid(p) for p in pids]
        for i in range(0, len(rids), 10):
            out.append("".join(_i(v) for v in rids[i : i + 10]))
        return out

    # Grup 1: hareketli parçaların düğümleri (ilk hız, duvar); grup 2: sabit.
    lines.extend(_grnod_part(1, "moving_parts", moving))
    if fixed:
        lines.extend(_grnod_part(2, "fixed_parts", fixed))
        # /BCS: üç öteleme + üç dönme serbestliği kilitli.
        lines.extend(["/BCS/1", "fixed_parts", f"   111 111{_i(0)}{_i(2)}"])

    contacts = _contacts(params)
    for c in contacts:
        for pid in (c.master_part, c.slave_part):
            if pid not in part_ids:
                raise SolverError(f"Crash: temas parçası #{pid} mesh'te yok.")
    inter_ids = list(range(1, len(contacts) + 1))
    lines.extend(_contact_cards(contacts, _rid, shell_parts))

    vx = float(vel.get("vx") or 0.0)
    vy = float(vel.get("vy") or 0.0)
    vz = float(vel.get("vz") or 0.0)
    # /INIVEL/TRA: Vx Vy Vz grnd_ID skew_ID tek satırda (mm/ms).
    lines.extend(
        [
            "/INIVEL/TRA/1",
            "impact_vel",
            f"{_f(vx)}{_f(vy)}{_f(vz)}{_i(1)}{_i(0)}",
        ]
    )
    # /RWALL/PLANE: node_ID=0 sabit duvar; Slide=0 kayan; grnd_ID1 = tüm
    # düğümler. Düzlem M noktası ve M1 = M + n (normal, ikincil düğümlerin
    # bulunduğu tarafa bakar). d = 0, sürtünme yok (Slide=0).
    px, py, pz = (float(v) for v in wall["point"])
    nx, ny, nz = (float(v) for v in wall["normal"])
    norm = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    nx, ny, nz = nx / norm, ny / norm, nz / norm
    th_vars = lambda names: "".join(f"{n:>10}" for n in names)  # noqa: E731
    # Duvar kapatılabilir (1.12: temasla parça–parça çarpışma). Varsayılan açık.
    if params.get("use_rigid_wall", True):
        lines.extend(
            [
                "/RWALL/PLANE/1",
                "barrier",
                f"{_i(0)}{_i(0)}{_i(1)}{_i(0)}",
                f"{_f(0.0)}{'':>20}{_f(0.0)}",
                f"{_f(px)}{_f(py)}{_f(pz)}",
                f"{_f(px + nx)}{_f(py + ny)}{_f(pz + nz)}",
                "/TH/RWALL/1",
                "barrier_th",
                th_vars(["FNX", "FNY", "FNZ"]),
                _i(1),
            ]
        )
    if inter_ids:
        # Normal (FN*) + teğetsel (FT*) temas kuvveti; post-process grup
        # başlığı "contact_th" ile arayüz başına altışar sütun okur.
        lines.extend(["/TH/INTER/1", "contact_th", th_vars(["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"])])
        for i in range(0, len(inter_ids), 10):
            lines.append("".join(_i(v) for v in inter_ids[i : i + 10]))
    lines.extend(
        [
            "/TH/PART/1",
            "part_energy",
            th_vars(["IE", "KE"]),
            "".join(_i(_rid(p)) for p in part_ids),
        ]
    )
    th_nodes = params.get("th_nodes") or []
    if th_nodes:
        lines.extend(["/TH/NODE/1", "hic_nodes", th_vars(["ACCX", "ACCY", "ACCZ"])])
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
    # /RUN veri satırı = Tstop (ms). /TFILE: zaman geçmişi yazma aralığı.
    dt_th = max(t_end / 200.0, 1e-3)
    lines = [
        "#RADIOSS ENGINE",
        f"/RUN/{run_name}/1",
        _f(t_end),
        "/TFILE",
        _f(dt_th),
        "/ANIM/DT",
        f"{_f(0.0)}{_f(dt_anim)}",
        "/ANIM/VECT/DISP",
        "/ANIM/VECT/VEL",
        "/ANIM/ELEM/ENER",
        "/END",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _convert_time_history(bins: OpenRadiossBins, work_dir: Path, starter_name: str) -> str:
    """`<job>T01` ikilisini th_to_csv ile CSV'ye çevirir (en iyi çaba).

    Post-process (`openradioss_th.parse_openradioss_dir`) duvar kuvvetini,
    parça enerjilerini ve HIC için düğüm ivmelerini `*T01*.csv`'den okur; .out
    yalnız toplam enerjileri verir. Converter yoksa ya da patlarsa çözüm
    yine "bitti" sayılır, log'a not düşülür.
    """
    job = starter_name.replace("_0000.rad", "")
    t01 = work_dir / f"{job}T01"
    if not t01.is_file():
        return "=== th_to_csv === T01 yok, atlandı"
    conv = bins.engine.with_name("th_to_csv_linux64_gf")
    if bins.docker_image is None and not conv.is_file():
        return f"=== th_to_csv === converter yok ({conv}), atlandı"
    try:
        proc = subprocess.run(
            launch_command(bins, conv, [t01.name], work_dir),
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            env=runtime_env(bins),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover — ortam
        return f"=== th_to_csv === çalıştırılamadı: {exc}"
    return "=== th_to_csv ===\n" + (proc.stdout or "") + (proc.stderr or "")


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
                if exported.shells:
                    params["shells"] = exported.shells
                if exported.sh3n:
                    params["sh3n"] = exported.sh3n
                params["element_parts"] = exported.element_parts
                params["coincident_nodes"] = exported.coincident_nodes
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
                launch_command(bins, bins.starter, ["-i", artifact.path.name, "-np", "1"], work_dir),
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
                    launch_command(bins, bins.engine, ["-i", engine_input.name], work_dir),
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
                    launch_command(bins, bins.engine, ["-i", engine_input.name], work_dir),
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
        if exit_code == 0:
            chunks.append(_convert_time_history(bins, work_dir, artifact.path.name))
        log_path.write_text("\n".join(chunks), encoding="utf-8")
        handle = JobHandle(job_id=job_id, work_dir=work_dir, artifact=artifact)
        handle._exit_code = exit_code  # type: ignore[attr-defined]
        handle._log_path = log_path  # type: ignore[attr-defined]
        if exit_code != 0:
            raise SolverError(f"OpenRadioss hata (exit={exit_code}). Log: {log_path}")
        return handle

    def poll_status(self, job: JobHandle) -> JobStatus:  # noqa: D102 — arayüz
        exit_code = getattr(job, "_exit_code", None)
        if exit_code is None:
            return JobStatus(state="pending")
        if exit_code == 0:
            return JobStatus(state="done", exit_code=0)
        return JobStatus(state="failed", exit_code=exit_code, message="OpenRadioss hata")

    def parse_results(self, job: JobHandle) -> ResultSet:
        from app.postprocess.openradioss_th import parse_openradioss_dir

        return parse_openradioss_dir(job.work_dir)
