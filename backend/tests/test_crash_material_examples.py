"""1.23 A3 — belgelerdeki malzeme örnekleri (LAW1, LAW2 εp,max, /FAIL/TENSSTRAIN, /FAIL/JOHNSON).

Örnek verisi tek kaynak: `frontend/src/docs/crashMaterialExamples.json` (belge oradan çizilir).
Her örneğin `model`'i deck'e çevrilir; belgede yazan kart ve alan değerleri deck'te olmalı.
Ölçülen sonuçlar (koşu #333, #334; 1.14d) belge metninde, burada kart düzeni denetlenir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_crash_contact import _card
from tests.test_crash_fail import _deck

_EXAMPLES = json.loads(
    (Path(__file__).resolve().parents[2] / "frontend" / "src" / "docs" / "crashMaterialExamples.json").read_text(
        encoding="utf-8"
    )
)


def test_four_examples_in_doc():
    assert [e["id"] for e in _EXAMPLES] == ["law1", "law2_epsmax", "tensstrain", "johnson"]


@pytest.mark.parametrize("ex", _EXAMPLES, ids=[e["id"] for e in _EXAMPLES])
def test_example_model_produces_documented_cards(tmp_path, ex):
    s = _deck(tmp_path, ex["model"])
    for chk in ex["deck"]:
        assert chk["card"] in s, chk["card"]
        if "line" in chk:
            line = _card(s, chk["card"])[chk["line"]]
            f = chk["field"]
            assert float(line[20 * f : 20 * f + 20]) == pytest.approx(chk["value"]), (chk, line)
