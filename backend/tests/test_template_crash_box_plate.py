"""Crash box + plaka şablonu (1.11a): iki ayrı katı, dört isimli bölge.

Deck (1.11b) parça kimliğine güveneceği için burada kilitlenen şey: STEP'te
tam iki hacim var, hacimler mesh katmanının part sırasına göre 0 = kutu,
1 = plaka, her bölge tek yüzey ve doğru hacme ait, aralık > 0 (başlangıçta
temas yok).
"""

from __future__ import annotations

import gmsh
import pytest
from pydantic import ValidationError

from app.templates import build_template, get_template
from app.templates.crash_box_plate import (
    REGION_BOX_BACK,
    REGION_BOX_FRONT,
    REGION_PLATE_BACK,
    REGION_PLATE_FRONT,
    box_volume_mm3,
    plate_volume_mm3,
)


def _volumes_and_faces(step_path):
    """(hacim tag → kütle), (hacim tag → yüzey tag'leri) — mesh katmanının
    part sırası = gmsh.model.getEntities(3) sırası."""
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(step_path))
        vols = [t for _d, t in gmsh.model.getEntities(3)]
        mass = {t: gmsh.model.occ.getMass(3, t) for t in vols}
        faces = {
            t: {b for d, b in gmsh.model.getBoundary([(3, t)], oriented=False) if d == 2}
            for t in vols
        }
        bbox = {t: gmsh.model.getBoundingBox(3, t) for t in vols}
        return vols, mass, faces, bbox
    finally:
        gmsh.finalize()


def test_registered_with_symbols_and_crash_tag():
    t = get_template("crash_box_plate")
    props = t.params_schema()["properties"]
    for name, prop in props.items():
        if prop.get("type") in ("number", "integer"):
            assert prop.get("symbol"), f"{name} sembolsüz"
    assert "crash" in t.tags
    assert t.analytic is None
    assert set(t.region_names()) == {
        REGION_PLATE_BACK, REGION_PLATE_FRONT, REGION_BOX_FRONT, REGION_BOX_BACK,
    }


def test_two_separate_solids_with_expected_volumes(tmp_path):
    t = get_template("crash_box_plate")
    p = t.parse_params({})
    r = build_template(t, p, tmp_path / "cbp.step")
    vols, mass, faces, bbox = _volumes_and_faces(r.step_path)
    assert len(vols) == 2, "kutu ve plaka ayrı katı olmalı (fuse yok)"
    # part 0 = kutu (x ≥ 0), part 1 = plaka (x < 0): mesh katmanının sırası
    box_tag, plate_tag = vols
    assert bbox[box_tag][0] == pytest.approx(0.0, abs=1e-6)
    assert bbox[plate_tag][3] == pytest.approx(p.plate_front_x, abs=1e-6)
    assert mass[box_tag] == pytest.approx(box_volume_mm3(p), rel=1e-6)
    assert mass[plate_tag] == pytest.approx(plate_volume_mm3(p), rel=1e-6)
    # başlangıçta temas yok: kutu önü ile plaka önü arasında gap
    assert bbox[box_tag][0] - bbox[plate_tag][3] == pytest.approx(p.gap, abs=1e-6)
    # bölgeler tek yüzey ve doğru katıda
    for name in (REGION_PLATE_BACK, REGION_PLATE_FRONT):
        assert len(r.regions[name]) == 1 and r.regions[name][0] in faces[plate_tag], name
    for name in (REGION_BOX_FRONT, REGION_BOX_BACK):
        assert len(r.regions[name]) == 1 and r.regions[name][0] in faces[box_tag], name


def test_box_front_face_is_hollow_ring(tmp_path):
    """Kutu ön ucu açık: x=0 yüzeyinin alanı dış − iç kesit."""
    t = get_template("crash_box_plate")
    p = t.parse_params({"wall": 3.0})
    r = build_template(t, p, tmp_path / "cbp.step")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(r.step_path))
        area = gmsh.model.occ.getMass(2, r.regions[REGION_BOX_FRONT][0])
    finally:
        gmsh.finalize()
    expected = p.box_height * p.box_width - (p.box_height - 6.0) * (p.box_width - 6.0)
    assert area == pytest.approx(expected, rel=1e-6)


def test_constraints():
    t = get_template("crash_box_plate")
    with pytest.raises(ValidationError, match="2 × wall"):
        t.parse_params({"wall": 30.0})
    with pytest.raises(ValidationError, match="box_length"):
        t.parse_params({"box_length": 20.0, "box_height": 50.0})
    with pytest.raises(ValidationError):
        t.parse_params({"gap": 0.0})
