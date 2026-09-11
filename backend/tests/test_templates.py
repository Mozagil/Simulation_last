"""Şablon altyapısı (0.4.1) + ilk şablon uçtan uca (0.4.2).

Uçtan uca test, ankastre kirişi ŞABLONDAN üretip mevcut mesh/BC/çözüm
akışıyla çözer ve Faz 0'ın doğrulanmış değerlerini (23.92 mm / 330.7 MPa)
bekler. `test_reference_validation.py` aynı vakayı elle kurulmuş kutuyla
çözer; ikisi birlikte "şablon altyapısı geometriyi doğru üretiyor ve
bölgeleri doğru yüzeye bağlıyor" iddiasını kilitler.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.templates import (
    TEMPLATES,
    AnalyticInput,
    TemplateError,
    UnknownTemplateError,
    build_template,
    get_template,
    list_templates,
)
from app.templates.cantilever_beam import REGION_FIXED, REGION_LOAD

# Faz 0 referans vakası — test_reference_validation.py ile aynı sayılar.
REF_PARAMS = {"length": 500.0, "thickness": 10.0, "width": 50.0}
FORCE_N = 500.0
E_PA = 210e9
EXPECTED_DISP_MM = 23.92
EXPECTED_MAX_VM_MPA = 330.7
TOLERANCE = 0.05

requires_ccx = pytest.mark.skipif(
    shutil.which("ccx") is None,
    reason="CalculiX (ccx) kurulu değil — bu test gerçek çözüm gerektirir",
)


# --- kayıt mekanizması --------------------------------------------------------


def test_registry_lists_cantilever():
    ids = [t.id for t in list_templates()]
    assert "cantilever_beam" in ids
    assert len(ids) == len(set(ids)), "şablon id'leri benzersiz olmalı"
    assert get_template("cantilever_beam") is TEMPLATES["cantilever_beam"]


def test_unknown_template_raises():
    with pytest.raises(UnknownTemplateError):
        get_template("yok_boyle_sablon")


def test_params_schema_is_json_schema_with_units():
    schema = get_template("cantilever_beam").params_schema()
    assert set(schema["properties"]) == {"length", "thickness", "width"}
    for prop in schema["properties"].values():
        assert prop["type"] == "number"
        assert prop["exclusiveMinimum"] == 0
        assert prop["unit"] == "mm"


# --- parametre doğrulama --------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        {"length": -1},
        {"thickness": 0},
        {"width": -50},
        {"length": "abc"},
        # geometrik kısıt: L < 5T kiriş teorisini geçersiz kılar
        {"length": 40, "thickness": 10},
    ],
)
def test_invalid_params_rejected(raw):
    with pytest.raises(ValidationError):
        get_template("cantilever_beam").parse_params(raw)


def test_defaults_are_reference_case():
    p = get_template("cantilever_beam").parse_params({})
    assert p.model_dump() == REF_PARAMS


# --- kurucu + bölgeler --------------------------------------------------------


def test_build_writes_step_and_finds_regions(tmp_path):
    t = get_template("cantilever_beam")
    p = t.parse_params({"length": 300, "thickness": 20, "width": 40})
    r = build_template(t, p, tmp_path / "beam.step")

    assert r.step_path.exists() and r.step_path.stat().st_size > 0
    assert set(r.regions) == {REGION_FIXED, REGION_LOAD}
    assert len(r.regions[REGION_FIXED]) == 1
    assert len(r.regions[REGION_LOAD]) == 1
    assert r.regions[REGION_FIXED] != r.regions[REGION_LOAD]

    xmin, ymin, zmin, xmax, ymax, zmax = r.bounding_box
    assert (xmax - xmin, ymax - ymin, zmax - zmin) == pytest.approx((300, 20, 40), abs=1e-5)


def test_regions_found_geometrically_not_by_fixed_tag(tmp_path):
    """Bölge seçimi sınır kutusuyla yapılıyor; STEP'i tekrar açıp yüzeyin
    gerçekten x=0 / x=L düzleminde olduğunu bağımsız olarak doğrula."""
    import gmsh

    t = get_template("cantilever_beam")
    p = t.parse_params({})
    r = build_template(t, p, tmp_path / "beam.step")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(r.step_path))
        for name, x_target in ((REGION_FIXED, 0.0), (REGION_LOAD, p.length)):
            (tag,) = r.regions[name]
            xmin, _, _, xmax, _, _ = gmsh.model.getBoundingBox(2, tag)
            assert xmin == pytest.approx(x_target, abs=1e-5)
            assert xmax == pytest.approx(x_target, abs=1e-5)
    finally:
        gmsh.finalize()


def test_build_fails_loudly_when_region_missing(tmp_path):
    """Kurucu bölge yüzeyini üretemezse sessizce geçmemeli."""
    from dataclasses import replace

    from app.templates.base import Region, plane_at

    t = get_template("cantilever_beam")
    broken = replace(
        t,
        regions=t.regions
        + (Region(name="hayali", description="", select=plane_at("x", 12345.0), expected_faces=1),),
    )
    with pytest.raises(TemplateError, match="hayali"):
        build_template(broken, t.parse_params({}), tmp_path / "x.step")


# --- analitik referans ----------------------------------------------------------


def test_analytic_matches_beam_theory():
    t = get_template("cantilever_beam")
    p = t.parse_params(REF_PARAMS)
    out = t.analytic(p, AnalyticInput(force_n=FORCE_N, youngs_modulus_pa=E_PA))
    assert out["max_displacement"] == pytest.approx(23.81, abs=0.01)
    assert out["max_von_mises"] == pytest.approx(300.0, abs=0.01)


# --- uçtan uca: şablon -> mesh -> BC (bölgeden) -> çözüm ------------------------


@requires_ccx
def test_cantilever_template_end_to_end_matches_reference(tmp_path):
    """0.4.2: tek şablonla tüm akış; sonuç Faz 0 referansıyla eşleşmeli."""
    from app.mesh.base import MeshParams
    from app.mesh.gmsh_adapter import GmshMesherAdapter
    from app.solvers.calculix import CalculiXAdapter

    t = get_template("cantilever_beam")
    p = t.parse_params(REF_PARAMS)
    built = build_template(t, p, tmp_path / "beam.step")

    adapter = GmshMesherAdapter()
    geom = adapter.import_geometry(built.step_path)
    mesh = adapter.generate_mesh(
        geom, MeshParams(element_size=8.0, dimension=3, element_scheme="tet")
    )
    assert "Tetrahedron10" in mesh.element_type_counts

    params = {
        "mesh_path": mesh.mesh_path,
        "dimension": 3,
        "output_dir": tmp_path / "run",
        "job_name": "tpl",
        "materials": [
            {"part_id": 0, "name": "S235", "youngs_modulus": E_PA, "poisson_ratio": 0.3, "density": 7850.0}
        ],
        # BC'ler ŞABLONUN bölgelerinden — yüzey numarası elle yazılmıyor.
        "bcs": [
            {"type": "fixed", "face_ids": built.regions[REGION_FIXED]},
            {"type": "cload", "face_ids": built.regions[REGION_LOAD], "fx": 0.0, "fy": -FORCE_N, "fz": 0.0},
        ],
    }
    ccx = CalculiXAdapter()
    job = ccx.submit(ccx.build_input(params))
    for _ in range(600):
        status = ccx.poll_status(job)
        if status.state in ("done", "failed"):
            break
    assert status.state == "done", f"çözüm başarısız: {status}"
    s = ccx.parse_results(job).scalars

    assert s["max_displacement"] == pytest.approx(EXPECTED_DISP_MM, rel=TOLERANCE)
    assert s["max_von_mises"] == pytest.approx(EXPECTED_MAX_VM_MPA, rel=TOLERANCE)

    # Analitik referans da aynı akışta tutmalı (0.4.5'in ön izlemesi).
    ana = t.analytic(p, AnalyticInput(force_n=FORCE_N, youngs_modulus_pa=E_PA))
    assert s["max_displacement"] == pytest.approx(ana["max_displacement"], rel=TOLERANCE)


# --- DB bağlama -------------------------------------------------------------------


def _db_available() -> bool:
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from app.db.session import SessionLocal

    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except OperationalError:
        return False


requires_db = pytest.mark.skipif(
    not _db_available(),
    reason="PostgreSQL bağlantısı yok (DATABASE_URL ayarlı değil ya da servis kapalı)",
)


@requires_db
def test_create_geometry_from_template_persists_groups():
    from app.api.geometry import TESSELLATION_DIR, UPLOAD_DIR
    from app.db.session import SessionLocal
    from app.models.geometry import Geometry, PhysicalGroup
    from app.templates.service import create_geometry_from_template

    db = SessionLocal()
    try:
        geo, regions = create_geometry_from_template(db, "cantilever_beam", {"length": 200})
        try:
            assert geo.current_filename == f"{geo.id}.step"
            assert (UPLOAD_DIR / geo.current_filename).exists()
            assert (TESSELLATION_DIR / f"{geo.id}.stl").exists()

            groups = db.query(PhysicalGroup).filter(PhysicalGroup.geometry_id == geo.id).all()
            assert {g.name: g.entity_tags for g in groups} == regions
            assert set(regions) == {REGION_FIXED, REGION_LOAD}
        finally:
            (UPLOAD_DIR / geo.current_filename).unlink(missing_ok=True)
            for f in TESSELLATION_DIR.glob(f"{geo.id}.*"):
                f.unlink()
            db.delete(db.get(Geometry, geo.id))
            db.commit()
    finally:
        db.close()


@requires_db
def test_create_geometry_from_template_invalid_params_leaves_no_row():
    from app.db.session import SessionLocal
    from app.models.geometry import Geometry
    from app.templates.service import create_geometry_from_template

    db = SessionLocal()
    try:
        before = db.query(Geometry).count()
        with pytest.raises(ValidationError):
            create_geometry_from_template(db, "cantilever_beam", {"length": -5})
        assert db.query(Geometry).count() == before
    finally:
        db.close()
