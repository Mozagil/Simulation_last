"""Faz 3.8 — CalculiX COMPOSITE kesit kartları (ccx çalışmaz)."""

import pytest

from app.composite.section_writer import write_composite_inp, write_composite_section
from app.solvers.calculix import _section_block


def _t300_ply(angle: float, t: float = 0.125) -> dict:
    return {
        "name": "T300/epoxy",
        "e1": 135e9,
        "e2": 10e9,
        "e3": 10e9,
        "nu12": 0.30,
        "nu13": 0.30,
        "nu23": 0.45,
        "g12": 5.2e9,
        "g13": 5.2e9,
        "g23": 3.4e9,
        "density": 1600.0,
        "thickness_mm": t,
        "angle_deg": angle,
    }


def test_write_composite_0_90_0_cards():
    text = write_composite_section(
        {
            "part_id": 0,
            "dir0": [1.0, 0.0, 0.0],
            "plies": [_t300_ply(0.0), _t300_ply(90.0), _t300_ply(0.0)],
        }
    )
    assert text.count("*MATERIAL, NAME=T300_epoxy") == 1
    assert "*ELASTIC, TYPE=ENGINEERING CONSTANTS" in text
    assert "135000" in text  # 135e9 Pa → 135000 MPa
    assert "1.350000e+11" not in text
    assert "1.600000e-09" in text  # 1600 * 1e-12
    # Açı başına bir rozet: ortak eksenler + yerel 3 etrafında ek dönme.
    assert text.count("*ORIENTATION, NAME=") == 2
    assert "*ORIENTATION, NAME=OR_0_0, SYSTEM=RECTANGULAR\n1, 0, 0, 0, 1, 0\n3, 0\n" in text
    assert "*ORIENTATION, NAME=OR_0_1, SYSTEM=RECTANGULAR\n1, 0, 0, 0, 1, 0\n3, 90\n" in text
    assert "*SHELL SECTION, ELSET=PART_0, COMPOSITE\n" in text
    # ccx 4. alan = orientation ADI (sayı yazılırsa "nonexistent orientation").
    assert "0.125, 3, T300_epoxy, OR_0_0" in text
    assert "0.125, 3, T300_epoxy, OR_0_1" in text
    assert text.count("T300_epoxy, OR_0_0") == 2
    assert "T300_epoxy, 0\n" not in text
    assert "*SHELL SECTION, ELSET=PART_0, MATERIAL=" not in text


def test_write_composite_rejects_empty_and_bad_thickness():
    with pytest.raises(ValueError, match="En az bir"):
        write_composite_section({"plies": []})
    with pytest.raises(ValueError, match="pozitif"):
        write_composite_section({"plies": [_t300_ply(0.0, 0.0)]})


def test_section_block_uses_composite_only_when_param_set():
    iso = [
        {
            "part_id": 0,
            "name": "S355",
            "youngs_modulus": 210e9,
            "poisson_ratio": 0.3,
            "density": 7850.0,
        }
    ]
    iso_text = _section_block({}, iso, dimension=2, shell_thickness=2.0)
    assert "*SHELL SECTION, ELSET=PART_0, MATERIAL=S355" in iso_text
    assert "COMPOSITE" not in iso_text
    assert "ENGINEERING CONSTANTS" not in iso_text

    comp_text = _section_block(
        {"composite_layup": {"part_id": 0, "plies": [_t300_ply(0.0), _t300_ply(90.0)]}},
        iso,
        dimension=2,
        shell_thickness=2.0,
    )
    assert "COMPOSITE" in comp_text
    assert "ENGINEERING CONSTANTS" in comp_text
    assert "MATERIAL=S355" not in comp_text


def test_write_composite_inp_list_two_parts():
    glass = dict(_t300_ply(45.0), name="E-glass/epoxy", e1=41e9)
    text = write_composite_inp(
        [
            {"part_id": 0, "plies": [_t300_ply(0.0)]},
            {"part_id": 1, "plies": [glass]},
        ]
    )
    assert "ELSET=PART_0" in text
    assert "ELSET=PART_1" in text
    assert "glass_epoxy" in text
    assert "41000" in text  # 41e9 Pa → 41000 MPa
