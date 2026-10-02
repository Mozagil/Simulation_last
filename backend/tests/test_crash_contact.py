"""1.12a — temas: /SURF/PART/EXT + /INTER/TYPE7 | TYPE24 + /TH/INTER.

Kart düzenleri OpenRadioss hm_cfg tanımlarından (radioss2020 TYPE7,
radioss2021 TYPE24); burada sütun genişlikleri ve kimlik eşlemesi sınanır.
Duvar `use_rigid_wall=False` ile kapatılabilir; varsayılan açık.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.postprocess.openradioss_th import parse_openradioss_dir
from app.solvers.base import SolverError
from app.solvers.crash_params import CrashContactParams
from app.solvers.openradioss import OpenRadiossAdapter
from tests.test_crash_multipart import _two_part_params


def _card(s: str, header: str) -> list[str]:
    """Başlıktan sonraki satırlar, bir sonraki /KART'a kadar."""
    after = s.split(header + "\n", 1)[1].splitlines()
    out: list[str] = []
    for ln in after:
        if ln.startswith("/"):
            break
        out.append(ln)
    return out


def _deck(tmp_path, contacts, **extra) -> str:
    p = _two_part_params(tmp_path)
    p["contacts"] = contacts
    p.update(extra)
    return OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")


def test_type7_cards_and_ids(tmp_path):
    # kutu (parça 0, Radioss 1) slave düğümleri → plaka (parça 1, Radioss 2) yüzeyi
    s = _deck(tmp_path, [{"type": 7, "master_part": 1, "slave_part": 0, "fric": 0.2, "gapmin": 0.5}])
    assert _card(s, "/SURF/PART/EXT/1002") == ["skin_part_1", f"{2:10d}"]
    assert _card(s, "/GRNOD/PART/1001") == ["nodes_part_0", f"{1:10d}"]
    assert "/SURF/PART/EXT/1001" not in s  # TYPE7 slave yüzey değil düğüm
    c = _card(s, "/INTER/TYPE7/1")
    assert c[0] == "contact_1_p0_on_p1"
    assert len(c) == 7  # başlık + 6 veri satırı (Ifric=0, Iadm=0, Ithe=0)
    assert c[1][:20] == f"{1001:10d}{1002:10d}"
    assert len(c[1]) == 100
    stfac, fric, gapmin = (float(c[4][i : i + 20]) for i in (0, 20, 40))
    assert (stfac, fric, gapmin) == (1.0, 0.2, 0.5)
    assert c[5].startswith("       000") and int(c[5][30:40]) == 0  # IBC · Inacti


def test_type24_cards_and_self_contact(tmp_path):
    s = _deck(
        tmp_path,
        [
            {"type": 24, "master_part": 1, "slave_part": 0, "iedge": 1, "inacti": -1},
            {"type": 24, "master_part": 0, "slave_part": 0},
        ],
    )
    # her iki parça için dış deri bir kez
    assert s.count("/SURF/PART/EXT/1001\n") == 1 and s.count("/SURF/PART/EXT/1002\n") == 1
    assert "/GRNOD/PART/100" not in s
    c1 = _card(s, "/INTER/TYPE24/1")
    assert c1[1][:20] == f"{1001:10d}{1002:10d}"
    assert int(c1[2][30:40]) == 1  # Iedge
    assert int(c1[5][30:40]) == -1  # Inacti
    c2 = _card(s, "/INTER/TYPE24/2")
    assert c2[1][:20] == f"{1001:10d}{0:10d}"  # self-contact: surf_ID2 = 0
    th = _card(s, "/TH/INTER/1")
    assert th[0] == "contact_th"
    assert th[1].split() == ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"]
    assert th[2] == f"{1:10d}{2:10d}"


def test_rigid_wall_off_and_default_on(tmp_path):
    contacts = [{"type": 7, "master_part": 1, "slave_part": 0}]
    off = _deck(tmp_path / "a", contacts, use_rigid_wall=False)
    assert "/RWALL/" not in off and "/TH/RWALL/" not in off
    assert "/INIVEL/TRA/1" in off  # ilk hız bariyerden gelmeye devam eder
    on = _deck(tmp_path / "b", [])
    assert "/RWALL/PLANE/1" in on and "/INTER/" not in on and "/TH/INTER/" not in on


def test_contact_on_missing_part_is_error(tmp_path):
    with pytest.raises(SolverError, match="#5"):
        _deck(tmp_path, [{"type": 7, "master_part": 5, "slave_part": 0}])


@pytest.mark.parametrize(
    "raw",
    [
        {"type": 12, "master_part": 1, "slave_part": 0},
        {"type": 7, "master_part": 1, "slave_part": 0, "istf": 6},  # 6 yalnız TYPE24
        {"type": 24, "master_part": 1, "slave_part": 0, "inacti": 3},  # 3 yalnız TYPE7
        {"type": 7, "master_part": 1, "slave_part": 0, "fric": -0.1},
    ],
)
def test_invalid_contact_flags_rejected(raw):
    with pytest.raises(ValidationError):
        CrashContactParams.model_validate(raw)


def test_postprocess_contact_force_separate_from_wall(tmp_path):
    # th_to_csv düzeni: adsız "var N" sütunları, grup başlığıyla.
    hdr = ["TIME"]
    hdr += [f"barrier_th 1 barrier var {i}" for i in (1, 2, 3)]
    hdr += [f"contact_th 1 contact_1 var {i}" for i in range(1, 7)]
    hdr += ["part_energy 1 part_0 IE", "part_energy 1 part_0 KE"]
    rows = [
        [0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 10.0],
        [1.0, 1, 0, 0, 3, 4, 0, 9, 9, 9, 5.0, 5.0],
    ]
    csv = tmp_path / "crashT01.csv"
    csv.write_text(
        ",".join(hdr) + "\n" + "\n".join(",".join(str(v) for v in r) for r in rows) + "\n",
        encoding="utf-8",
    )
    rs = parse_openradioss_dir(tmp_path)
    assert rs.curves["contact_1_force"] == [0.0, 5.0]  # |FN| = √(3²+4²), FT hariç
    assert rs.scalars["contact_1_force_max"] == 5.0
    assert rs.curves["rwall_force"] == [0.0, 1.0]
