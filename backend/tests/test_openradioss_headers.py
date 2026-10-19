"""Radioss deck `#` sütun başlıkları — openradioss_headers.annotate."""

from __future__ import annotations

import pytest

from app.solvers.openradioss import RAW_CARDS_MARKER, _f, _i
from app.solvers.openradioss_headers import SPECS, _r, annotate, strip_headers


def test_baslik_alan_sutunlariyla_hizali():
    lines = ["/MAT/LAW2/1", "S235", _f(7.85e-6), f"{_f(210.0)}{_f(0.3)}{_i(0)}"]
    out = annotate(lines)
    assert out[:3] == ["/MAT/LAW2/1", "S235", "#              RHO_I"]
    hdr, data = out[4], out[5]
    assert hdr == "#                  E                  nu     Iflag"
    # her ad kendi alanının sağ kenarında biter
    assert hdr.index("nu") + 2 == 40 and len(hdr) == len(data) == 50


def test_her_baslik_100_karakteri_gecmez_ve_ad_alana_sigar():
    for key, (_title, rows) in SPECS.items():
        for r in rows:
            if r:
                assert r.startswith("#") and len(r) <= 100, key
    with pytest.raises(ValueError):
        _r("uzun_bir_ad:I")


def test_liste_kartinda_baslik_bir_kez_ham_kart_ve_mevcut_baslik_korunur():
    lines = ["/GRNOD/PART/1", "moving_parts", _i(1) * 10, _i(2),
             "/DAMP/1", "rayleigh", "#  elle", _f(0.0),
             RAW_CARDS_MARKER, "/BCS/99", "elle", "   111 111         0         1",
             "/END", ""]
    out = annotate(lines, RAW_CARDS_MARKER)
    assert out[:5] == ["/GRNOD/PART/1", "moving_parts", "# part_ID1  part_ID2  part_ID3", _i(1) * 10, _i(2)]
    assert out[5:9] == ["/DAMP/1", "rayleigh", "#  elle", _f(0.0)]  # zaten başlıklı blok
    assert out[9:] == lines[8:]  # ham kartlara dokunulmaz
    assert strip_headers("\n".join(out)) == "\n".join(lines)


def test_law36_egri_satirlari_n_funct_a_gore():
    lines = ["/MAT/LAW36/1", "S", _f(1.0), _f(1.0) * 5, f"{_i(7)}{_i(0)}", "x", "fct", "fct2", "sc", "sc2", "ed", "ed2"]
    out = annotate(lines)
    heads = [ln for ln in out if ln.startswith("#")]
    assert heads[4].split() == ["#", "fct_ID1", "fct_ID2", "fct_ID3", "fct_ID4", "fct_ID5"]
    assert out[out.index("fct") - 1] == heads[4] and out[out.index("fct2") - 1] == "fct"
    assert out[out.index("sc") - 1].split()[1] == "Fscale1"


def test_th_degisken_ve_nesne_basliklari():
    out = annotate(["/TH/NODE/4", "th_nodes", "AX        AY        AZ        ", f"{_i(5)}{_i(0)}n5", f"{_i(6)}{_i(0)}n6"])
    assert out[2].split()[1:] == ["var_ID1", "var_ID2", "var_ID3"]
    assert out[4].startswith("#  node_ID   skew_ID")
    assert sum(ln.startswith("#") for ln in out) == 2


def test_deck_yaziciya_bagli(tmp_path):
    from app.solvers.openradioss import OpenRadiossAdapter

    p = {"output_dir": tmp_path, "job_name": "h",
         "nodes": [{"id": i + 1, "x": float(x), "y": float(y), "z": float(z)}
                   for i, (x, y, z) in enumerate([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)])],
         "tets": [[1, 1, 2, 3, 4]], "t_end_ms": 1.0}
    art = OpenRadiossAdapter().build_input(p)
    s = art.path.read_text(encoding="utf-8")
    assert "/NODE\n#  node_ID                  Xc" in s
    assert "/PART/1\npart_0_moving\n#  prop_ID    mat_ID" in s
    eng = art.path.with_name("h_0001.rad").read_text(encoding="utf-8")
    assert "/TFILE\n#             DT_HIS\n" in eng
