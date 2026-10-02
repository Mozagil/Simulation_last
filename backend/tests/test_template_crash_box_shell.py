"""Kabuk crash box şablonu (1.13b): orta yüzey tüp, hacim yok.

Kilitlenen şey: STEP'te hacim yok, tam dört yüzey var ve kenar paylaşıyor
(2D mesh tek parça, uyumlu), orta yüzey alanı × t solid kutu hacmine eşit
(kütle aynı), uç bölgeleri dörder kenar; 2D mesh → OpenRadioss /SHELL.
"""

from __future__ import annotations

import gmsh
import pytest
from pydantic import ValidationError

from app.mesh.openradioss_export import gmsh_msh_to_radioss
from app.templates import TemplateError, build_template, get_template
from app.templates.crash_box_plate import CrashBoxPlateParams, box_volume_mm3
from app.templates.crash_box_shell import (
    REGION_BOX_BACK,
    REGION_BOX_FRONT,
    CrashBoxShellParams,
    shell_area_mm2,
    shell_volume_mm3,
)


def _open(step_path, sew=True):
    """Mesh katmanı (`import_geometry`) yüzey-only dosyayı dikişli açar; aynısı."""
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("Geometry.OCCSewFaces", 1 if sew else 0)
    gmsh.open(str(step_path))


def test_registered_surface_only_with_symbols():
    t = get_template("crash_box_shell")
    assert t.surface_only is True
    assert {"crash", "kabuk"} <= set(t.tags)
    assert t.analytic is None
    for name, prop in t.params_schema()["properties"].items():
        if prop.get("type") in ("number", "integer"):
            assert prop.get("symbol"), f"{name} sembolsüz"


def test_four_mid_surfaces_no_volume_and_area(tmp_path):
    t = get_template("crash_box_shell")
    p = t.parse_params({})
    r = build_template(t, p, tmp_path / "cbs.step")
    _open(r.step_path)
    try:
        assert gmsh.model.getEntities(3) == []
        faces = [tag for _d, tag in gmsh.model.getEntities(2)]
        assert len(faces) == 4
        area = sum(gmsh.model.occ.getMass(2, f) for f in faces)
        assert area == pytest.approx(shell_area_mm2(p), rel=1e-9)
        # orta yüzey kesiti: y ∈ [t/2, h−t/2], z ∈ [t/2, b−t/2]
        x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(-1, -1)
        # OCC sınır kutusu ~1e-7 tolerans payı taşır
        assert (x0, x1) == pytest.approx((0.0, p.box_length), abs=1e-6)
        assert (y0, y1) == pytest.approx((p.wall / 2, p.box_height - p.wall / 2), abs=1e-6)
        assert (z0, z1) == pytest.approx((p.wall / 2, p.box_width - p.wall / 2), abs=1e-6)
        # dikişli açılışta yüzeyler kenar paylaşır: 4 uzun + 8 uç kenar = 12
        assert len(gmsh.model.getEntities(1)) == 12
    finally:
        gmsh.finalize()


def test_unsewn_step_duplicates_shared_edges(tmp_path):
    """Neden dikiş: Gmsh STEP yazıcısı ortak kenarları ikizliyor (16 ≠ 12)."""
    t = get_template("crash_box_shell")
    r = build_template(t, t.parse_params({}), tmp_path / "cbs.step")
    _open(r.step_path, sew=False)
    try:
        assert len(gmsh.model.getEntities(1)) == 16
    finally:
        gmsh.finalize()


def test_mass_equals_solid_box_with_same_dimensions():
    for raw in ({}, {"box_length": 250.0, "box_height": 60.0, "box_width": 45.0, "wall": 2.0}):
        sp = CrashBoxShellParams.model_validate(raw)
        solid = CrashBoxPlateParams(
            box_length=sp.box_length, box_height=sp.box_height, box_width=sp.box_width, wall=sp.wall
        )
        assert shell_volume_mm3(sp) == pytest.approx(box_volume_mm3(solid), rel=1e-12)


def test_end_regions_are_four_edges_each(tmp_path):
    t = get_template("crash_box_shell")
    p = t.parse_params({})
    r = build_template(t, p, tmp_path / "cbs.step")
    assert len(r.regions[REGION_BOX_FRONT]) == 4
    assert len(r.regions[REGION_BOX_BACK]) == 4
    assert not set(r.regions[REGION_BOX_FRONT]) & set(r.regions[REGION_BOX_BACK])


def test_invalid_params_rejected():
    with pytest.raises(ValidationError):
        CrashBoxShellParams(box_height=6.0, wall=3.0)
    with pytest.raises(ValidationError):
        CrashBoxShellParams(box_length=40.0, box_height=50.0)


def test_surface_only_flag_enforced(tmp_path):
    """Hacim üreten şablon surface_only ise ve tersi açık hata."""
    from dataclasses import replace

    plate = get_template("crash_box_plate")
    with pytest.raises(TemplateError, match="yalnız yüzey"):
        build_template(replace(plate, surface_only=True), plate.parse_params({}), tmp_path / "a.step")
    shell = get_template("crash_box_shell")
    with pytest.raises(TemplateError, match="hacim üretmedi"):
        build_template(replace(shell, surface_only=False), shell.parse_params({}), tmp_path / "b.step")


def test_2d_quad_mesh_exports_single_shell_part(tmp_path):
    t = get_template("crash_box_shell")
    p = t.parse_params({})
    r = build_template(t, p, tmp_path / "cbs.step")
    _open(r.step_path)
    try:
        gmsh.option.setNumber("Mesh.RecombineAll", 1)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 10.0)
        gmsh.model.mesh.generate(2)
        msh = tmp_path / "cbs_d2.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    rm = gmsh_msh_to_radioss(msh)
    assert rm.shells and not rm.tets
    assert set(rm.element_parts.values()) == {0}  # kenar paylaşan 4 yüz → tek parça
    # uyumlu mesh: aynı koordinatta iki ayrı düğüm yok
    coords = [(round(n["x"], 6), round(n["y"], 6), round(n["z"], 6)) for n in rm.nodes]
    assert len(coords) == len(set(coords))
