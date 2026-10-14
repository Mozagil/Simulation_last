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
    th = _card(s, "/TH/INTER/2")  # 1.15b: TH grup kimlikleri tekil
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
    # FN* impuls: temas 1 (0,0,0) → (3,4,0) → (3,4,0) (plato); duvar 0 → 1 → 1
    rows = [
        [0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 10.0],
        [1.0, 1, 0, 0, 3, 4, 0, 9, 9, 9, 5.0, 5.0],
        [2.0, 1, 0, 0, 3, 4, 0, 9, 9, 9, 6.0, 4.0],
    ]
    csv = tmp_path / "crashT01.csv"
    csv.write_text(
        ",".join(hdr) + "\n" + "\n".join(",".join(str(v) for v in r) for r in rows) + "\n",
        encoding="utf-8",
    )
    rs = parse_openradioss_dir(tmp_path)
    # kuvvet = d(impuls)/dt bileşen bileşen; FT hariç; platoda 0
    assert rs.curves["contact_1_force"] == pytest.approx([5.0, 5.0, 0.0])
    assert rs.curves["contact_1_impulse"] == pytest.approx([0.0, 5.0, 5.0])
    assert rs.scalars["contact_1_force_max"] == pytest.approx(5.0)
    assert rs.scalars["contact_1_impulse_final"] == pytest.approx(5.0)
    assert rs.curves["rwall_force"] == pytest.approx([1.0, 1.0, 0.0])


# --- 1.24a — genel temas (all_parts) ---------------------------------------


def test_all_parts_solid_single_self_contact(tmp_path):
    # iki solid parça → tek /SURF/PART/EXT (iki parça) + tek öz TYPE24
    s = _deck(tmp_path, [{"type": 24, "all_parts": True, "fric": 0.1, "iedge": 1}])
    assert _card(s, "/SURF/PART/EXT/7902") == ["all_solid_parts", f"{1:10d}{2:10d}"]
    assert "/SURF/PART/7901" not in s
    c = _card(s, "/INTER/TYPE24/1")
    assert c[0] == "contact_1_all_parts_solid"
    assert c[1][:20] == f"{7902:10d}{0:10d}"  # öz temas: surf_ID2 = 0
    assert int(c[2][30:40]) == 1  # Iedge
    assert float(c[4][20:40]) == 0.1  # Fric
    assert "/INTER/TYPE24/2" not in s
    assert "/SURF/PART/EXT/100" not in s  # parça başı yüzey yazılmaz


def test_all_parts_shell_and_solid_three_interfaces(tmp_path):
    from tests.test_crash_shell import _shell_params

    p = _shell_params(tmp_path, contacts=[{"type": 24, "all_parts": True}])
    s = OpenRadiossAdapter().build_input(p).path.read_text(encoding="utf-8")
    assert _card(s, "/SURF/PART/7901") == ["all_shell_parts", f"{1:10d}"]
    assert _card(s, "/SURF/PART/EXT/7902") == ["all_solid_parts", f"{2:10d}"]
    c1, c2, c3 = (_card(s, f"/INTER/TYPE24/{k}") for k in (1, 2, 3))
    assert c1[0].endswith("_shell") and c1[1][:20] == f"{7901:10d}{0:10d}"
    assert c2[0].endswith("_solid") and c2[1][:20] == f"{7902:10d}{0:10d}"
    assert c3[0].endswith("_shell_solid") and c3[1][:20] == f"{7901:10d}{7902:10d}"
    assert _card(s, "/TH/INTER/2")[2] == f"{1:10d}{2:10d}{3:10d}"


def test_all_parts_with_pair_contact_ids_continue(tmp_path):
    s = _deck(
        tmp_path,
        [{"type": 7, "master_part": 1, "slave_part": 0}, {"type": 24, "all_parts": True}],
    )
    assert _card(s, "/INTER/TYPE7/1")[0] == "contact_1_p0_on_p1"
    assert _card(s, "/INTER/TYPE24/2")[0] == "contact_2_all_parts_solid"
    assert _card(s, "/TH/INTER/2")[2] == f"{1:10d}{2:10d}"


@pytest.mark.parametrize(
    "raw",
    [
        {"type": 7, "all_parts": True},  # yalnız TYPE24
        {"type": 24, "all_parts": True, "master_part": 0, "slave_part": 0},  # çift verilmez
        {"type": 24, "master_part": 0},  # all_parts yoksa ikisi de gerekli
        {"type": 7},
    ],
)
def test_all_parts_validation(raw):
    with pytest.raises(ValidationError):
        CrashContactParams.model_validate(raw)
