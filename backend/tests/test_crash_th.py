"""1.15b — /TH seçimi: gruplar, değişkenler, düğümler; th_spec.json ile adlı eğriler.

Kart düzeni hm_cfg OUTPUTBLOCK r110 (th_node: satır başına bir düğüm
`%10d%10d%-80s`; değişkenler `%-10s`, satır 100 karakter). Radioss sütunları
kendi sırasıyla yazar; TH grup kimlikleri tekil olmalı (starter hata 79).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.solvers.openradioss_headers import strip_headers
from app.postprocess.openradioss_th import named_th_curves, parse_openradioss_dir
from app.solvers.base import SolverError
from app.solvers.crash_params import CrashThParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_contact import _card
from tests.test_crash_multipart import _two_part_params


def _starter(tmp_path, th=None, **extra):
    p = _two_part_params(tmp_path)
    if th is not None:
        p["th"] = th
    p.update(extra)
    art = OpenRadiossAdapter().build_input(p)
    spec = json.loads((art.path.parent / "th_spec.json").read_text(encoding="utf-8"))
    return strip_headers(art.path.read_text(encoding="utf-8")), spec


def test_default_groups_and_unique_ids(tmp_path):
    s, spec = _starter(tmp_path)
    assert _card(s, "/TH/RWALL/1") == ["barrier_th", f"{'FNX':<10}{'FNY':<10}{'FNZ':<10}", f"{1:10d}"]
    assert _card(s, "/TH/PART/3")[1].split() == ["IE", "KE"]
    assert "/TH/NODE/" not in s
    assert [g["kind"] for g in spec["groups"]] == ["rwall", "part"]
    assert spec["groups"][1]["mesh_ids"] == [0, 1]


def test_custom_vars_sorted_and_node_lines(tmp_path):
    vars12 = ["Z", "DX", "DY", "DZ", "VX", "VY", "VZ", "AX", "AY", "AZ", "X", "Y"]
    s, spec = _starter(
        tmp_path,
        {"rwall": {"vars": ["FTZ", "FNX"]}, "part": {"enabled": False}, "node_ids": [3, 1], "node_vars": vars12},
    )
    assert _card(s, "/TH/RWALL/1")[1].split() == ["FNX", "FTZ"]  # hm_cfg sırası
    assert "/TH/PART/" not in s
    node = _card(s, "/TH/NODE/4")
    assert node[0] == "th_nodes"
    assert node[1].split() == ["DX", "DY", "DZ", "VX", "VY", "VZ", "AX", "AY", "AZ", "X"]  # 10 / satır
    assert node[2].split() == ["Y", "Z"]
    assert node[3:] == [f"{3:10d}{0:10d}n3", f"{1:10d}{0:10d}n1"]  # satır başına bir düğüm
    assert spec["groups"][-1] == {"kind": "node", "title": "th_nodes", "objects": [3, 1],
                                  "vars": ["DX", "DY", "DZ", "VX", "VY", "VZ", "AX", "AY", "AZ", "X", "Y", "Z"]}


def test_legacy_th_nodes_become_acc_group(tmp_path):
    s, _ = _starter(tmp_path, th_nodes=[2])
    assert _card(s, "/TH/NODE/4")[1].split() == ["AX", "AY", "AZ"]


def test_missing_node_is_solver_error(tmp_path):
    with pytest.raises(SolverError, match="düğüm mesh'te yok"):
        _starter(tmp_path, {"node_ids": [999]})


@pytest.mark.parametrize(
    "raw",
    [
        {"rwall": {"vars": ["FN"]}},  # bu ikili bileşkeyi yazmıyor
        {"part": {"vars": ["DEF"]}},  # kısa yol yok
        {"part": {"vars": ["IE", "ie"]}},  # tekrar
        {"inter": {"enabled": True, "vars": []}},
        {"node_ids": [1, 1]},
        {"node_ids": [1], "node_vars": []},
    ],
)
def test_invalid_th_rejected(raw):
    with pytest.raises(ValidationError):
        CrashThParams.model_validate(raw)


# th_to_csv başlık biçimi gerçek koşudan (iş ddc643c5…)
_SPEC = {"groups": [
    {"kind": "rwall", "title": "barrier_th", "objects": [1], "vars": ["FNX", "FNY", "FNZ"]},
    {"kind": "part", "title": "part_energy", "objects": [1], "names": ["part_0_moving"],
     "mesh_ids": [0], "vars": ["IE", "MASS"]},
    {"kind": "node", "title": "th_nodes", "objects": [7, 9], "vars": ["DX", "AX"]},
]}


def _cols():
    h = {"time": [0.0, 1.0, 2.0],
         "part_0_moving                             IE ": [0.0, 5.0, 6.0],
         "part_0_moving                             MASS ": [1.2, 1.2, 1.2]}
    for n in (25, 26, 27):
        h[f"barrier_th                               1 barrier                                  var {n}"] = [0.0, float(n), float(n)]
    for k, n in enumerate((28, 29, 30, 31)):
        node = 7 if k < 2 else 9
        h[f"th_nodes                                 {node} n{node}                                       var {n}"] = [float(n)] * 3
    return h


def test_named_curves_follow_spec_order():
    named, unmapped = named_th_curves(_cols(), _SPEC)
    assert unmapped == []
    assert named["th_rwall_FNY"] == [0.0, 26.0, 26.0]
    assert named["th_part_0_MASS"] == [1.2, 1.2, 1.2]
    assert named["th_node_7_AX"] == [29.0] * 3 and named["th_node_9_DX"] == [30.0] * 3


def test_column_count_mismatch_is_unmapped_not_mislabelled():
    spec = {"groups": [{**_SPEC["groups"][0], "vars": ["FNX", "FNY", "FNZ", "FTX"]}]}
    named, unmapped = named_th_curves(_cols(), spec)
    assert unmapped == ["barrier_th"] and not any(k.startswith("th_rwall") for k in named)


def test_dir_uses_spec_for_wall_force(tmp_path):
    cols = _cols()
    lines = [",".join(f'"{h}"' for h in cols)]
    for i in range(3):
        lines.append(",".join(str(v[i]) for v in cols.values()))
    (tmp_path / "crashT01.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "th_spec.json").write_text(json.dumps(_SPEC), encoding="utf-8")
    rs = parse_openradioss_dir(tmp_path)
    assert rs.curves["th_node_9_AX"] == [31.0] * 3
    assert rs.scalars["rwall_impulse_final"] == pytest.approx((25**2 + 26**2 + 27**2) ** 0.5)
    assert "th_unmapped_groups" not in rs.diagnostics
