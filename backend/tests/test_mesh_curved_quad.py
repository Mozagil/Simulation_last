"""2D quad mesh eğri (silindir) yüzeylerde çökmesin — kullanıcı 2026-10-07.

Ölçülen hata: Mesh.Algorithm 8 door_beam impaktörünün çeyrek-yay yüzlerinde
yüz başına ~50 uzun şerit eleman (minSICN medyan 0.20) üretiyordu.
"""

from __future__ import annotations

from pathlib import Path

import gmsh
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from tests.test_crash_solve import _clean_state  # noqa: F401 (autouse temizlik)
from tests.test_materials import requires_db

client = TestClient(app)


@requires_db
def test_door_beam_impactor_quad_mesh_quality():
    created = client.post("/templates/door_beam_shell/create", json={})
    assert created.status_code == 200, created.text
    gid = created.json()["geometry_id"]
    r = client.post(f"/geometry/{gid}/mesh", json={"dimension": 2, "element_size": 6, "element_scheme": "quad"})
    assert r.status_code == 200, r.text
    mesh_path = Path(r.json()["mesh_path"])

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(mesh_path))
        curved = []
        for _d, tag in gmsh.model.getEntities(2):
            types, tags, _ = gmsh.model.mesh.getElements(2, tag)
            elems = np.concatenate(tags)
            quads = sum(len(e) for t, e in zip(types, tags) if t == 3)
            q = np.array(gmsh.model.mesh.getElementQualities(elems, "minSICN"))
            curved.append((len(elems), quads, float(np.median(q))))
    finally:
        gmsh.finalize()
    # Her yüz: yüzlerce eleman, çoğunluğu quad, medyan kalite iyi (eski: ~50 eleman, 0.20).
    for n, quads, med in curved:
        assert n > 300, curved
        assert quads / n > 0.95, curved
        assert med > 0.8, curved


def _face_counts(mesh_path: Path) -> dict[int, int]:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(mesh_path))
        out = {}
        for _d, tag in gmsh.model.getEntities(2):
            _types, tags, _ = gmsh.model.mesh.getElements(2, tag)
            out[tag] = int(sum(len(e) for e in tags))
        return out
    finally:
        gmsh.finalize()


@requires_db
def test_remesh_face_sizes_refines_only_selected_face():
    """Remesh (kullanıcı 2026-10-07): seçili yüzey yerel boyutla, diğerleri değişmez."""
    gid = client.post("/templates/crash_box_shell/create", json={}).json()["geometry_id"]
    base = client.post(f"/geometry/{gid}/mesh", json={"dimension": 2, "element_size": 8, "element_scheme": "quad"})
    assert base.status_code == 200, base.text
    before = _face_counts(Path(base.json()["mesh_path"]))
    face = max(before, key=before.get)
    r = client.post(
        f"/geometry/{gid}/mesh",
        json={"dimension": 2, "element_size": 8, "element_scheme": "quad", "face_sizes": {str(face): 4}},
    )
    assert r.status_code == 200, r.text
    after = _face_counts(Path(r.json()["mesh_path"]))
    # boyut yarıya → eleman sayısı ~4 kat (kenar geçişleri payı)
    assert after[face] > 3 * before[face], (before, after)
    for f, n in before.items():
        if f != face:
            assert abs(after[f] - n) <= 0.35 * n, (f, before, after)
