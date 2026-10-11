"""LS-DYNA keyword içe aktarma API — 1.21e-1 (`/crash/import/dyna`).

Yalnız okuma + çeviri: .k / .dyn (ve *INCLUDE dosyaları) yüklenir, ara
modelden OpenRadioss adaptör parametrelerine çevrilir, çeviri raporu
döner. Koşu başlatılmaz; parametreler `uploads/crash_import/{id}/
import.json`'a yazılır (DB şeması değişmez). Kart yazmak / çözmek
mevcut adaptörün işi.

Birim çarpanları (dosya → mm, kg, s) ve hız etkisi için ε̇ listesi
mühendisten gelir; tahmin edilmez.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.importers.dyna_k import SUPPORTED_SUFFIXES, DynaParseError, read_keyword_file
from app.importers.dyna_material import DynaMaterialError, DynaUnits, to_crash_materials
from app.importers.dyna_mesh import DynaMeshError, to_crash_mesh
from app.importers.dyna_setup import to_crash_setup

router = APIRouter(prefix="/crash/import", tags=["crash"])

IMPORT_DIR = Path("uploads") / "crash_import"
MAX_FILE_BYTES = 200 * 1024 * 1024


def _parse_rates(raw: str) -> list[float]:
    try:
        return [float(x) for x in raw.replace(";", ",").split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail=f"ε̇ listesi okunamadı: '{raw}'") from None


async def _save(upload: UploadFile, folder: Path) -> Path:
    name = Path(upload.filename or "").name
    if not name or name in (".", ".."):
        raise HTTPException(status_code=422, detail="Dosya adı boş.")
    target = folder / name
    if target.exists():
        raise HTTPException(status_code=422, detail=f"'{name}' iki kez yüklendi.")
    data = await upload.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"'{name}' 200 MB'tan büyük.")
    target.write_bytes(data)
    return target


@router.post("/dyna")
async def import_dyna(
    main: UploadFile = File(..., description=".k / .dyn / .key ana dosya"),
    includes: list[UploadFile] = File(default=[], description="*INCLUDE dosyaları"),
    length_to_mm: float = Form(..., description="Dosya uzunluk birimi → mm"),
    mass_to_kg: float = Form(..., description="Dosya kütle birimi → kg"),
    time_to_s: float = Form(..., description="Dosya zaman birimi → s"),
    rates_per_s: str = Form(default="", description="Hız etkisi için ε̇ (1/s), virgüllü; boş = yok"),
) -> dict[str, Any]:
    if Path(main.filename or "").suffix.lower() not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=422, detail=f"Ana dosya uzantısı {', '.join(SUPPORTED_SUFFIXES)} olmalı."
        )
    rates = _parse_rates(rates_per_s)
    try:
        units = DynaUnits(length_to_mm, mass_to_kg, time_to_s)
    except DynaMaterialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    import_id = uuid.uuid4().hex
    folder = IMPORT_DIR / import_id
    folder.mkdir(parents=True)
    try:
        main_path = await _save(main, folder)
        for inc in includes:
            await _save(inc, folder)
        model = read_keyword_file(main_path)
        mesh = to_crash_mesh(model, length_to_mm=units.length_to_mm)
        materials = to_crash_materials(model, mesh, units, rates_per_s=rates)
        setup = to_crash_setup(model, mesh, units)
    except (DynaParseError, DynaMeshError, DynaMaterialError) as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    params = mesh.adapter_params()
    materials.apply(params)
    setup.apply(params)
    report = {
        "import_id": import_id,
        "file": main_path.name,
        "units": {"length_to_mm": length_to_mm, "mass_to_kg": mass_to_kg, "time_to_s": time_to_s},
        "rates_per_s": sorted(set(rates)),
        "parse": model.summary(),
        "mesh": mesh.report(),
        "materials": materials.report(),
        "setup": setup.report(),
    }
    (folder / "import.json").write_text(
        json.dumps({"report": report, "params": params}), encoding="utf-8"
    )
    return report


@router.get("/dyna/{import_id}")
def get_import(import_id: str) -> dict[str, Any]:
    """Kayıtlı çeviri raporu (parametreler hariç; ağ boyutu büyük olabilir)."""
    if len(import_id) != 32 or not all(c in "0123456789abcdef" for c in import_id):
        raise HTTPException(status_code=404, detail="İçe aktarma bulunamadı.")
    path = IMPORT_DIR / import_id / "import.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="İçe aktarma bulunamadı.")
    return json.loads(path.read_text(encoding="utf-8"))["report"]
