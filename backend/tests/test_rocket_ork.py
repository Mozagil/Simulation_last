"""R6 — OpenRocket .ork içe aktarma (zip + XML → R1 parametreleri)."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.templates.rocket import RocketParams
from app.templates.rocket_ork import OrkError, ork_to_params, read_ork_xml

ORK = b"""<?xml version='1.0' encoding='utf-8'?>
<openrocket version="1.9" creator="OpenRocket 23.09">
  <rocket><name>Deneme</name><subcomponents><stage><name>Sustainer</name><subcomponents>
    <nosecone><name>Burun</name><length>0.3</length><shape>haack</shape><shapeparameter>0.0</shapeparameter><aftradius>auto 0.05</aftradius></nosecone>
    <bodytube><name>Ust</name><length>0.5</length><radius>auto 0.05</radius></bodytube>
    <bodytube><name>Alt</name><length>0.7</length><radius>0.05</radius>
      <subcomponents><trapezoidfinset><name>Kanat</name><position type="bottom">-0.02</position>
        <fincount>3</fincount><rootchord>0.15</rootchord><tipchord>0.06</tipchord><height>0.1</height>
        <sweeplength>0.08</sweeplength><thickness>0.004</thickness></trapezoidfinset></subcomponents>
    </bodytube>
    <transition><name>Kuyruk</name><length>0.06</length><shape>conical</shape><foreradius>auto</foreradius><aftradius>0.04</aftradius></transition>
  </subcomponents></stage></subcomponents></rocket>
</openrocket>"""


def _zip(xml: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("rocket.ork", xml)
    return buf.getvalue()


def test_ork_mapping_zip():
    out = ork_to_params(read_ork_xml(_zip(ORK)))
    p = out["params"]
    assert out["name"] == "Deneme"
    assert p["nose_shape"] == "von_karman" and p["nose_length"] == 300
    assert p["body_diameter"] == 100 and p["body_length"] == 1200
    assert (p["fin_count"], p["fin_root_chord"], p["fin_tip_chord"], p["fin_span"], p["fin_sweep"], p["fin_thickness"]) == (3, 150, 60, 100, 80, 4)
    assert p["fin_offset"] == 20
    assert p["boattail_length"] == 60 and p["boattail_aft_diameter"] == 80
    assert any("2 gövde tüpü" in n for n in out["notes"])
    RocketParams.model_validate(p)


def test_plain_xml_and_rejects():
    assert read_ork_xml(ORK).tag == "openrocket"
    with pytest.raises(OrkError):
        read_ork_xml(b"<rocket/>")
    with pytest.raises(OrkError):
        read_ork_xml(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><openrocket/>')


def test_endpoint():
    c = TestClient(app)
    r = c.post("/cfd/rocket/ork", files={"file": ("d.ork", _zip(ORK), "application/octet-stream")})
    assert r.status_code == 200 and r.json()["valid"] is True
    assert c.post("/cfd/rocket/ork", files={"file": ("x.ork", b"bozuk", "application/octet-stream")}).status_code == 422


def test_axialoffset_new_format():
    xml = ORK.replace(b'<position type="bottom">-0.02</position>', b'<axialoffset method="bottom">-0.03</axialoffset><position type="bottom">-0.02</position>')
    assert ork_to_params(read_ork_xml(xml))["params"]["fin_offset"] == 30
