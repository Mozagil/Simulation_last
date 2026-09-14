"""Çözücü girdisini DB anlığından yeniden üretmek (0.5.2).

`.inp` saklanmaz: `bcs`, `materials_snapshot`, `dimension`, `element_size`,
`element_scheme`, `shell_thickness` satırda durur; mesh dosyası hâlâ
`uploads/meshes/` altındadır. Aynı parametrelerle `CalculiXAdapter.build_input`
birebir aynı kartları üretir.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.models.run import AnalysisRun
from app.solvers.base import InputArtifact
from app.solvers.calculix import CalculiXAdapter

logger = logging.getLogger(__name__)


def discard_solver_input(run: AnalysisRun) -> None:
    """Başarılı çözümden sonra `.inp`'i siler; yol kolonunu boşaltır.

    `.inputs.npz` / `.train.npz` / `.frd.gz` durur. Girdi yeniden üretilebilir.
    """
    path_s = run.inp_path
    if path_s:
        p = Path(path_s)
        if p.is_file():
            p.unlink()
            logger.info("Çözücü girdisi silindi (yeniden üretilebilir): %s", p)
    run.inp_path = None


def build_input_from_snapshot(
    *,
    mesh_path: Path,
    output_dir: Path,
    job_name: str,
    dimension: int,
    bcs: list[dict[str, Any]],
    materials: list[dict[str, Any]],
    shell_thickness: float = 1.0,
    analysis_type: str = "static",
    n_modes: int = 10,
    element_scheme: str | None = None,
) -> InputArtifact:
    """DB'de saklanan anlıktan `.inp` üretir. `element_scheme` yalnız kayıt içindir."""
    _ = element_scheme
    adapter = CalculiXAdapter()
    return adapter.build_input(
        {
            "mesh_path": mesh_path,
            "dimension": dimension,
            "output_dir": output_dir,
            "job_name": job_name,
            "materials": materials,
            "shell_thickness": shell_thickness,
            "bcs": bcs,
            "analysis_type": analysis_type,
            "n_modes": n_modes,
        }
    )


def rebuild_input_for_run(
    run: AnalysisRun,
    mesh_path: Path,
    output_dir: Path,
    job_name: str = "rebuild",
) -> InputArtifact:
    analysis_type = str((run.scalars or {}).get("_analysis_type") or "static")
    n_modes = int((run.scalars or {}).get("n_frequencies") or 10)
    return build_input_from_snapshot(
        mesh_path=mesh_path,
        output_dir=output_dir,
        job_name=job_name,
        dimension=run.dimension,
        bcs=list(run.bcs or []),
        materials=list(run.materials_snapshot or []),
        shell_thickness=float(run.shell_thickness or 1.0),
        analysis_type=analysis_type,
        n_modes=n_modes,
        element_scheme=run.element_scheme,
    )
