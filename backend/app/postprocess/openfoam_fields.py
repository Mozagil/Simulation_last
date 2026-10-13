"""OpenFOAM ASCII alan dosyalarından yama (boundaryField) değerleri — Faz 2.6b.

Ör. ``wallShearStress`` ve ``C`` (hücre / yüz merkezleri) alanlarından bir duvar
yamasının yüz değerleri okunur; yeniden bağlanma noktası gibi yüzey verileri
buradan hesaplanır. Yalnız ASCII biçim (case yazıcımız ``writeFormat ascii``).
"""

from __future__ import annotations

import re

_VEC = re.compile(r"\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)")


def _patch_block(text: str, patch: str) -> str:
    bf = text.find("boundaryField")
    if bf < 0:
        raise ValueError("boundaryField bulunamadı.")
    m = re.search(rf"\n\s*{re.escape(patch)}\s*\n\s*\{{", text[bf:])
    if not m:
        raise ValueError(f"Yama yok: {patch}")
    start = bf + m.end()
    depth = 1
    i = start
    while depth and i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start : i - 1]


def patch_vectors(text: str, patch: str) -> list[tuple[float, float, float]]:
    """``value nonuniform List<vector> N ( (x y z) … )`` ya da ``uniform (x y z)``."""
    block = _patch_block(text, patch)
    m = re.search(r"value\s+nonuniform\s+List<vector>\s*(\d+)\s*\(", block)
    if m:
        n = int(m.group(1))
        vecs = [(float(a), float(b), float(c)) for a, b, c in _VEC.findall(block[m.end() :])][:n]
        if len(vecs) != n:
            raise ValueError(f"{patch}: {n} vektör bekleniyordu, {len(vecs)} okundu.")
        return vecs
    m = re.search(r"value\s+uniform\s+" + _VEC.pattern, block)
    if m:
        return [(float(m.group(1)), float(m.group(2)), float(m.group(3)))]
    raise ValueError(f"{patch}: değer listesi okunamadı.")


def reattachment_x(
    centres: list[tuple[float, float, float]],
    shear: list[tuple[float, float, float]],
    x_min: float,
    x_max: float,
) -> float | None:
    """Duvar kayma gerilmesinin x bileşeninin [x_min, x_max] aralığındaki SON
    işaret değişimi (doğrusal ara değerle) — geri basamakta yeniden bağlanma.
    Değişim yoksa None.

    OpenFOAM ``wallShearStress`` duvara etkiyen gerilmenin tersidir: ileri
    akışta (alt duvar, +x) τ_x < 0, ters akışta (geri dönüş bölgesi) τ_x > 0.
    Köşe girdabı basamağa yakın ek işaret değişimleri üretir; ana geri dönüş
    bölgesinin sonu aralıktaki son değişimdir (ölçüldü: pitzDaily, V-C3)."""
    pts = sorted((c[0], s[0]) for c, s in zip(centres, shear) if x_min <= c[0] <= x_max)
    last = None
    for (x0, t0), (x1, t1) in zip(pts, pts[1:]):
        if t0 == 0.0 or (t0 < 0) != (t1 < 0):
            last = x0 if t0 == t1 else x0 + (x1 - x0) * (-t0) / (t1 - t0)
    return last
