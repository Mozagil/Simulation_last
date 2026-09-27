"""/solve `region` alanını sessizce yok sayıyordu (TODO 8.1).

Bölge adıyla BC gönderilince (`{"type":"cload","region":"yuk_yuzeyi",...}`)
pydantic bilinmeyen alanı atıyor, BC hiçbir yüzeye bağlanmıyor ve model
YÜKSÜZ çözülüyordu. ccx hata vermez: sıfır deplasmanlı, "başarılı" görünen
bir sonuç çıkar. Bölge→yüzey bağlamayı yalnız DOE/yakınsama yolu yapıyordu.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.solve import SolveBC, _bind_regions, _require_targets
from app.models.base import Base
from app.models.geometry import Geometry, PhysicalGroup


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture()
def geo(db):
    g = Geometry(
        original_filename="k.step", current_filename="k.step",
        template_id="cantilever_beam",
        template_params={"length": 500.0, "thickness": 10.0, "width": 50.0},
    )
    db.add(g)
    db.flush()
    db.add(PhysicalGroup(geometry_id=g.id, name="ankastre_uc", dim=2, entity_tags=[1]))
    db.add(PhysicalGroup(geometry_id=g.id, name="yuk_yuzeyi", dim=2, entity_tags=[2]))
    db.add(PhysicalGroup(geometry_id=g.id, name="alt_kenar", dim=1, entity_tags=[7]))
    db.commit()
    return g


# --- modelde alan var mı ------------------------------------------------------


def test_region_alani_modelde_var():
    """Alan olmayınca pydantic sessizce atıyordu — hatanın kaynağı buydu."""
    bc = SolveBC(type="cload", region="yuk_yuzeyi", fy=-500.0)
    assert bc.region == "yuk_yuzeyi"
    assert "region" in bc.model_dump(exclude_none=True)


# --- bölge çözümü -------------------------------------------------------------


def test_bolge_yuzey_idlerine_cevrilir(db, geo):
    out = _bind_regions(db, geo.id, [
        {"type": "fixed", "region": "ankastre_uc"},
        {"type": "cload", "region": "yuk_yuzeyi", "fy": -500.0},
    ])
    assert out[0]["face_ids"] == [1]
    assert out[1]["face_ids"] == [2]
    assert out[1]["fy"] == -500.0
    assert "region" not in out[0], "bölge çözüldükten sonra ham ad kalmaz"


def test_kenar_bolgesi_edge_ids_olur(db, geo):
    out = _bind_regions(db, geo.id, [{"type": "cload", "region": "alt_kenar", "fz": -10.0}])
    assert out[0]["edge_ids"] == [7]
    assert "face_ids" not in out[0]


def test_bilinmeyen_bolge_422_ve_mevcutlari_yazar(db, geo):
    with pytest.raises(HTTPException) as exc:
        _bind_regions(db, geo.id, [{"type": "cload", "region": "yok_boyle", "fy": -1.0}])
    assert exc.value.status_code == 422
    assert "yuk_yuzeyi" in str(exc.value.detail), "mevcut bölgeler listelenmeli"


def test_bolgesiz_bcler_dokunulmadan_gecer(db, geo):
    bcs = [{"type": "fixed", "face_ids": [3]}, {"type": "cload", "node_ids": [9], "fy": -2.0}]
    assert _bind_regions(db, geo.id, [dict(b) for b in bcs]) == bcs


# --- hedefsiz BC --------------------------------------------------------------


def test_hedefsiz_yuk_reddedilir():
    """Hedefsiz cload modeli YÜKSÜZ çözer; ccx hata vermez."""
    with pytest.raises(HTTPException) as exc:
        _require_targets([{"type": "fixed", "face_ids": [1]}, {"type": "cload", "fy": -500.0}])
    assert exc.value.status_code == 422
    assert "#1 cload" in str(exc.value.detail)


@pytest.mark.parametrize("bc_type", ["fixed", "pressure", "displacement", "sliding", "bearing"])
def test_hedef_gerektiren_tipler(bc_type):
    with pytest.raises(HTTPException):
        _require_targets([{"type": bc_type, "magnitude": 1.0}])


def test_gravity_ve_rigid_body_hedef_istemez():
    """Yerçekimi hacim yüküdür, rigid body referans düğümle çalışır."""
    _require_targets([
        {"type": "gravity", "gz": -9810.0},
        {"type": "rigid_body", "ref_node_id": 5},
    ])


@pytest.mark.parametrize(
    "target", [{"face_ids": [1]}, {"edge_ids": [2]}, {"node_ids": [3]}, {"mesh_node_ids": [4]}]
)
def test_her_hedef_turu_kabul_edilir(target):
    _require_targets([{"type": "cload", "fy": -1.0, **target}])


def test_bolge_cozulunce_hedef_kontrolunden_gecer(db, geo):
    """İkisi birlikte: bölge adı verilen BC hedefsiz sayılmamalı."""
    bcs = _bind_regions(db, geo.id, [{"type": "cload", "region": "yuk_yuzeyi", "fy": -500.0}])
    _require_targets(bcs)
