"""Faz 1.5 — OpenRadioss post-process (enerji, RWALL, HIC)."""

import pytest

from app.postprocess.hic import hic15, hic36
from app.postprocess.openradioss_th import (
    impulse_to_force,
    parse_energy_listing,
    parse_openradioss_dir,
    parse_th_csv,
)
from app.solvers.base import JobHandle
from app.solvers.openradioss import OpenRadiossAdapter


def test_hic15_constant_100g_15ms():
    n = 16
    t = [0.015 * i / (n - 1) for i in range(n)]
    a = [100.0] * n
    assert hic15(t, a) == pytest.approx(100.0**2.5 * 0.015, rel=1e-9)
    assert hic36(t, a) == pytest.approx(100.0**2.5 * 0.015, rel=1e-9)


def test_hic_empty_is_zero():
    assert hic15([], []) == 0.0
    assert hic15([0.0], [1.0]) == 0.0


def test_impulse_to_force_constant_slope():
    t = [0.0, 1.0, 2.0, 3.0]
    imp = [0.0, 10.0, 20.0, 30.0]
    f = impulse_to_force(t, imp)
    assert f[1:] == pytest.approx([10.0, 10.0, 10.0])


def test_parse_listing_energy(tmp_path):
    out = tmp_path / "crash_0001.out"
    out.write_text(
        """
 ** ENGINE **
   CYCLE        TIME     TIMESTP      IENERGY      KENERGY     HOURGLASS
       0  0.0000E+00  1.0000E-03  0.0000E+00  1.2500E+02  0.0000E+00
      10  5.0000E+00  1.0000E-03  2.0000E+01  1.0000E+02  1.0000E+00
      20  1.0000E+01  1.0000E-03  4.0000E+01  8.0000E+01  2.0000E+00
""",
        encoding="utf-8",
    )
    parsed = parse_energy_listing(out)
    assert parsed["IE"][-1] == pytest.approx(40.0)
    assert parsed["KE"][0] == pytest.approx(125.0)
    rs = parse_openradioss_dir(tmp_path)
    assert rs.scalars["internal_energy_final"] == pytest.approx(40.0)
    assert rs.scalars["kinetic_energy_max"] == pytest.approx(125.0)
    assert rs.curves["internal_energy"][-1] == pytest.approx(40.0)


def test_parse_csv_rwall_and_hic(tmp_path):
    # 10 ms, 100 g in Z (0.980665 mm/ms²)
    az = 0.980665
    lines = ["Time,FNX,FNY,FNZ,ACCX,ACCY,ACCZ"]
    for i in range(11):
        t = float(i)
        lines.append(f"{t},0,0,12.0,0,0,{az}")
    csv_path = tmp_path / "impT01.csv"
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cols = parse_th_csv(csv_path)
    assert "FNZ" in cols
    rs = parse_openradioss_dir(tmp_path)
    assert rs.scalars["rwall_force_max"] == pytest.approx(12.0)
    assert rs.scalars["acc_peak_g"] == pytest.approx(100.0, rel=1e-3)
    # tam sinyal 10 ms < 15 ms → HIC15 = 100^2.5 * 0.01
    assert rs.scalars["hic15"] == pytest.approx(100.0**2.5 * 0.01, rel=1e-3)
    assert rs.scalars["hic36"] == pytest.approx(rs.scalars["hic15"], rel=1e-9)


def test_parse_results_empty_without_th_files(tmp_path):
    params = {
        "output_dir": tmp_path,
        "job_name": "imp",
        "nodes": [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 10.0},
            {"id": 2, "x": 1.0, "y": 0.0, "z": 10.0},
            {"id": 3, "x": 0.0, "y": 1.0, "z": 10.0},
            {"id": 4, "x": 0.0, "y": 0.0, "z": 11.0},
        ],
        "tets": [(1, 1, 2, 3, 4)],
    }
    adapter = OpenRadiossAdapter()
    art = adapter.build_input(params)
    rs = adapter.parse_results(JobHandle(job_id="j", work_dir=tmp_path, artifact=art))
    assert rs.scalars == {}
    assert "/TH/RWALL/1" in art.path.read_text(encoding="utf-8")
    assert "/TH/TITLE" in (tmp_path / "imp_0001.rad").read_text(encoding="utf-8")
