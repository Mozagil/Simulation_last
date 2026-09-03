"""CalculiX (ccx) solver adaptörü — Faz 0 durability.

`build_input`: Gmsh .msh → Abaqus/CalculiX .inp + malzeme + BC kartları.
`submit`: `ccx` subprocess (CCX_PATH veya PATH). Kurulu değilse SolverError.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import gmsh

from app.mesh.gmsh_adapter import _gmsh_lock
from app.solvers.base import (
    InputArtifact,
    JobHandle,
    JobStatus,
    ResultSet,
    SolverAdapter,
    SolverError,
)

logger = logging.getLogger(__name__)

_GMSH_TO_CCX_3D = {
    4: "C3D4",  # tet4
    11: "C3D10",  # tet10
    5: "C3D8",  # hex8
}
_GMSH_TO_CCX_2D = {
    2: "S3",  # tri3 shell
    3: "S4",  # quad4 shell
}


def _frd_data_line(line: str) -> tuple[int, list[float]] | None:
    """CalculiX .frd sabit-sütun-genişlikli veri satırını parse eder.

    Format (gerçek bir .frd dosyasıyla doğrulandı): " -1" + node_id (10
    karakter) + N × değer (12 karakter). Negatif sayılarda boşluk OLMADIĞI
    için basit `split()` yanlış parse eder — sütun pozisyonuna göre dilimleme
    zorunlu.
    """
    if not line.startswith(" -1"):
        return None
    try:
        node_id = int(line[3:13])
    except ValueError:
        return None
    values: list[float] = []
    pos = 13
    while pos + 12 <= len(line):
        chunk = line[pos : pos + 12]
        try:
            values.append(float(chunk))
        except ValueError:
            break
        pos += 12
    return node_id, values


def _parse_frd(frd_path: Path) -> dict[str, dict[int, tuple[float, ...]]]:
    """CalculiX .frd (ASCII) sonuç dosyasını parse eder.

    Döndürür: node_coords (id -> (x,y,z)), displacement (id -> (dx,dy,dz)),
    stress (id -> (sxx,syy,szz,sxy,syz,szx)). Dict sırası dosyadaki sıraya
    göre korunur (Python 3.7+) — bu, mesh'in kanonik node sırasıyla aynıdır
    (CalculiX, .inp'teki *NODE sırasını aynen yansıtır).
    """
    lines = frd_path.read_text(encoding="utf-8", errors="replace").splitlines()

    node_coords: dict[int, tuple[float, ...]] = {}
    displacement: dict[int, tuple[float, ...]] = {}
    stress: dict[int, tuple[float, ...]] = {}

    in_node_block = False
    current_result_type: str | None = None

    for line in lines:
        stripped_start = line[:6] if len(line) >= 6 else line
        if stripped_start.strip() == "2C" or line.lstrip().startswith("2C "):
            in_node_block = True
            current_result_type = None
            continue
        if line.startswith(" -4"):
            # örn: " -4  DISP        4    1" / " -4  STRESS      6    1"
            rest = line[4:].split()
            current_result_type = rest[0] if rest else None
            in_node_block = False
            continue
        if line.startswith(" -3"):
            in_node_block = False
            current_result_type = None
            continue
        if line.startswith(" -5"):
            continue  # component tanım satırı, veri değil

        if in_node_block:
            parsed = _frd_data_line(line)
            if parsed and len(parsed[1]) >= 3:
                nid, vals = parsed
                node_coords[nid] = (vals[0], vals[1], vals[2])
            continue

        if current_result_type == "DISP":
            parsed = _frd_data_line(line)
            if parsed and len(parsed[1]) >= 3:
                nid, vals = parsed
                displacement[nid] = (vals[0], vals[1], vals[2])
        elif current_result_type == "STRESS":
            parsed = _frd_data_line(line)
            if parsed and len(parsed[1]) >= 6:
                nid, vals = parsed
                stress[nid] = tuple(vals[:6])

    return {"node_coords": node_coords, "displacement": displacement, "stress": stress}


def _von_mises_stress(
    sxx: float, syy: float, szz: float, sxy: float, syz: float, szx: float
) -> float:
    """Standart von Mises eşdeğer gerilme formülü (gerilme tensöründen)."""
    return math.sqrt(
        0.5
        * (
            (sxx - syy) ** 2
            + (syy - szz) ** 2
            + (szz - sxx) ** 2
            + 6 * (sxy**2 + syz**2 + szx**2)
        )
    )


def _ccx_executable() -> str | None:
    env = os.environ.get("CCX_PATH")
    if env and Path(env).exists():
        return env
    return shutil.which("ccx") or shutil.which("ccx.exe")


def _sanitize_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:64] or "MAT"


class CalculiXAdapter(SolverAdapter):
    def build_input(self, params: dict[str, Any]) -> InputArtifact:
        """params anahtarları:
        - mesh_path: Path
        - dimension: 2|3
        - output_dir: Path
        - job_name: str
        - materials: list[{name, density, youngs_modulus, poisson_ratio, part_id}]
        - shell_thickness: float (dim=2)
        - bcs: list[dict]  fixed/cload/pressure/displacement/gravity/bearing
        """
        mesh_path = Path(params["mesh_path"])
        if not mesh_path.exists():
            raise SolverError(f"Mesh yok: {mesh_path}")

        dimension = int(params["dimension"])
        output_dir = Path(params["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        job_name = params.get("job_name", "job")
        inp_path = output_dir / f"{job_name}.inp"

        materials = params.get("materials") or []
        shell_thickness = float(params.get("shell_thickness", 1.0))
        bcs = params.get("bcs") or []

        mesh_block, nsets, elsets = _mesh_to_inp_blocks(
            mesh_path, dimension, materials, shell_thickness
        )
        mat_block = _materials_inp_block(materials, dimension, shell_thickness)
        # model_bc_block: *BOUNDARY/*TRANSFORM (STEP DIŞINDA kalabilir).
        # step_bc_block: *CLOAD/*DLOAD (SADECE STEP İÇİNDE geçerli — gerçek
        # bir çalıştırmada dışarıda kalınca CalculiX "*CLOAD should only be
        # used within a STEP" hatasıyla durduğu doğrulandı).
        model_bc_block, step_bc_block = _bcs_inp_block(bcs, nsets, elsets, dimension)
        step_block = _static_step_block(step_bc_block)

        inp_path.write_text(
            mesh_block + mat_block + model_bc_block + step_block,
            encoding="utf-8",
        )
        logger.info("CalculiX .inp yazıldı: %s", inp_path)
        return InputArtifact(path=inp_path, kind="file")

    def submit(self, artifact: InputArtifact) -> JobHandle:
        ccx = _ccx_executable()
        if ccx is None:
            raise SolverError(
                "CalculiX (ccx) bulunamadı. CCX_PATH ayarlayın veya PATH'e ekleyin. "
                f".inp hazır: {artifact.path}"
            )

        work_dir = artifact.path.parent
        job_name = artifact.path.stem
        job_id = str(uuid.uuid4())
        log_path = work_dir / f"{job_name}.ccx.log"

        try:
            proc = subprocess.run(
                [ccx, job_name],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SolverError("CalculiX zaman aşımı (600s).") from exc

        log_path.write_text(
            (proc.stdout or "") + "\n" + (proc.stderr or ""),
            encoding="utf-8",
        )
        handle = JobHandle(job_id=job_id, work_dir=work_dir, artifact=artifact)
        handle._exit_code = proc.returncode  # type: ignore[attr-defined]
        handle._log_path = log_path  # type: ignore[attr-defined]
        if proc.returncode != 0:
            raise SolverError(
                f"CalculiX hata (exit={proc.returncode}). Log: {log_path}"
            )
        return handle

    def poll_status(self, job: JobHandle) -> JobStatus:
        exit_code = getattr(job, "_exit_code", None)
        if exit_code is None:
            frd = job.work_dir / f"{job.artifact.path.stem}.frd"
            if frd.exists():
                return JobStatus(state="done", exit_code=0)
            return JobStatus(state="pending")
        if exit_code == 0:
            return JobStatus(state="done", exit_code=0)
        return JobStatus(state="failed", exit_code=exit_code, message="ccx failed")

    def parse_results(self, job: JobHandle) -> ResultSet:
        frd = job.work_dir / f"{job.artifact.path.stem}.frd"
        if not frd.exists():
            return ResultSet(raw_result_path=None, scalars={"frd_exists": 0.0})

        try:
            parsed = _parse_frd(frd)
        except Exception as exc:  # noqa: BLE001 — parse hatası çözümü bozmasın
            logger.warning("FRD parse edilemedi: %s", exc)
            return ResultSet(
                scalars={"frd_bytes": float(frd.stat().st_size)},
                raw_result_path=frd,
            )

        node_coords = parsed["node_coords"]
        displacement = parsed["displacement"]
        stress = parsed["stress"]

        # Dosyadaki (2C bloğundaki) node sırası = mesh'in kanonik sırası —
        # aynı sıralama frontend'in mesh önizlemesindeki `nodes[]` dizisiyle
        # birebir eşleşir (ikisi de aynı Gmsh `getNodes()` çağrısından gelir).
        node_order = list(node_coords.keys())

        nodes_array = [list(node_coords[nid]) for nid in node_order]

        disp_mag: dict[int, float] = {}
        for nid, (dx, dy, dz) in displacement.items():
            disp_mag[nid] = math.sqrt(dx * dx + dy * dy + dz * dz)

        von_mises: dict[int, float] = {}
        for nid, (sxx, syy, szz, sxy, syz, szx) in stress.items():
            von_mises[nid] = _von_mises_stress(sxx, syy, szz, sxy, syz, szx)

        disp_mag_array = [disp_mag.get(nid, 0.0) for nid in node_order]
        von_mises_array = [von_mises.get(nid, 0.0) for nid in node_order]
        # Deforme şekil (deformed shape) görselleştirmesi için — sadece
        # büyüklük değil, gerçek vektör (dx,dy,dz) gerekiyor.
        disp_vector_array = [
            list(displacement.get(nid, (0.0, 0.0, 0.0))) for nid in node_order
        ]

        max_disp = max(disp_mag_array, default=0.0)
        max_vm = max(von_mises_array, default=0.0)
        # Kritik node: maksimum von Mises'e sahip düğümün gerçek CalculiX
        # node ID'si (frontend'de "CRITICAL NODE: #8421" gibi göstermek
        # için — index değil, gerçek node numarası).
        critical_node_id: int | None = None
        if von_mises:
            critical_node_id = max(von_mises, key=lambda nid: von_mises[nid])

        results_preview_path = job.work_dir / f"{job.artifact.path.stem}.results.json"
        results_preview_path.write_text(
            json.dumps(
                {
                    "node_ids": node_order,
                    "nodes": nodes_array,
                    "displacement_magnitude": disp_mag_array,
                    "displacement_vectors": disp_vector_array,
                    "von_mises": von_mises_array,
                    "max_displacement": max_disp,
                    "max_von_mises": max_vm,
                    "critical_node_id": critical_node_id,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

        logger.info(
            "FRD parse edildi: %s, node_sayisi=%d, max_disp=%.6g, max_von_mises=%.6g",
            frd,
            len(node_order),
            max_disp,
            max_vm,
        )

        return ResultSet(
            scalars={
                "frd_bytes": float(frd.stat().st_size),
                "node_count": float(len(node_order)),
                "max_displacement": max_disp,
                "max_von_mises": max_vm,
                **(
                    {"critical_node_id": float(critical_node_id)}
                    if critical_node_id is not None
                    else {}
                ),
            },
            raw_result_path=frd,
            results_preview_path=results_preview_path,
        )


def _mesh_to_inp_blocks(
    mesh_path: Path,
    dimension: int,
    materials: list[dict[str, Any]],
    shell_thickness: float,
) -> tuple[str, dict[str, list[int]], dict[str, list[int]]]:
    """Gmsh mesh'ten *NODE / *ELEMENT / *NSET / *ELSET blokları."""
    _gmsh_lock.acquire()
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(mesh_path))

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        tag_to_idx = {int(t): i + 1 for i, t in enumerate(node_tags)}  # 1-based inp
        lines: list[str] = ["*HEADING", "CAE platform CalculiX job", "*NODE"]
        for i, tag in enumerate(node_tags):
            nid = i + 1
            x, y, z = coords[3 * i : 3 * i + 3]
            lines.append(f"{nid}, {x:.8g}, {y:.8g}, {z:.8g}")

        nsets: dict[str, list[int]] = {}
        elsets: dict[str, list[int]] = {}
        elem_id = 1

        type_map = _GMSH_TO_CCX_2D if dimension == 2 else _GMSH_TO_CCX_3D
        elem_dim = dimension

        # Volume/yüzey bazlı ELSET: part_id ↔ entity sırası
        entities = gmsh.model.getEntities(elem_dim)
        if not entities:
            # Tüm elemanlar tek set
            entities = [(-1, -1)]

        part_materials = {int(m["part_id"]): m for m in materials}

        if entities == [(-1, -1)]:
            etypes, etags_list, enodes_list = gmsh.model.mesh.getElements(dim=elem_dim)
            all_eids: list[int] = []
            for etype, etags, enodes in zip(etypes, etags_list, enodes_list):
                ccx_type = type_map.get(int(etype))
                if not ccx_type:
                    continue
                n_per = len(enodes) // max(len(etags), 1) if len(etags) else 0
                lines.append(f"*ELEMENT, TYPE={ccx_type}, ELSET=PART_0")
                for ei, _etag in enumerate(etags):
                    conn = [
                        tag_to_idx[int(enodes[ei * n_per + k])]
                        for k in range(n_per)
                    ]
                    lines.append(f"{elem_id}, " + ", ".join(str(c) for c in conn))
                    all_eids.append(elem_id)
                    elem_id += 1
            elsets["PART_0"] = all_eids
        else:
            # 2D: PART_n = kenar paylaşan kabuk (preview triangle_to_part ile aynı).
            # 3D: PART_n = volume sırası. FACE_EL_* her yüzey için ayrı kalır (DLOAD).
            face_to_part: dict[int, int] = {}
            if elem_dim == 2:
                from app.mesh.gmsh_adapter import _surface_parts_by_coincident_nodes

                face_to_part = _surface_parts_by_coincident_nodes()

            for entity_index, (edim, etag) in enumerate(entities):
                part_id = (
                    face_to_part.get(etag, 0) if elem_dim == 2 else entity_index
                )
                etypes, etags_list, enodes_list = gmsh.model.mesh.getElements(
                    dim=edim, tag=etag
                )
                elset = f"PART_{part_id}"
                part_eids: list[int] = []
                for etype, etags, enodes in zip(etypes, etags_list, enodes_list):
                    ccx_type = type_map.get(int(etype))
                    if not ccx_type:
                        continue
                    n_per = len(enodes) // max(len(etags), 1) if len(etags) else 0
                    if len(etags) == 0:
                        continue
                    lines.append(f"*ELEMENT, TYPE={ccx_type}, ELSET={elset}")
                    for ei, _ in enumerate(etags):
                        conn = [
                            tag_to_idx[int(enodes[ei * n_per + k])]
                            for k in range(n_per)
                        ]
                        lines.append(f"{elem_id}, " + ", ".join(str(c) for c in conn))
                        part_eids.append(elem_id)
                        elem_id += 1
                elsets.setdefault(elset, []).extend(part_eids)
                if elem_dim == 2:
                    # Shell yüzey eleman seti → *DLOAD P için
                    elsets[f"FACE_EL_{etag}"] = list(part_eids)

                # Yüzey düğüm setleri (BC için): bu volume'un sınır yüzleri
                if elem_dim == 3:
                    for bdim, btag in gmsh.model.getBoundary(
                        [(edim, etag)], oriented=False, recursive=False
                    ):
                        if bdim != 2:
                            continue
                        nset = f"FACE_{btag}"
                        if nset in nsets:
                            continue
                        nt, _, _ = gmsh.model.mesh.getNodes(2, btag)
                        nsets[nset] = [tag_to_idx[int(t)] for t in nt if int(t) in tag_to_idx]
                else:
                    # 2D: yüzey kendisi
                    nset = f"FACE_{etag}"
                    nt, _, _ = gmsh.model.mesh.getNodes(2, etag)
                    nsets[nset] = [tag_to_idx[int(t)] for t in nt if int(t) in tag_to_idx]

        # Kenar NSET (displacement/sliding)
        for _d, ctag in gmsh.model.getEntities(1):
            nset = f"EDGE_{ctag}"
            nt, _, _ = gmsh.model.mesh.getNodes(1, ctag)
            ids = [tag_to_idx[int(t)] for t in nt if int(t) in tag_to_idx]
            if ids:
                nsets[nset] = ids

        for nset, ids in nsets.items():
            if not ids:
                continue
            lines.append(f"*NSET, NSET={nset}")
            lines.extend(_chunk_csv(ids))

        # FACE_EL_* (PART_* dışında) — DLOAD için ek ELSET
        for es_name, eids in elsets.items():
            if not es_name.startswith("FACE_EL_") or not eids:
                continue
            lines.append(f"*ELSET, ELSET={es_name}")
            lines.extend(_chunk_csv(eids))

        # Kullanılmayan part_materials uyarısı yok — section'lar materials bloğunda
        _ = part_materials
        _ = shell_thickness
        return "\n".join(lines) + "\n", nsets, elsets
    finally:
        gmsh.finalize()
        _gmsh_lock.release()


def _materials_inp_block(
    materials: list[dict[str, Any]], dimension: int, shell_thickness: float
) -> str:
    lines: list[str] = []
    if not materials:
        # Varsayılan çelik
        materials = [
            {
                "part_id": 0,
                "name": "DEFAULT_STEEL",
                "youngs_modulus": 210e9,
                "poisson_ratio": 0.3,
                "density": 7850.0,
            }
        ]

    seen_mat: set[str] = set()
    for m in materials:
        mname = _sanitize_name(str(m["name"]))
        if mname not in seen_mat:
            # KRİTİK BİRİM DÖNÜŞÜMÜ: malzeme kütüphanesi SI birimlerinde
            # saklıyor (Young modülü Pa, yoğunluk kg/m³ — bkz.
            # ARCHITECTURE.md#malzeme-kütüphanesi). Ama geometri mm, yükler
            # N cinsinden — CalculiX tutarlı bir birim sistemi gerektiriyor
            # (mm/N/MPa/tonne). Dönüştürmeden E'yi Pa olarak göndermek,
            # malzemeyi 1.000.000 kat daha sert gösteriyordu — gerçek bir
            # ankastre kiriş testinde elle hesapla (25.5mm) karşılaştırılıp
            # kanıtlandı: dönüşümsüz sonuç 0.0000226mm çıkıyordu (beklenenin
            # ~1 milyonda biri).
            #   E: Pa -> MPa (1 MPa = 1e6 Pa)
            #   yoğunluk: kg/m³ -> tonne/mm³ (1 kg/m³ = 1e-12 tonne/mm³)
            E_pa = float(m["youngs_modulus"])
            nu = float(m["poisson_ratio"])
            rho_kg_m3 = float(m["density"])
            E = E_pa / 1e6
            rho = rho_kg_m3 * 1e-12
            lines.append(f"*MATERIAL, NAME={mname}")
            lines.append("*ELASTIC")
            lines.append(f"{E:.6e}, {nu:.6g}")
            lines.append("*DENSITY")
            lines.append(f"{rho:.6e}")
            seen_mat.add(mname)
        elset = f"PART_{int(m['part_id'])}"
        if dimension == 2:
            lines.append(
                f"*SHELL SECTION, ELSET={elset}, MATERIAL={mname}"
            )
            lines.append(f"{shell_thickness:.6g}")
        else:
            lines.append(
                f"*SOLID SECTION, ELSET={elset}, MATERIAL={mname}"
            )
    return "\n".join(lines) + "\n"


def _bcs_inp_block(
    bcs: list[dict[str, Any]],
    nsets: dict[str, list[int]],
    elsets: dict[str, list[int]],
    dimension: int,
) -> tuple[str, str]:
    """BC kartlarını üretir — döndürür: (model_seviyesi, step_seviyesi).

    CalculiX/Abaqus format kuralı: `*BOUNDARY`/`*TRANSFORM` gibi kalıcı model
    tanımı kartları `*STEP`'in DIŞINDA kalabilir, ama `*CLOAD`/`*DLOAD` gibi
    yük kartları SADECE `*STEP` İÇİNDE olabilir — gerçek bir çalıştırmada
    `*CLOAD` dışarıda kalınca CalculiX "*CLOAD should only be used within a
    STEP" hatasıyla durduğu doğrulandı. Bu yüzden ikisi ayrı listelerde
    tutulup, step-seviyesi olanlar çağıran tarafından `*STEP`/`*STATIC` ile
    `*NODE FILE` arasına yerleştiriliyor.
    """
    model_lines: list[str] = []
    step_lines: list[str] = []
    for bc in bcs:
        btype = str(bc.get("type", "")).lower()
        if btype == "fixed":
            for fid in bc.get("face_ids") or []:
                nset = f"FACE_{int(fid)}"
                if nset not in nsets or not nsets[nset]:
                    continue
                model_lines.append("*BOUNDARY")
                model_lines.append(f"{nset}, 1, 3")
            for eid in bc.get("edge_ids") or []:
                nset = f"EDGE_{int(eid)}"
                if nset not in nsets or not nsets[nset]:
                    continue
                model_lines.append("*BOUNDARY")
                model_lines.append(f"{nset}, 1, 3")
            for nid in bc.get("node_ids") or []:
                model_lines.append("*BOUNDARY")
                model_lines.append(f"{int(nid)}, 1, 3")
        elif btype == "cload":
            fx = float(bc.get("fx", 0.0))
            fy = float(bc.get("fy", 0.0))
            fz = float(bc.get("fz", 0.0))
            node_ids = bc.get("node_ids") or []
            if node_ids:
                step_lines.append("*CLOAD")
                for nid in node_ids:
                    if abs(fx) > 0:
                        step_lines.append(f"{int(nid)}, 1, {fx:.6g}")
                    if abs(fy) > 0:
                        step_lines.append(f"{int(nid)}, 2, {fy:.6g}")
                    if abs(fz) > 0:
                        step_lines.append(f"{int(nid)}, 3, {fz:.6g}")
            for fid in bc.get("face_ids") or []:
                nset = f"FACE_{int(fid)}"
                ids = nsets.get(nset) or []
                if not ids:
                    continue
                n = len(ids)
                step_lines.append("*CLOAD")
                for nid in ids:
                    if abs(fx) > 0:
                        step_lines.append(f"{nid}, 1, {fx / n:.6g}")
                    if abs(fy) > 0:
                        step_lines.append(f"{nid}, 2, {fy / n:.6g}")
                    if abs(fz) > 0:
                        step_lines.append(f"{nid}, 3, {fz / n:.6g}")
            for eid in bc.get("edge_ids") or []:
                nset = f"EDGE_{int(eid)}"
                ids = nsets.get(nset) or []
                if not ids:
                    continue
                n = len(ids)
                step_lines.append("*CLOAD")
                for nid in ids:
                    if abs(fx) > 0:
                        step_lines.append(f"{nid}, 1, {fx / n:.6g}")
                    if abs(fy) > 0:
                        step_lines.append(f"{nid}, 2, {fy / n:.6g}")
                    if abs(fz) > 0:
                        step_lines.append(f"{nid}, 3, {fz / n:.6g}")
        elif btype == "pressure":
            mag = float(bc.get("magnitude", 0.0))
            if abs(mag) < 1e-30:
                continue
            for fid in bc.get("face_ids") or []:
                elset = f"FACE_EL_{int(fid)}"
                if elset in elsets and elsets[elset]:
                    step_lines.append("*DLOAD")
                    step_lines.append(f"{elset}, P, {mag:.6g}")
                    continue
                # 3D solid: yüzey ELSET yok → düğümlere dağıtılmış CLOAD
                nset = f"FACE_{int(fid)}"
                ids = nsets.get(nset) or []
                if not ids:
                    continue
                dx = float(bc.get("dx", 0.0))
                dy = float(bc.get("dy", 0.0))
                dz = float(bc.get("dz", -1.0))
                norm = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                fx, fy, fz = mag * dx / norm, mag * dy / norm, mag * dz / norm
                n = len(ids)
                step_lines.append(f"** pressure face {fid} as distributed CLOAD (no FACE_EL)")
                step_lines.append("*CLOAD")
                for nid in ids:
                    if abs(fx) > 0:
                        step_lines.append(f"{nid}, 1, {fx / n:.6g}")
                    if abs(fy) > 0:
                        step_lines.append(f"{nid}, 2, {fy / n:.6g}")
                    if abs(fz) > 0:
                        step_lines.append(f"{nid}, 3, {fz / n:.6g}")
        elif btype == "displacement":
            dofs = bc.get("dofs") or {"1": 0.0, "2": 0.0, "3": 0.0}
            targets: list[str] = []
            for eid in bc.get("edge_ids") or []:
                targets.append(f"EDGE_{int(eid)}")
            for fid in bc.get("face_ids") or []:
                targets.append(f"FACE_{int(fid)}")
            for nid in bc.get("node_ids") or []:
                model_lines.append("*BOUNDARY")
                for dof, val in dofs.items():
                    model_lines.append(
                        f"{int(nid)}, {int(dof)}, {int(dof)}, {float(val):.6g}"
                    )
            for nset in targets:
                if nset not in nsets:
                    continue
                model_lines.append("*BOUNDARY")
                for dof, val in dofs.items():
                    model_lines.append(f"{nset}, {int(dof)}, {int(dof)}, {float(val):.6g}")
        elif btype == "sliding":
            # Yerel eksen: normal = 1. DOF; teğet serbest. *TRANSFORM + *BOUNDARY
            normal = bc.get("normal") or [0.0, 0.0, 1.0]
            nx, ny, nz = float(normal[0]), float(normal[1]), float(normal[2])
            nlen = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            nx, ny, nz = nx / nlen, ny / nlen, nz / nlen
            # İkinci eksen: normal × dünya Z (veya X)
            if abs(nz) < 0.9:
                tx, ty, tz = -ny, nx, 0.0
            else:
                tx, ty, tz = 0.0, -nz, ny
            tlen = math.sqrt(tx * tx + ty * ty + tz * tz) or 1.0
            tx, ty, tz = tx / tlen, ty / tlen, tz / tlen
            nsets_targets: list[str] = []
            for eid in bc.get("edge_ids") or []:
                nsets_targets.append(f"EDGE_{int(eid)}")
            for fid in bc.get("face_ids") or []:
                nsets_targets.append(f"FACE_{int(fid)}")
            for nset in nsets_targets:
                if nset not in nsets or not nsets[nset]:
                    continue
                model_lines.append(f"*TRANSFORM, NSET={nset}, TYPE=C")
                model_lines.append(
                    f"{nx:.6g}, {ny:.6g}, {nz:.6g}, {tx:.6g}, {ty:.6g}, {tz:.6g}"
                )
                model_lines.append("*BOUNDARY")
                # Local 1 (normal) sabit; 2-3 serbest (sliding)
                model_lines.append(f"{nset}, 1, 1")
        elif btype == "gravity":
            gx = float(bc.get("gx", 0.0))
            gy = float(bc.get("gy", 0.0))
            gz = float(bc.get("gz", -9810.0))
            mag = math.sqrt(gx * gx + gy * gy + gz * gz) or 1.0
            part_elsets = [
                name for name in elsets if name.startswith("PART_") and elsets[name]
            ]
            if not part_elsets:
                part_elsets = ["PART_0"]
            step_lines.append("*DLOAD")
            for pel in part_elsets:
                step_lines.append(
                    f"{pel}, GRAV, {mag:.6g}, {gx / mag:.6g}, {gy / mag:.6g}, {gz / mag:.6g}"
                )
        elif btype == "bearing":
            mag = float(bc.get("magnitude", 0.0))
            axis = bc.get("axis") or [0.0, 0.0, -1.0]
            ax, ay, az = float(axis[0]), float(axis[1]), float(axis[2])
            for fid in bc.get("face_ids") or []:
                nset = f"FACE_{int(fid)}"
                ids = nsets.get(nset) or []
                if len(ids) < 2 or abs(mag) < 1e-30:
                    continue
                weights = [
                    max(0.0, math.cos(math.pi * i / max(len(ids) - 1, 1)))
                    for i in range(len(ids))
                ]
                wsum = sum(weights) or 1.0
                step_lines.append(f"** bearing load face {fid}")
                step_lines.append("*CLOAD")
                for nid, w in zip(ids, weights):
                    f = mag * w / wsum
                    if abs(ax) > 0:
                        step_lines.append(f"{nid}, 1, {f * ax:.6g}")
                    if abs(ay) > 0:
                        step_lines.append(f"{nid}, 2, {f * ay:.6g}")
                    if abs(az) > 0:
                        step_lines.append(f"{nid}, 3, {f * az:.6g}")
        else:
            model_lines.append(f"** unknown bc type: {btype}")

    _ = dimension
    model_block = ("\n".join(model_lines) + "\n") if model_lines else ""
    step_block = ("\n".join(step_lines) + "\n") if step_lines else ""
    return model_block, step_block


def _static_step_block(step_bc_lines: str = "") -> str:
    return (
        "*STEP\n"
        "*STATIC\n"
        f"{step_bc_lines}"
        "*NODE FILE\n"
        "U\n"
        "*EL FILE\n"
        "S\n"
        "*END STEP\n"
    )


def _chunk_csv(ids: list[int], per_line: int = 10) -> list[str]:
    out: list[str] = []
    for i in range(0, len(ids), per_line):
        out.append(", ".join(str(x) for x in ids[i : i + per_line]))
    return out
