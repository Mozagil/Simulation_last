"""1.22b — OpenRadioss starter deck'inde ID envanteri + ham kart çakışmaları.

Yalnız veri üretir (öneri yok): üretilen deck hangi ID'leri kullanıyor, ham
kartlar bunlarla (ya da kendi içinde) nerede çakışıyor.

Ad alanı kuralı (başlık ``/ANAHTAR/.../ID``; ID = son tamsayı alan):
- ilk alan ad alanıdır: MAT, PROP, PART, FUNCT, INTER, BCS, RWALL, TH, ...
- /GR*, /SURF, /LINE tek ``GRUP`` ad alanı (temkinli: adaptör de grup
  tabanlarını türler arasında ayrık tutuyor);
- /NODE satırları ``NODE``, eleman blokları (/TETRA4, /BRICK, /SHELL, /SH3N,
  /SPHCEL) satırları ``ELEM``; bu blokların başlık ID'si parça referansıdır;
- /FAIL/*/ID malzemeye referanstır, tanım sayılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: 1.22 — kullanıcı ham kartlarına ayrılan ID aralığının alt sınırı (kullanıcı onayı).
USER_ID_MIN = 900_000

_ELEMENT_BLOCKS = {"TETRA4", "BRICK", "SHELL", "SH3N", "SPHCEL"}
_GROUP_PREFIXES = ("GR", "SURF", "LINE")
#: Tanım ID'si taşımayan ya da referans başlıklar.
_NO_DEF = {"BEGIN", "END", "NODE", "FAIL", "TFILE", "ANIM", "RUN", "DT", "STOP", "PRINT", "VERS", "TITLE"}


@dataclass(frozen=True)
class CardId:
    namespace: str
    id: int
    keyword: str  # başlık satırı (ör. /MAT/LAW2/3) ya da /NODE, /TETRA4/1
    line: int  # 1 tabanlı satır no (verilen metin içinde)


def _namespace(head: str) -> str:
    return "GRUP" if head.startswith(_GROUP_PREFIXES) else head


def _is_comment(line: str) -> bool:
    return line.startswith("#") or line.startswith("$")


def card_ids(text: str) -> list[CardId]:
    """Metindeki tanım ID'leri: kart başlıkları + /NODE ve eleman satırları."""
    out: list[CardId] = []
    block: str | None = None  # "NODE" | "ELEM" | None
    block_kw = ""
    for no, raw in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        line = raw.rstrip()
        if not line.strip() or _is_comment(line):
            continue
        if line.startswith("/"):
            kw = line.strip()
            parts = [p for p in kw.split("/") if p]
            head = parts[0].upper() if parts else ""
            block, block_kw = None, kw
            if head == "NODE":
                block = "NODE"
            elif head in _ELEMENT_BLOCKS:
                block = "ELEM"
            elif head not in _NO_DEF and len(parts) >= 2 and parts[-1].strip().isdigit():
                out.append(CardId(_namespace(head), int(parts[-1]), kw, no))
            continue
        if block is not None:
            first = line[:10].strip()
            if first.lstrip("-").isdigit():
                out.append(CardId(block, int(first), block_kw, no))
    return out


def deck_inventory(text: str) -> dict[str, Any]:
    """Üretilen deck'in kullandığı ID'ler: ad alanı başına liste; NODE/ELEM aralık."""
    by_ns: dict[str, set[int]] = {}
    for c in card_ids(text):
        by_ns.setdefault(c.namespace, set()).add(c.id)
    ranges = {}
    for ns in ("NODE", "ELEM"):
        ids = by_ns.pop(ns, set())
        ranges[ns] = {"count": len(ids), "min": min(ids) if ids else None, "max": max(ids) if ids else None}
    return {
        "user_id_min": USER_ID_MIN,
        "nodes": ranges["NODE"],
        "elements": ranges["ELEM"],
        "ids": {ns: sorted(ids) for ns, ids in sorted(by_ns.items())},
    }


def raw_card_report(generated: str, raw: str) -> dict[str, Any]:
    """Ham kart ID'lerinin üretilen deck ve kendi içleriyle çakışmaları.

    - ``collisions``: üretilen deck'te aynı ad alanı + ID var;
    - ``duplicates``: ham kartta aynı ad alanı + ID ikinci kez;
    - ``below_user_range``: < USER_ID_MIN olan ham kart ID'leri (NODE/ELEM hariç;
      onlar mesh ID'si olabilir — çakışma listesi ayrıca gösterir).
    """
    gen: dict[str, set[int]] = {}
    for c in card_ids(generated):
        gen.setdefault(c.namespace, set()).add(c.id)
    seen: dict[tuple[str, int], int] = {}
    collisions, duplicates, below = [], [], []
    for c in card_ids(raw):
        row = {"line": c.line, "keyword": c.keyword, "namespace": c.namespace, "id": c.id}
        if c.id in gen.get(c.namespace, ()):
            collisions.append(row)
        key = (c.namespace, c.id)
        if key in seen:
            duplicates.append({**row, "first_line": seen[key]})
        else:
            seen[key] = c.line
        if c.namespace not in ("NODE", "ELEM") and c.id < USER_ID_MIN:
            below.append(row)
    return {"collisions": collisions, "duplicates": duplicates, "below_user_range": below}
