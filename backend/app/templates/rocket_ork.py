"""OpenRocket ``.ork`` içe aktarma — R6.

``.ork`` = zip içinde ``rocket.ork`` XML'i (eski sürümlerde düz XML). Birimler
SI (m). Tüm kademeler fırlatma konfigürasyonunda (yukarıdan aşağı) tek roket
olarak birleştirilir; bileşenlerden R1 şablon parametreleri (mm) çıkarılır:

- ``nosecone`` → burun profili + boyu (ogive, conical → konik, ellipsoid →
  elips, haack (şekil parametresi 0) → von_karman; diğerleri eşlenmez, not düşülür)
- ``bodytube``'lar → toplam gövde boyu; çap = kanatçık tüpünün yarıçapı × 2
  (kanatçık yoksa en büyük tüp)
- en arkadaki yamuk kanatçıklı tüpün ``trapezoidfinset``'i → N, Cr, Ct, s
  (height), Xs (sweeplength), t; aynı geometride birden çok set (ör. tek
  kanatçıklı 3 set) → sayılar toplanır; firar kenarı → gövde sonu
  (``axialoffset`` / ``position`` bottom: negatif değer ileri)
- son tüpten sonraki daralan ``transition`` → boat-tail (Lt, Dt)

Örnek dosyalarla denendi (OpenRocket deposu ``datafiles/examples``: basit
model, 3B baskı, ARC yük roketi, çift paraşüt, iki kademeli, tüp kanatçık).

Eşlenemeyen her şey ``notes`` listesinde veri olarak döner; değerler
mühendisin formunda düzenlenir. Yeni bağımlılık yok (zipfile + xml.etree).
"""

from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

MAX_XML_BYTES = 20 * 1024 * 1024

_NOSE = {"ogive": "ogive", "conical": "konik", "ellipsoid": "elips"}


class OrkError(ValueError):
    pass


def read_ork_xml(data: bytes) -> ET.Element:
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".ork")] or z.namelist()
            if not names:
                raise OrkError("Zip boş.")
            info = z.getinfo(names[0])
            if info.file_size > MAX_XML_BYTES:
                raise OrkError("XML çok büyük.")
            data = z.read(info)
    if b"<!DOCTYPE" in data[:2048] or b"<!ENTITY" in data:
        raise OrkError("DOCTYPE / ENTITY içeren XML kabul edilmez.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise OrkError(f"XML okunamadı: {e}") from e
    if root.tag != "openrocket":
        raise OrkError("OpenRocket dosyası değil (kök <openrocket> yok).")
    return root


def _num(el: ET.Element | None, tag: str) -> float | None:
    if el is None:
        return None
    t = el.findtext(tag)
    if t is None:
        return None
    for tok in t.replace("auto", " ").split():
        try:
            return float(tok)
        except ValueError:
            continue
    return None


def _mm(v: float | None) -> float | None:
    return None if v is None else round(v * 1000.0, 3)


def ork_to_params(root: ET.Element) -> dict[str, Any]:
    """→ ``{"params": {...}, "notes": [...], "name": str}`` (params kısmi olabilir)."""
    notes: list[str] = []
    params: dict[str, Any] = {}
    rocket = root.find("rocket")
    if rocket is None:
        raise OrkError("<rocket> yok.")
    stages = rocket.findall("./subcomponents/stage")
    if not stages:
        raise OrkError("Aşama (stage) yok.")
    # Fırlatma konfigürasyonu: kademeler yukarıdan aşağı üst üste
    comps: list[ET.Element] = []
    for st in stages:
        sub = st.find("subcomponents")
        comps.extend(list(sub) if sub is not None else [])
    if len(stages) > 1:
        notes.append(f"{len(stages)} kademe fırlatma konfigürasyonunda tek roket olarak birleştirildi.")

    nose = next((c for c in comps if c.tag == "nosecone"), None)
    if nose is None:
        notes.append("Burun konisi yok; burun varsayılanı kalır.")
    else:
        shape = (nose.findtext("shape") or "").strip().lower()
        sp = _num(nose, "shapeparameter")
        if shape == "haack" and (sp or 0.0) == 0.0:
            params["nose_shape"] = "von_karman"
        elif shape in _NOSE:
            params["nose_shape"] = _NOSE[shape]
            if shape == "ogive" and sp is not None and sp < 1.0:
                notes.append(f"Ogive şekil parametresi {sp:g} (şablon teğet ogive = 1).")
        else:
            notes.append(f"Burun profili '{shape}' şablonda yok; profil seçilmedi.")
        params["nose_length"] = _mm(_num(nose, "length"))

    tubes = [c for c in comps if c.tag == "bodytube"]
    if not tubes:
        raise OrkError("Gövde tüpü (bodytube) yok.")
    lengths = [_num(t, "length") or 0.0 for t in tubes]
    params["body_length"] = _mm(sum(lengths))
    if len(tubes) > 1:
        notes.append(f"{len(tubes)} gövde tüpü tek tüp olarak birleştirildi (toplam boy).")
    mids = [c for c in comps[comps.index(tubes[0]) : comps.index(tubes[-1])] if c.tag == "transition"]
    if mids:
        notes.append(f"Gövde arasındaki {len(mids)} geçiş (transition) alınmadı; boyu gövdeye eklenmedi.")

    # Kanatçık: en arkadaki yamuk kanatçıklı tüp (şablonda tek set)
    fin_sets = [(i, f) for i, t in enumerate(tubes) for f in t.findall("./subcomponents/trapezoidfinset")]
    fin = None
    fin_tube_idx = len(tubes) - 1
    if fin_sets:
        fin_tube_idx = max(i for i, _ in fin_sets)
        aft = [f for i, f in fin_sets if i == fin_tube_idx]
        fin = aft[0]
        geo_keys = ("rootchord", "tipchord", "height", "sweeplength", "thickness", "axialoffset", "position")
        same = all(all(_num(f, k) == _num(fin, k) for k in geo_keys) for f in aft)
        n_fins = sum(int(_num(f, "fincount") or 1) for f in aft) if same else int(_num(fin, "fincount") or 4)
        if len(aft) > 1:
            notes.append(
                f"Arka tüpte {len(aft)} kanatçık seti " + ("aynı geometride; kanatçık sayıları toplandı." if same else "farklı geometride; yalnız ilki alındı.")
            )
        fwd = len(fin_sets) - len(aft)
        if fwd:
            notes.append(f"Öndeki {fwd} kanatçık seti alınmadı (şablonda tek kanatçık seti var).")

    # Çap: kanatçık tüpünün yarıçapı; yoksa en büyük tüp yarıçapı
    radii = [_num(t, "radius") for t in tubes]
    r0 = radii[fin_tube_idx] or max((r for r in radii if r), default=None)
    if r0 is None and nose is not None:
        r0 = _num(nose, "aftradius")
    if r0 is None:
        notes.append("Gövde yarıçapı 'auto' ve çözülemedi; çap girilmeli.")
    else:
        params["body_diameter"] = _mm(2 * r0)
        other = sorted({round(2000 * r, 2) for r in radii if r and abs(r - r0) > 1e-9})
        if other:
            notes.append(f"Gövde tüpleri farklı çaplarda ({', '.join(f'{d:g}' for d in other)} mm); kanatçık tüpünün çapı alındı.")

    if fin is None:
        kinds = {o.tag for t in tubes for o in t.findall("./subcomponents/*") if o.tag.endswith("finset")}
        notes.append("Yamuk kanatçık seti yok" + (f" (bulunan: {', '.join(sorted(kinds))})" if kinds else "") + "; kanatçık varsayılanları kalır.")
    else:
        params["fin_count"] = n_fins
        params["fin_root_chord"] = _mm(_num(fin, "rootchord"))
        params["fin_tip_chord"] = _mm(_num(fin, "tipchord"))
        params["fin_span"] = _mm(_num(fin, "height"))
        params["fin_sweep"] = _mm(_num(fin, "sweeplength"))
        params["fin_thickness"] = _mm(_num(fin, "thickness"))
        # OpenRocket 23.09: <axialoffset method="bottom">, eskiler: <position type="bottom">
        tag = "axialoffset" if fin.find("axialoffset") is not None else "position"
        pos = fin.find(tag)
        ptype = ((pos.get("method") or pos.get("type")) if pos is not None else None) or "bottom"
        pval = _num(fin, tag) or 0.0
        after = sum(lengths[fin_tube_idx + 1 :])
        if ptype == "bottom":
            params["fin_offset"] = _mm(max(0.0, -pval) + after)
            if pval > 0:
                notes.append("Kanatçık gövde sonundan taşıyor; firar kenarı gövde sonuna alındı.")
        else:
            notes.append(f"Kanatçık konumu '{ptype}' referanslı; Xf elle girilmeli.")

    last_tube_pos = comps.index(tubes[-1])
    tail = next((c for c in comps[last_tube_pos + 1 :] if c.tag == "transition"), None)
    if tail is not None:
        fr, ar = _num(tail, "foreradius"), _num(tail, "aftradius")
        if fr is None:
            fr = r0
        if ar is not None and fr is not None and ar < fr:
            params["boattail_length"] = _mm(_num(tail, "length"))
            params["boattail_aft_diameter"] = _mm(2 * ar)
        else:
            notes.append("Arka geçiş daralan değil; boat-tail alınmadı.")
    else:
        params["boattail_length"] = 0.0

    params = {k: v for k, v in params.items() if v is not None}
    return {"name": rocket.findtext("name") or "", "params": params, "notes": notes}
