"""1.23 D1 — üretilen deck'i koşmadan görüntüle (starter + engine + kart listesi)."""

from __future__ import annotations

from app.api.crash import CRASH_DIR, deck_outline
from tests.test_crash_solve import _barrier, _upload_and_mesh_box, client, requires_db


def test_outline_blocks():
    text = "#RADIOSS STARTER\n/BEGIN\nrun\n/NODE\n1 0 0 0\n2 1 0 0\n/END"
    assert deck_outline(text) == [
        {"card": "/BEGIN", "line": 2, "lines": 2},
        {"card": "/NODE", "line": 4, "lines": 3},
        {"card": "/END", "line": 7, "lines": 1},
    ]
    assert deck_outline("") == []


@requires_db
def test_preview_endpoint_returns_decks_with_raw_cards():
    gid = _upload_and_mesh_box()
    r = client.post(
        "/crash/deck/preview",
        json={"geometry_id": gid, "barrier": _barrier(), "raw_cards": "/FUNCT/900001\nkullanıcı\n0 0\n1 1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["starter"].startswith("#") or "/BEGIN" in body["starter"]
    cards = [c["card"] for c in body["starter_outline"]]
    assert "/BEGIN" in cards and any(c.startswith("/NODE") for c in cards)
    assert "/FUNCT/900001" in cards  # ham kart koşudaki gibi deck'te
    assert any(c.startswith("/RUN") for c in (o["card"] for o in body["engine_outline"]))
    assert not any((CRASH_DIR / "_preview").glob("*"))  # geçici klasör kalmaz
