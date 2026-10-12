"""1.22b — ID envanteri + ham kart çakışmaları (yalnız veri)."""

from __future__ import annotations

from app.api.crash import CRASH_DIR
from app.solvers.openradioss import OpenRadiossAdapter
from app.solvers.openradioss_ids import USER_ID_MIN, card_ids, deck_inventory, raw_card_report
from tests.test_crash_multipart import _two_part_params
from tests.test_crash_solve import _barrier, _upload_and_mesh_box, client, requires_db


def _generated(tmp_path) -> str:
    return OpenRadiossAdapter().build_input(_two_part_params(tmp_path)).path.read_text(encoding="utf-8")


def test_inventory_of_two_part_deck(tmp_path):
    inv = deck_inventory(_generated(tmp_path))
    assert inv["user_id_min"] == USER_ID_MIN == 900_000
    assert inv["nodes"] == {"count": 8, "min": 1, "max": 8}
    assert inv["elements"] == {"count": 2, "min": 1, "max": 2}
    ids = inv["ids"]
    assert ids["MAT"] == [1, 2] and ids["PROP"] == [1, 2] and ids["PART"] == [1, 2]
    assert ids["GRUP"] == [1, 2]  # /GRNOD/PART/1..2
    assert ids["BCS"] == [1] and ids["RWALL"] == [1]
    assert "TETRA4" not in ids and "FAIL" not in ids  # parça / malzeme referansı


def test_namespace_rules():
    text = "\n".join(
        [
            "# yorum /MAT/LAW1/5",
            "/MAT/LAW2/7",
            "çelik",
            "/FAIL/JOHNSON/7",
            "/GRNOD/NODE/900001",
            "g",
            "/SURF/SEG/900002",
            "/NODE",
            f"{900003:10d}{0.0:20.8g}{0.0:20.8g}{0.0:20.8g}",
            "/SHELL/3",
            f"{900004:10d}{1:10d}{2:10d}{3:10d}{4:10d}",
        ]
    )
    got = {(c.namespace, c.id) for c in card_ids(text)}
    assert got == {("MAT", 7), ("GRUP", 900001), ("GRUP", 900002), ("NODE", 900003), ("ELEM", 900004)}


def test_collisions_duplicates_and_range(tmp_path):
    raw = "\n".join(
        [
            "/MAT/LAW1/2",  # satır 1: üretilen MAT 2 ile çakışır, aralık altı
            "m",
            "/GRNOD/NODE/900001",  # satır 3
            "g",
            "/GRSHEL/PART/900001",  # satır 5: aynı GRUP ad alanında ikinci kez
            "/NODE",
            f"{5:10d}{0.0:20.8g}{0.0:20.8g}{0.0:20.8g}",  # satır 7: mesh düğümü 5 ile çakışır
        ]
    )
    rep = raw_card_report(_generated(tmp_path), raw)
    assert [(r["namespace"], r["id"], r["line"]) for r in rep["collisions"]] == [("MAT", 2, 1), ("NODE", 5, 7)]
    assert rep["duplicates"] == [
        {"line": 5, "keyword": "/GRSHEL/PART/900001", "namespace": "GRUP", "id": 900001, "first_line": 3}
    ]
    assert [(r["namespace"], r["id"]) for r in rep["below_user_range"]] == [("MAT", 2)]  # NODE hariç


def test_clean_raw_cards_report_empty(tmp_path):
    rep = raw_card_report(_generated(tmp_path), "/GRNOD/NODE/900001\ng\n" + f"{1:10d}")
    assert rep == {"collisions": [], "duplicates": [], "below_user_range": []}


@requires_db
def test_inventory_endpoint():
    gid = _upload_and_mesh_box()
    r = client.post(
        "/crash/raw-cards/inventory",
        json={"geometry_id": gid, "barrier": _barrier(), "raw_cards": "/MAT/LAW1/1\nm"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nodes"]["count"] > 0 and body["elements"]["count"] > 0
    assert 1 in body["ids"]["MAT"]
    assert [(c["namespace"], c["id"]) for c in body["collisions"]] == [("MAT", 1)]
    # Geçici deck klasörü kalmaz.
    assert not any((CRASH_DIR / "_inventory").glob("*"))
