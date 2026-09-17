"""Şablonların varsayılan (referans) sınır koşulları.

Her şablon `default_bcs` ile gelir: bölge adıyla bağlı BC listesi. Geometri
üretilince gerçek yüzey/kenar id'lerine çevrilir ve arayüzde hazır liste
olarak sunulur. Buradaki testler: her şablonun default_bcs'i geçerli
bölgelere bağlı, en az bir kısıt + bir yük içeriyor, ve gerçek kurulumda
id'lere çevrilebiliyor; API `create` yanıtı bunları bağlı halde döndürüyor.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.templates import bind_region_bcs, build_template, list_templates
from app.templates.base import BC_KEY_FOR_DIM, GeometryTemplate, Region, TemplateError, plane_at

CONSTRAINT_TYPES = {"fixed", "displacement", "sliding"}
LOAD_TYPES = {"cload", "pressure", "gravity", "bearing"}


@pytest.mark.parametrize("template", list_templates(), ids=lambda t: t.id)
def test_every_template_has_constraint_and_load(template):
    types = {bc["type"] for bc in template.default_bcs}
    assert types & CONSTRAINT_TYPES, f"{template.id}: kısıt yok"
    assert types & LOAD_TYPES, f"{template.id}: yük yok"
    names = {r.name for r in template.regions}
    assert all(bc["region"] in names for bc in template.default_bcs)


@pytest.mark.parametrize("template", list_templates(), ids=lambda t: t.id)
def test_default_bcs_bind_to_real_entities(tmp_path, template):
    """Gerçek kurulum: her BC doğru anahtarla (face/edge/node) ve boş olmayan id'lerle bağlanmalı."""
    params = template.parse_params({})
    built = build_template(template, params, tmp_path / f"{template.id}.step")
    bound = bind_region_bcs(template, built.regions)
    dims = {r.name: r.dim for r in template.regions}
    assert len(bound) == len(template.default_bcs)
    for bc in bound:
        key = BC_KEY_FOR_DIM[dims[bc["region"]]]
        assert bc[key], bc
        assert bc[key] == built.regions[bc["region"]]
        # Diğer hedef anahtarları sızmamalı
        for other in set(BC_KEY_FOR_DIM.values()) - {key}:
            assert other not in bc


def test_unknown_region_in_default_bcs_fails_at_definition():
    with pytest.raises(ValueError, match="hayali"):
        GeometryTemplate(
            id="x", name="x", description="", params_model=type("P", (), {}),  # type: ignore[arg-type]
            build=lambda p: None,
            regions=(Region("a", "", plane_at("x", 0.0)),),
            default_bcs=({"type": "fixed", "region": "hayali"},),
        )


def test_bind_fails_loudly_when_region_empty():
    t = list_templates()[0]
    with pytest.raises(TemplateError):
        bind_region_bcs(t, {})


# --- API ----------------------------------------------------------------------


def _db_available() -> bool:
    from app.db.session import SessionLocal

    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except OperationalError:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="PostgreSQL yok")


def test_list_templates_exposes_default_bcs():
    from fastapi.testclient import TestClient

    from app.main import app

    body = TestClient(app).get("/templates").json()
    cb = next(t for t in body["templates"] if t["id"] == "cantilever_beam")
    assert cb["default_bcs"] == [
        {"type": "fixed", "region": "ankastre_uc"},
        {"type": "cload", "region": "yuk_yuzeyi", "fx": 0.0, "fy": -500.0, "fz": 0.0},
    ]


@requires_db
def test_create_returns_bound_default_bcs():
    from fastapi.testclient import TestClient

    from app.api.geometry import UPLOAD_DIR
    from app.db.session import SessionLocal
    from app.main import app

    client = TestClient(app)
    r = client.post("/templates/cantilever_beam/create", json={"params": {}})
    assert r.status_code == 200, r.text
    body = r.json()
    try:
        bcs = body["default_bcs"]
        assert [b["type"] for b in bcs] == ["fixed", "cload"]
        assert bcs[0]["face_ids"] == body["regions"]["ankastre_uc"]
        assert bcs[1]["face_ids"] == body["regions"]["yuk_yuzeyi"]
        assert bcs[1]["fy"] == -500.0
        assert bcs[0]["region"] == "ankastre_uc"
    finally:
        from app.models.geometry import Geometry

        (UPLOAD_DIR / body["current_filename"]).unlink(missing_ok=True)
        db = SessionLocal()
        try:
            geo = db.get(Geometry, body["geometry_id"])
            if geo is not None:
                db.delete(geo)
                db.commit()
        finally:
            db.close()
