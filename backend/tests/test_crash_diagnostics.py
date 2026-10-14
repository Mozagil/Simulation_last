"""1.14 kapanış — engine kopma listesi + starter mesaj ID'leri iş sonucunda veri."""

from __future__ import annotations

import pytest

from app.postprocess.openradioss_th import (
    parse_openradioss_dir,
    parse_ruptures,
    parse_starter_messages,
)

# Gerçek OpenRadioss listing'inden kısaltılmış (iş 21f7c6a2…)
_ENGINE = """\
   CYCLE    TIME      TIME-STEP  ELEMENT          ERROR  I-ENERGY    K-ENERGY T  K-ENERGY R  EXT-WORK     MAS.ERR     TOTAL MASS  MASS ADDED
       0   0.000      0.5400E-03 SHELL       1625   0.0%   0.000       58.86       0.000       0.000       0.000       1.187       0.000    
 START DAMAGE (TENS) OF SHELL ELEMENT        607 ,GAUSS PT 1 ,LAYER  1 ,INTEGRATION PT  1
 EQUIVALENT STRAIN= 0.2008E-02
 -- RUPTURE (TENS_STRAIN) OF SHELL ELEMENT NUMBER       1030
 -- RUPTURE (TENS_STRAIN) OF SHELL ELEMENT NUMBER         41
      100  0.5400E-01  0.5396E-03 SHELL       1637  -0.2%   31.82       26.80      0.1086       0.000       0.000       1.187       0.000    
     ANIMATION FILE: crashA002 WRITTEN
 -- RUPTURE (JOHNSON-COOK) OF SHELL ELEMENT NUMBER       1030
    5100   2.754      0.5404E-03 SHELL       1625  -1.1%   48.29       7.617      0.4585      -1.854       0.000       1.187       0.000    
 -- RUPTURE (TENS_STRAIN) OF SHELL ELEMENT NUMBER        638
"""

_STARTER = """\
WARNING ID :   1912
** WARNING IN SHELL PROPERTY
ERROR ID :    574
ERROR ID :    574
|                                                           |       |---     1 WARNING ID :         1912               |
"""


def test_ruptures_time_is_next_printed_cycle(tmp_path):
    p = tmp_path / "crash_0001.out"
    p.write_text(_ENGINE, encoding="utf-8")
    rup = parse_ruptures(p)
    assert [(r["criterion"], r["kind"], r["element"]) for r in rup] == [
        ("TENS_STRAIN", "shell", 1030),
        ("TENS_STRAIN", "shell", 41),
        ("JOHNSON-COOK", "shell", 1030),
        ("TENS_STRAIN", "shell", 638),
    ]
    assert [r["time"] for r in rup] == [0.054, 0.054, 2.754, None]


def test_starter_messages_skip_summary_table(tmp_path):
    p = tmp_path / "crash_0000.out"
    p.write_text(_STARTER, encoding="utf-8")
    assert parse_starter_messages(p) == {"errors": {"574": 2}, "warnings": {"1912": 1}}


def test_dir_scalars_and_diagnostics(tmp_path):
    (tmp_path / "crash_0000.out").write_text(_STARTER, encoding="utf-8")
    (tmp_path / "crash_0001.out").write_text(_ENGINE, encoding="utf-8")
    rs = parse_openradioss_dir(tmp_path)
    # aynı eleman iki kez listelense de bir kez sayılır
    assert rs.scalars["elements_deleted"] == 3.0
    assert rs.scalars["deletion_time_first"] == pytest.approx(0.054)
    assert rs.scalars["deletion_time_last"] == pytest.approx(2.754)
    assert rs.scalars["starter_error_count"] == 2.0
    assert rs.scalars["starter_warning_count"] == 1.0
    assert rs.diagnostics["starter_warnings"] == {"1912": 1}
    assert len(rs.diagnostics["deleted_elements"]) == 4


def test_no_rupture_no_deletion_time(tmp_path):
    (tmp_path / "crash_0001.out").write_text(_ENGINE.split(" START DAMAGE")[0], encoding="utf-8")
    rs = parse_openradioss_dir(tmp_path)
    assert rs.scalars["elements_deleted"] == 0.0
    assert "deletion_time_first" not in rs.scalars
    assert "starter_error_count" not in rs.scalars  # starter listing yok


def test_rupture_without_criterion_is_material_limit(tmp_path):
    """1.23 A3 — LAW2 εp,max kopması parantezsiz yazılır; eskiden sayılmıyordu (0 silinen)."""
    p = tmp_path / "crash_0001.out"
    p.write_text(
        "   CYCLE    TIME      TIME-STEP  ELEMENT          ERROR\n"
        "   -- RUPTURE OF SHELL ELEMENT NUMBER       1270\n"
        "   -- RUPTURE OF SHELL ELEMENT NUMBER       1272\n"
        "     200  0.1080      0.5400E-03 SHELL       1945   0.0%\n",
        encoding="utf-8",
    )
    rup = parse_ruptures(p)
    assert [(r["criterion"], r["kind"], r["element"], r["time"]) for r in rup] == [
        ("MAT", "shell", 1270, 0.108),
        ("MAT", "shell", 1272, 0.108),
    ]
