"""1.15a — engine çıktı aralıkları + zaman adımı kartı; listing'den Δt ve kütle.

Kart düzenleri hm_cfg: eng_tfile r51, eng_anim_dt r51, eng_dt r110,
eng_dt_noda r2017 (Δt_sca Δt_min, %20). Süreler ms.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.solvers.openradioss_headers import strip_headers
from app.postprocess.openradioss_th import parse_cycle_table, parse_openradioss_dir
from app.solvers.base import SolverError
from app.solvers.crash_params import CrashEngineParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params


def _engine(tmp_path, engine=None, t_end=4.0) -> str:
    p = _two_part_params(tmp_path)
    p["t_end_ms"] = t_end
    if engine is not None:
        p["engine"] = engine
    art = OpenRadiossAdapter().build_input(p)
    return strip_headers(art.path.with_name(art.path.name.replace("_0000", "_0001")).read_text(encoding="utf-8"))


def test_defaults_unchanged(tmp_path):
    e = _engine(tmp_path)
    assert float(_card(e, "/TFILE")[0]) == pytest.approx(0.02)  # t_end / 200
    assert float(_card(e, "/ANIM/DT")[0][20:40]) == pytest.approx(0.2)  # t_end / 20
    assert "/DT" not in e.replace("/ANIM/DT", "")


def test_output_intervals(tmp_path):
    e = _engine(tmp_path, {"th_dt_ms": 0.002, "anim_dt_ms": 1.0})
    assert _card(e, "/TFILE") == [f"{0.002:20.8g}"]
    assert _card(e, "/ANIM/DT") == [f"{0.0:20.8g}{1.0:20.8g}"]


@pytest.mark.parametrize(
    "kind,header",
    [("DT", "/DT"), ("NODA/0", "/DT/NODA/0"), ("NODA/STOP", "/DT/NODA/STOP"), ("NODA/CST/0", "/DT/NODA/CST/0")],
)
def test_timestep_cards(tmp_path, kind, header):
    e = _engine(tmp_path, {"dt_kind": kind, "dt_scale": 0.67, "dt_min_ms": 0.001})
    assert _card(e, "\n" + header) == [f"{0.67:20.8g}{0.001:20.8g}"]  # /ANIM/DT ile karışmasın
    assert e.index(header) < e.index("/END")


@pytest.mark.parametrize(
    "raw",
    [
        {"dt_kind": "NODA/CST/1"},  # düğüm grubu ister, desteklenmiyor
        {"dt_scale": 0.5},  # tür seçilmeden
        {"dt_kind": "NODA/CST/0", "dt_scale": 0.9},  # Δt_min yok
        {"dt_kind": "NODA/STOP"},
        {"dt_kind": "DT", "dt_scale": 1.5},
        {"th_dt_ms": 0},
    ],
)
def test_invalid_engine_rejected(raw):
    with pytest.raises(ValidationError):
        CrashEngineParams.model_validate(raw)


def test_adapter_rejects_bad_engine(tmp_path):
    with pytest.raises(SolverError, match="engine"):
        _engine(tmp_path, {"dt_kind": "X"})


# Gerçek listing'den (iş 35ad798a…, /DT/NODA/CST/0 Δt_min 0.001 ms)
_LISTING = """\
   CYCLE    TIME      TIME-STEP  ELEMENT          ERROR  I-ENERGY    K-ENERGY T  K-ENERGY R  EXT-WORK     MAS.ERR     TOTAL MASS  MASS ADDED
       0   0.000      0.1000E-02 NODE         693   0.0%   0.000       91.88       0.000       0.000      0.5613       1.853      0.6662    
     ANIMATION FILE: crashA001 WRITTEN
     200  0.2000      0.1000E-02 NODE         507   0.2%   90.64       1.375      0.5597E-01   0.000      0.5651       1.858      0.6708    
   1   .6834E+00 .4387E-01 .1108E+00 .8419E+01 .2850E+00 .6040E-01 .9735E+01
"""


def test_cycle_table_and_mass_scalars(tmp_path):
    out = tmp_path / "crash_0001.out"
    out.write_text(_LISTING, encoding="utf-8")
    cyc = parse_cycle_table(out)
    assert cyc["time"] == [0.0, 0.2] and cyc["dt"] == [0.001, 0.001]
    assert cyc["mass_added"] == [0.6662, 0.6708]
    s = parse_openradioss_dir(tmp_path).scalars
    assert s["timestep_min"] == pytest.approx(0.001)
    assert s["mass_model"] == pytest.approx(1.853 - 0.6662)  # TOTAL MASS eklenen kütleyi içerir
    assert s["mass_added_rel"] == pytest.approx(0.6708 / (1.853 - 0.6662))


def test_nan_energy_rows_mark_divergence(tmp_path):
    """Radioss NaN'e gidip yine NORMAL TERMINATION yazabiliyor; ilk NaN zamanı veri olarak."""
    listing = _LISTING + (
        "    3700  0.1425E-01  0.1398-157 SHELL       1820   0.0%         NaN         NaN"
        "         NaN         NaN   0.000       1.187       0.000    \n"
    )
    out = tmp_path / "crash_0001.out"
    out.write_text(listing, encoding="utf-8")
    assert parse_cycle_table(out)["nan_time"] == [0.01425]
    res = parse_openradioss_dir(tmp_path)
    assert res.scalars["diverged_at_ms"] == pytest.approx(0.01425)
