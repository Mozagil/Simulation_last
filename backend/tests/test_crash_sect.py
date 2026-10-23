"""1.15c — /SECT/PARAL kesitleri + /TH/SECTIO; kesit kuvveti = d(FN + FT)/dt.

Kart düzeni hm_cfg radioss110 sect_paral; eleman grupları /GRSHEL|GRSH3N|
GRBRIC/PART. Gerçek koşuda (iş ffeda999…) x = sabit kesitte x kuvveti FTX'te
çıktı, FN* sıfır — toplam bileşen FN + FT.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.solvers.openradioss_headers import strip_headers
from app.postprocess.openradioss_th import parse_openradioss_dir
from app.solvers.base import SolverError
from app.solvers.crash_params import CrashSectionParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params

_SEC = {"name": "x0", "origin": [0.5, -1, -1], "corner1": [0.5, 2, -1], "corner2": [0.5, -1, 2]}


def _starter(tmp_path, sections, th=None):
    p = _two_part_params(tmp_path)
    p["sections"] = sections
    if th is not None:
        p["th"] = th
    art = OpenRadiossAdapter().build_input(p)
    spec = json.loads((art.path.parent / "th_spec.json").read_text(encoding="utf-8"))
    return strip_headers(art.path.read_text(encoding="utf-8")), spec


def test_sect_paral_card_layout(tmp_path):
    s, spec = _starter(tmp_path, [{**_SEC, "parts": [0], "iframe": 11}])
    c = _card(s, "/SECT/PARAL/1")
    assert c[0] == "x0"
    assert c[1] == f"{0:10d}{0:10d}{0:10d}{'':10}{0:10d}{'':10}{0.0:20.8g}{0.0:20.8g}"
    assert c[2] == ""  # dosya adı yok
    gid = int(c[3][:10])  # tetra → GRBRIC
    assert gid > 0 and c[3][10:20] == " " * 10 and int(c[3][20:30]) == 0
    assert int(c[3][90:100]) == 11
    assert [float(c[4][i : i + 20]) for i in (0, 20, 40)] == [0.5, -1.0, -1.0]
    assert _card(s, f"/GRBRIC/PART/{gid}")[1] == f"{1:10d}"  # yalnız parça 0 (rid 1)
    th = _card(s, "/TH/SECTIO/5")
    assert th[1].split() == ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"]  # varsayılan FN + FT
    assert th[2] == f"{1:10d}"
    assert spec["groups"][-1]["kind"] == "sect" and spec["groups"][-1]["names"] == ["x0"]


def test_all_parts_when_empty_and_two_sections(tmp_path):
    s, _ = _starter(tmp_path, [_SEC, {**_SEC, "name": "x2"}])
    g1 = int(_card(s, "/SECT/PARAL/1")[3][:10])
    g2 = int(_card(s, "/SECT/PARAL/2")[3][:10])
    assert g1 != g2
    assert _card(s, f"/GRBRIC/PART/{g1}")[1] == f"{1:10d}{2:10d}"
    assert _card(s, "/TH/SECTIO/5")[2] == f"{1:10d}{2:10d}"


def test_no_sections_no_cards(tmp_path):
    s, spec = _starter(tmp_path, [])
    assert "/SECT/" not in s and "/TH/SECTIO" not in s
    assert all(g["kind"] != "sect" for g in spec["groups"])


def test_unknown_part_is_solver_error(tmp_path):
    with pytest.raises(SolverError, match="parça mesh'te yok"):
        _starter(tmp_path, [{**_SEC, "parts": [7]}])


@pytest.mark.parametrize(
    "raw",
    [
        {**_SEC, "corner2": [0.5, 5, -1]},  # M, M1, M2 doğrusal
        {**_SEC, "iframe": 0},  # yerel eksen düğüm ister, desteklenmiyor
        {"name": "x", "origin": [0, 0, 0], "corner1": [1, 0, 0]},  # M2 yok
    ],
)
def test_invalid_section_rejected(raw):
    with pytest.raises(ValidationError):
        CrashSectionParams.model_validate(raw)


def test_section_force_from_fn_plus_ft(tmp_path):
    # x kuvveti FTX'te (gerçek koşudaki gibi); impuls 0 → 2 → 6 N·s
    spec = {"groups": [{"kind": "sect", "title": "sect_th", "objects": [1], "names": ["x20"],
                        "vars": ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"]}]}
    vals = {"FNX": [0, 0, 0], "FNY": [0, 0, 0], "FNZ": [0, 0, 0], "FTX": [0, -2, -6], "FTY": [0, 0, 0], "FTZ": [0, 0, 0]}
    header = ['"time"'] + [f'"sect_th 1 x20 var {28 + i}"' for i in range(6)]
    rows = [",".join([str(t)] + [str(vals[v][i]) for v in spec["groups"][0]["vars"]]) for i, t in enumerate((0.0, 1.0, 2.0))]
    (tmp_path / "crashT01.csv").write_text("\n".join([",".join(header), *rows]) + "\n", encoding="utf-8")
    (tmp_path / "th_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    rs = parse_openradioss_dir(tmp_path)
    assert rs.scalars["section_1_impulse_final"] == pytest.approx(6.0)
    assert rs.scalars["section_1_force_max"] == pytest.approx(4.0)
    assert rs.curves["th_sect_1_FTX"] == [0.0, -2.0, -6.0]
