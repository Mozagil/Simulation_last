"""Her sayısal şablon parametresi, şemadaki harfiyle (symbol) etiketlenmeli.

Arayüz formunda "Genişlik W (mm)" yazabilmek için; kullanıcı hangi alanın
şemadaki hangi ölçüye karşılık geldiğini tahmin etmek zorunda kalmasın.
"""

from __future__ import annotations

import pytest

from app.templates import list_templates


@pytest.mark.parametrize("template", list_templates(), ids=lambda t: t.id)
def test_numeric_params_have_symbol(template):
    props = template.params_schema()["properties"]
    for name, prop in props.items():
        if prop.get("type") in ("number", "integer"):
            assert prop.get("symbol"), f"{template.id}.{name}: symbol yok"


@pytest.mark.parametrize("template", list_templates(), ids=lambda t: t.id)
def test_symbols_unique_within_template(template):
    props = template.params_schema()["properties"]
    symbols = [p["symbol"] for p in props.values() if p.get("symbol")]
    assert len(symbols) == len(set(symbols)), f"{template.id}: harfler tekrar ediyor: {symbols}"


def test_known_symbols_match_schematic():
    """Şemalarda gösterilen harflerle birebir (regresyon)."""
    by_id = {t.id: t.params_schema()["properties"] for t in list_templates()}
    assert {k: v["symbol"] for k, v in by_id["cantilever_beam"].items()} == {
        "length": "L", "thickness": "T", "width": "W",
    }
    assert {k: v["symbol"] for k, v in by_id["i_beam"].items()} == {
        "length": "L", "height": "h", "flange_width": "b", "web": "tw", "flange": "tf",
    }
    assert by_id["thick_walled_tube"]["inner_radius"]["symbol"] == "a"
    assert by_id["thick_walled_tube"]["outer_radius"]["symbol"] == "b"
