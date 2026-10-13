"""CFD mesh API'si — Faz 2.5 (sanal rüzgâr tüneli + snappyHexMesh | cfMesh).

POST /cfd/mesh            geometri + tünel + snappy ayarları → mesh işi (arka plan)
GET  /cfd/mesh/{mesh_id}  durum + checkMesh / snappy verisi + yama listesi

Mesh ayrı bir adımdır (arayüzde 2 · Mesh): mühendis checkMesh verisine bakar,
sonra ``/cfd/solve`` ``mesh_id`` ile bu ağı kullanır. Bölgeler geometrinin
yüzey (dim 2) Physical Group'larıdır — her biri ayrı yama (yama başına kuvvet);
bölgeye girmeyen yüzeyler ``body`` yamasıdır.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.geometry import UPLOAD_DIR, _get_geometry_or_404
from app.db.session import get_db
from app.jobs.progress import get_hub
from app.mesh.cfd_mesher import (
    CFMESH_SCRIPT,
    MESH_SCRIPT,
    SnappyParams,
    TunnelParams,
    export_surface_stl,
    parse_check_mesh,
    parse_snappy_log,
    tunnel_patches,
    write_cfmesh_case,
    write_tunnel_case,
)
from app.models.geometry import PhysicalGroup
from app.solvers.openfoam import docker_command, resolve_openfoam_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cfd/mesh", tags=["cfd"])

CFD_MESH_DIR = Path("uploads") / "cfd_meshes"

_CONTROL_DICT = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}

application     snappyHexMesh;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         0;
deltaT          1;
writeControl    timeStep;
writeInterval   1;
writeFormat     ascii;
writePrecision  8;
timeFormat      general;
runTimeModifiable false;
"""


#: snappyHexMesh / checkMesh şema ve çözücü sözlüklerini de okur (yalnız varlık).
_FV_SCHEMES = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSchemes;
}

ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default none; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
wallDist { method meshWave; }
"""

_FV_SOLUTION = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}

solvers {}
"""


class CfdMeshRequest(BaseModel):
    geometry_id: int
    #: Mesh'leyici (NLGEOM gibi seçim; otomatik seçim yok). cfMesh için
    #: OPENFOAM_DOCKER_IMAGE cfMesh derlenmiş imaj olmalı (backend/docker/openfoam).
    mesher: Literal["snappy", "cfmesh"] = "snappy"
    tunnel: TunnelParams
    snappy: SnappyParams = Field(default_factory=SnappyParams)
    #: Ayrı yama olacak yüzey bölgeleri (Physical Group adları); None = tüm yüzey bölgeleri.
    regions: list[str] | None = None
    wait: bool = False


def mesh_dir(mesh_id: str) -> Path:
    return CFD_MESH_DIR / mesh_id


def read_mesh_meta(mesh_id: str) -> dict[str, Any] | None:
    path = mesh_dir(mesh_id) / "mesh.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_meta(meta: dict[str, Any]) -> None:
    path = mesh_dir(str(meta["mesh_id"])) / "mesh.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _run_mesh(mesh_id: str) -> None:
    meta = read_mesh_meta(mesh_id)
    if meta is None:
        return
    hub = get_hub()
    hub.update(mesh_id, state="running", percent=0.0, message="blockMesh → snappyHexMesh → checkMesh")
    case = Path(meta["case_dir"])
    try:
        image = resolve_openfoam_image()
        if image is None:
            raise RuntimeError("OpenFOAM yapılandırılmamış (OPENFOAM_DOCKER_IMAGE)")
        cfmesh = meta.get("mesher") == "cfmesh"
        script = CFMESH_SCRIPT if cfmesh else MESH_SCRIPT
        proc = subprocess.run(
            docker_command(image, case, script), capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        check_log = case / "log.checkMesh"
        meta["check"] = parse_check_mesh(check_log.read_text(encoding="utf-8", errors="replace")) if check_log.is_file() else {}
        if cfmesh:
            cf_log = case / "log.cartesianMesh"
            text = cf_log.read_text(encoding="utf-8", errors="replace") if cf_log.is_file() else ""
            meta["cfmesh"] = {
                "finished": "Finished renaming boundary patches" in text,
                "layer_cells_added": sum(int(n) for n in re.findall(r"Number of newly generated cells (\d+)", text)),
            }
            if "command not found" in text or "cartesianMesh: command not found" in proc.stdout:
                raise RuntimeError("Bu imajda cartesianMesh (cfMesh) yok — backend/docker/openfoam imajını kullanın.")
            finished = bool(meta["cfmesh"]["finished"])
            logs = ("log.cartesianMesh", "log.checkMesh")
        else:
            snappy_log = case / "log.snappyHexMesh"
            meta["snappy"] = parse_snappy_log(snappy_log.read_text(encoding="utf-8", errors="replace")) if snappy_log.is_file() else {}
            finished = bool(meta["snappy"].get("finished"))
            logs = ("log.blockMesh", "log.surfaceFeatureExtract", "log.snappyHexMesh")
        ok = (case / "constant" / "polyMesh" / "owner").is_file() and finished
        if not ok:
            failed = next((n for n in logs if "FOAM FATAL" in _tail(case / n)), None)
            detail = _tail(case / failed, 600) if failed else proc.stdout[-600:]
            raise RuntimeError(f"Mesh üretilemedi ({failed or 'bilinmiyor'}): {detail}")
        cells = meta["check"].get("cells")
        meta["status"] = "meshed"
        meta["message"] = f"mesh hazır · {cells} hücre · checkMesh {'OK' if meta['check'].get('mesh_ok') else str(meta['check'].get('failed_checks')) + ' kontrol başarısız'}"
        _write_meta(meta)
        hub.update(mesh_id, state="done", percent=100.0, message=meta["message"])
    except Exception as exc:  # noqa: BLE001 — arka plan işi
        logger.warning("cfd mesh başarısız mesh_id=%s: %s", mesh_id, exc)
        meta["status"] = "failed"
        meta["message"] = str(exc)
        _write_meta(meta)
        hub.update(mesh_id, state="failed", message=str(exc))


def _tail(path: Path, n: int = 2000) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[-n:] if path.is_file() else ""


@router.post("")
def cfd_mesh(body: CfdMeshRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> dict[str, Any]:
    geo = _get_geometry_or_404(db, body.geometry_id)
    groups = (
        db.query(PhysicalGroup)
        .filter(PhysicalGroup.geometry_id == geo.id, PhysicalGroup.dim == 2)
        .order_by(PhysicalGroup.id)
        .all()
    )
    available = {g.name: list(g.entity_tags) for g in groups}
    wanted = list(available) if body.regions is None else body.regions
    missing = sorted(set(wanted) - set(available))
    if missing:
        raise HTTPException(status_code=422, detail=f"Geometride olmayan yüzey bölgesi: {', '.join(missing)}")
    mesh_id = str(uuid.uuid4())
    case = mesh_dir(mesh_id) / "case"
    try:
        stl = export_surface_stl(
            UPLOAD_DIR / geo.current_filename,
            case / "constant" / "triSurface" / "body.stl",
            regions={name: available[name] for name in wanted},
            size_mm=body.snappy.stl_size_mm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    (case / "system").mkdir(parents=True, exist_ok=True)
    for name, text in (("controlDict", _CONTROL_DICT), ("fvSchemes", _FV_SCHEMES), ("fvSolution", _FV_SOLUTION)):
        (case / "system" / name).write_text(text, encoding="utf-8", newline="\n")
    if body.mesher == "cfmesh":
        box = write_cfmesh_case(case, stl, body.tunnel, body.snappy)
    else:
        box = write_tunnel_case(case, stl, body.tunnel, body.snappy)
    meta: dict[str, Any] = {
        "mesh_id": mesh_id,
        "geometry_id": geo.id,
        "mesher": body.mesher,
        "case_dir": str(case),
        "status": "pending",
        "message": "mesh kuyrukta",
        "tunnel": body.tunnel.model_dump(),
        "snappy": {},
        "snappy_params": body.snappy.model_dump(),
        "surface": {
            "regions": stl.regions,
            "triangles": stl.triangles,
            "triangles_per_region": stl.triangles_per_region,
            "open_edges": stl.open_edges,
            "bbox_m": list(stl.bbox_m),
        },
        "domain": {"min_m": list(box.lo), "max_m": list(box.hi), "background_cells": list(box.cells), "body_length_m": box.body_length_m},
        "patches": tunnel_patches(stl.regions, body.tunnel.ground),
        "check": {},
    }
    _write_meta(meta)
    hub = get_hub()
    hub.create(mesh_id)
    hub.update(mesh_id, state="running", percent=0.0, message=meta["message"])
    if body.wait:
        _run_mesh(mesh_id)
        meta = read_mesh_meta(mesh_id) or meta
    else:
        background_tasks.add_task(_run_mesh, mesh_id)
    return {**meta, "progress_url": f"/cfd/mesh/{mesh_id}"}


@router.get("/{mesh_id}")
def cfd_mesh_snapshot(mesh_id: str) -> dict[str, Any]:
    meta = read_mesh_meta(mesh_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="cfd mesh yok")
    live = get_hub().get(mesh_id)
    if live is not None:
        meta["hub_state"] = live.state
    return meta
