"""Radioss deck sütun başlıkları — her kart veri satırının üstüne `#` yorum satırı.

Deck yazıcı (`openradioss._write_starter` / `_write_engine`) kartları yazdıktan sonra
`annotate()` her bilinen kartın veri satırlarının üstüne alan adlarını, alanın
genişliğine sağa yaslı yazar (Radioss girdi kılavuzundaki "#" başlık düzeni). Radioss
`#` satırlarını yorum sayar; çözüm değişmez. Alan adları yazıcıdaki hm_cfg düzeni
yorumlarından; düzeni doğrulanmamış kartlara (SPH, yay, /PLOAD) başlık yazılmaz.
Kullanıcının ham kartlarına (`RAW_CARDS_MARKER` sonrası) ve zaten `#` satırıyla
başlayan bloklara (ör. /DAMP) dokunulmaz.
"""

from __future__ import annotations

from collections.abc import Callable

#: Alan: (ad, genişlik). Ad boşsa alan boş sütundur (başlıkta da boş).
Field = tuple[str, int]
I, F = 10, 20  # _i / _f genişlikleri


def _row(*fields: Field) -> str:
    s = "".join(f"{name:>{w}}" if name else " " * w for name, w in fields)
    return "#" + s[1:] if s else "#"


def _r(spec: str) -> str:
    """Kısa yazım: "E:F nu:F Iflag:I _:I" → başlık satırı (`_` = boş alan)."""
    out: list[Field] = []
    for tok in spec.split():
        name, w = tok.rsplit(":", 1)
        width = {"I": I, "F": F}.get(w) or int(w)
        if len(name) >= width:  # ad, önceki alanın adına bitişmesin
            raise ValueError(f"başlık adı alana sığmıyor: {name} ({width})")
        out.append(("" if name == "_" else name, width))
    return _row(*out)


#: Kart anahtarı (sondaki sayısal kimlikler atılmış) → (başlık satırı var mı, veri satırı başlıkları).
#: Başlık listesi kısa ise kalan satırlar başlıksız (liste kartlarında başlık bir kez).
SPECS: dict[str, tuple[bool, list[str | None]]] = {
    "/BEGIN": (True, [_r("Invers:I Irun:I"),
                      _r("Input_mass_unit:F Input_length_unit:F Input_time_unit:F"),
                      _r("Work_mass_unit:F Work_length_unit:F Work_time_unit:F")]),
    "/NODE": (False, [_r("node_ID:I Xc:F Yc:F Zc:F")]),
    "/SHELL": (False, [_r("shell_ID:I node_ID1:I node_ID2:I node_ID3:I node_ID4:I")]),
    "/SH3N": (False, [_r("sh3n_ID:I node_ID1:I node_ID2:I node_ID3:I")]),
    "/TETRA4": (False, [_r("tetra_ID:I node_ID1:I node_ID2:I node_ID3:I node_ID4:I")]),
    "/BRICK": (False, [_r("brick_ID:I node_ID1:I node_ID2:I node_ID3:I node_ID4:I node_ID5:I node_ID6:I "
                          "node_ID7:I node_ID8:I")]),
    "/MAT/LAW1": (True, [_r("RHO_I:F"), _r("E:F nu:F")]),
    "/MAT/LAW2": (True, [_r("RHO_I:F"), _r("E:F nu:F Iflag:I"),
                         _r("a:F b:F n:F EPS_p_max:F SIG_max0:F"),
                         _r("c:F EPS_DOT_0:F ICC:I Fsmooth:I F_cut:F Chard:F"),
                         _r("m:F T_melt:F rhoC_p:F T_r:F")]),
    # LAW36 eğri kimliği / ölçek / hız satırları N_funct'a göre — _law36
    "/FUNCT": (True, [_r("X:F Y:F")]),
    "/FAIL/JOHNSON": (False, [_r("D1:F D2:F D3:F D4:F D5:F"),
                              _r("EPS_DOT_0:F Ifail_sh:I Ifail_so:I _:F Dadv:F _:I Ixfem:I")]),
    "/FAIL/TENSSTRAIN": (False, [_r("Epsilon_t1:F Epsilon_t2:F fct_ID:I Epsilon_f1:F Epsilon_f2:F S_Flag:I")]),
    "/PROP/TYPE1": (True, [_r("Ishell:I Ismstr:I Ish3n:I Idrill:I Ipinch:I _:I P_Thick_Fail:F"),
                           _r("hm:F hf:F hr:F dm:F dn:F"),
                           _r("N:I Istrain:I Thick:F Ashear:F _:I Ithick:I Iplas:I")]),
    "/PROP/TYPE14": (True, [_r("Isolid:I Ismstr:I Iale:I Icpre:I Itetra10:I Inpts:I Itetra4:I Iframe:I dn:F"),
                            _r("q_a:F q_b:F h:F LAMBDA_v:F MU_v:F"),
                            _r("dt_min:F Istrain:I IHKT:I")]),
    "/PART": (True, [_r("prop_ID:I mat_ID:I subset_ID:I")]),
    "/GRNOD/PART": (True, [_r("part_ID1:I part_ID2:I part_ID3:I")]),
    "/GRNOD/NODE": (True, [_r("node_ID1:I node_ID2:I node_ID3:I")]),
    "/GRSHEL/PART": (True, [_r("part_ID1:I part_ID2:I part_ID3:I")]),
    "/GRSH3N/PART": (True, [_r("part_ID1:I part_ID2:I part_ID3:I")]),
    "/GRBRIC/PART": (True, [_r("part_ID1:I part_ID2:I part_ID3:I")]),
    "/SURF/PART": (True, [_r("part_ID1:I part_ID2:I part_ID3:I")]),
    "/SURF/PART/EXT": (True, [_r("part_ID1:I part_ID2:I part_ID3:I")]),
    "/SURF/SEG": (True, [_r("seg_ID:I node_ID1:I node_ID2:I node_ID3:I node_ID4:I")]),
    "/BCS": (True, [_r("Trarot:I skew_ID:I grnod_ID:I")]),
    "/INTER/TYPE7": (True, [_r("grnd_IDs:I surf_IDm:I Istf:I Ithe:I Igap:I _:I Ibag:I Idel:I Icurv:I Iadm:I"),
                            _r("Fscale_gap:F GAP_MAX:F Fpenmax:F _:F Itied:I"),
                            _r("Stmin:F Stmax:F %mesh_size:F dtmin:F Irem_gap:I Irem_i2:I"),
                            _r("Stfac:F Fric:F Gapmin:F Tstart:F Tstop:F"),
                            _r("IBC:I _:F Inacti:I VIS_S:F VIS_F:F Bumult:F"),
                            _r("Ifric:I Ifiltr:I Xfreq:F Iform:I sens_ID:I fct_IDF:I AscaleF:F fric_ID:I")]),
    "/INTER/TYPE24": (True, [_r("surf_ID1:I surf_ID2:I Istf:I _:F Irem_i2:I _:I Idel:I"),
                             _r("grnd_IDs:I _:F Iedge:I Edge_angle:F Gap_max_s:F Gap_max_m:F"),
                             _r("Stmin:F Stmax:F Igap0:I Ipen0:I Ipen_max:F"),
                             _r("Stfac:F Fric:F _:F Tstart:F Tstop:F"),
                             _r("IBC:I _:F Inacti:I VISs:F _:F Tpressfit:F"),
                             _r("Ifric:I Ifiltr:I Xfreq:F _:I sens_ID:I _:30 fric_ID:I")]),
    "/INIVEL/TRA": (True, [_r("Vx:F Vy:F Vz:F grnd_ID:I skew_ID:I")]),
    "/ADMAS": (True, [_r("MASS:F grnd_ID:I")]),
    "/RBODY": (True, [_r("node_ID:I sens_ID:I skew_ID:I Ispher:I Mass:F grnd_ID:I Ikrem:I ICoG:I surf_ID:I"),
                      _r("Jxx:F Jyy:F Jzz:F"), _r("Jxy:F Jyz:F Jxz:F")]),
    "/IMPVEL": (True, [_r("fct_IDT:I Dir:I skew_ID:I sens_ID:I grnd_ID:I _:I Icoor:I"),
                       _r("Ascale_x:F Fscale_Y:F Tstart:F Tstop:F")]),
    "/GRAV": (True, [_r("fct_IDT:I Dir:I skew_ID:I sens_ID:I grnd_ID:I _:I Ascale_x:F Fscale_Y:F")]),
    "/LOAD/PBLAST": (True, [_r("surf_ID:I Exp_data:I I_tshift:I Ndt:I IZ:I Imodel:I _:30 Node_id:I"),
                            _r("Xdet:F Ydet:F Zdet:F Tdet:F WTNT:F"), _r("Pmin:F Tstop:F"), _r("Ground_ID:I")]),
    "/RWALL/PLANE": (True, [_r("node_ID:I Slide:I grnd_ID1:I grnd_ID2:I"), _r("d:F"),
                            _r("XM:F YM:F ZM:F"), _r("XM1:F YM1:F ZM1:F")]),
    "/RWALL/CYL": (True, [_r("node_ID:I Slide:I grnd_ID1:I grnd_ID2:I"), _r("d:F _:F Diameter:F"),
                          _r("XM:F YM:F ZM:F"), _r("XM1:F YM1:F ZM1:F")]),
    "/SECT/PARAL": (True, [_r("node_ID1:I node_ID2:I node_ID3:I _:I ISAVE:I _:I Dt:F alpha:F"), None,
                           _r("grbric_ID:I _:I grshel_ID:I grtrus_ID:I grbeam_ID:I grsprg_ID:I grtria_ID:I "
                              "Niter:I _:I Iframe:I"),
                           _r("XM:F YM:F ZM:F"), _r("XM1:F YM1:F ZM1:F"), _r("XM2:F YM2:F ZM2:F")]),
    # Engine
    "/RUN": (False, [_r("Tstop:F")]),
    "/TFILE": (False, [_r("DT_HIS:F")]),
    "/ANIM/DT": (False, [_r("Tstart:F Tfreq:F")]),
    "/DT": (False, [_r("DT_SCA:F DT_MIN:F")]),
}


def _law36(data: list[str]) -> list[str | None]:
    rows: list[str | None] = [_r("RHO_I:F"), _r("E:F nu:F Eps_p_max:F Eps_t:F Eps_m:F"),
                              _r("N_funct:I F_smooth:I C_hard:F F_cut:F Eps_f:F _:I VP:I"),
                              _r("fct_IDp:I Fscale:F Fct_IDE:I EInf:F CE:F")]
    try:
        n = int(data[2][:10])
    except (IndexError, ValueError):
        return rows
    k = -(-n // 5)  # 5 eğri / satır
    for hdr in ("fct_ID{}:I", "Fscale{}:F", "Eps_dot{}:F"):
        rows.append(_r(" ".join(hdr.format(j) for j in range(1, min(n, 5) + 1))))
        rows += [None] * (k - 1)
    return rows


def _th(data: list[str], node: bool) -> list[str | None]:
    """/TH/…: değişken satırları (harfle başlar) + nesne kimlikleri; ikisine de başlık bir kez.
    /TH/NODE kimlik satırı: node_ID skew_ID ad."""
    obj = _r("node_ID:I skew_ID:I") + "name" if node else _r("Obj_ID1:I Obj_ID2:I Obj_ID3:I")
    rows: list[str | None] = []
    var_done = obj_done = False
    for ln in data:
        if ln[:1].isalpha() and not var_done:
            rows.append(_r("var_ID1:I var_ID2:I var_ID3:I"))
            var_done = True
        elif ln.strip()[:1].isdigit() and not obj_done:
            rows.append(obj)
            obj_done = True
        else:
            rows.append(None)
    return rows


SPECIAL: dict[str, Callable[[list[str]], list[str | None]]] = {"/MAT/LAW36": _law36}


def _key(head: str) -> str | None:
    """`/MAT/LAW2/3` → `/MAT/LAW2`; en uzun eşleşen SPECS anahtarı (ya da /TH)."""
    parts = [p for p in head.strip().split("/") if p]
    while parts and parts[-1].isdigit():
        parts.pop()
    for n in range(len(parts), 0, -1):
        k = "/" + "/".join(parts[:n])
        if k in SPECS or k in SPECIAL:
            return k
    return "/TH" if parts and parts[0] == "TH" else None


def annotate(lines: list[str], stop_marker: str | None = None) -> list[str]:
    """Kart veri satırlarının üstüne `#` sütun başlıkları ekler (yeni liste döner)."""
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        if stop_marker is not None and ln == stop_marker:
            return out + lines[i:]
        if not ln.startswith("/") or ln.startswith("/END"):
            out.append(ln)
            i += 1
            continue
        j = i + 1
        while j < n and not lines[j].startswith("/") and lines[j] != stop_marker:
            j += 1
        block = lines[i + 1 : j]
        key = _key(ln)
        out.append(ln)
        if key is None or any(b.startswith("#") for b in block):
            out += block
            i = j
            continue
        if key == "/TH":
            has_title, data = True, block[1:]
            rows = _th(data, ln.startswith("/TH/NODE"))
        else:
            has_title = SPECS[key][0] if key in SPECS else True
            data = block[1:] if has_title else block
            rows = SPECIAL[key](data) if key in SPECIAL else SPECS[key][1]
        if has_title and block:
            out.append(block[0])
        for k_, d in enumerate(data):
            hdr = rows[k_] if k_ < len(rows) else None
            if hdr and d.strip():
                out.append(hdr.rstrip())
            out.append(d)
        i = j
    return out


def _all_headers() -> set[str]:
    out = {r.rstrip() for _t, rows in SPECS.values() for r in rows if r}
    for n in range(1, 6):
        out |= {r.rstrip() for r in _law36(["", "", f"{n:10d}"]) if r}
    out |= {r.rstrip() for r in _th(["X", "1"], False) + _th(["X", "1"], True) if r}
    return out


ALL_HEADERS = _all_headers()


def strip_headers(text: str) -> str:
    """`annotate`'in eklediği başlık satırlarını atar (deck verisini satır satır karşılaştırmak için).
    Elle yazılmış `#` satırlarına (/DAMP başlığı, ham kartlar) dokunmaz."""
    return "\n".join(ln for ln in text.split("\n") if ln not in ALL_HEADERS)
