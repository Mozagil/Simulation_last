"""1.23 C6 — enerji grafiği verisi: temas enerjisi, dış iş, toplam enerji eğrisi + özet."""

from __future__ import annotations

import pytest

from app.postprocess.openradioss_th import parse_openradioss_dir


def test_contact_external_total_energy(tmp_path):
    h = ['"time"', '"INTERNAL ENERGY"', '"KINETIC ENERGY"', '"EXTERNAL WORK"', '"CONTACT ENERGY"',
         '"HOURGLASS ENERGY"']
    rows = ["0,0,100,0,0,0", "1,80,10,0,6,2"]
    (tmp_path / "crashT01.csv").write_text("\n".join([",".join(h), *rows]) + "\n", encoding="utf-8")
    res = parse_openradioss_dir(tmp_path)
    assert res.curves["contact_energy"] == [0.0, 6.0]
    assert res.curves["external_work"] == [0.0, 0.0]
    # toplam = IE + KE + HG − dış iş (energy_balance_rel ile aynı tanım)
    assert res.curves["total_energy"] == pytest.approx([100.0, 92.0])
    s = res.scalars
    assert s["contact_energy_final"] == 6.0 and s["contact_energy_max"] == 6.0
    assert s["contact_energy_ratio"] == pytest.approx(6 / 80)
    assert s["external_work_final"] == 0.0
    assert s["energy_balance_rel"] == pytest.approx(8 / 100)


def test_no_contact_column_no_contact_curve(tmp_path):
    h = ['"time"', '"INTERNAL ENERGY"', '"KINETIC ENERGY"']
    (tmp_path / "crashT01.csv").write_text("\n".join([",".join(h), "0,0,10", "1,9,1"]) + "\n", encoding="utf-8")
    res = parse_openradioss_dir(tmp_path)
    assert "contact_energy" not in res.curves and "contact_energy_final" not in res.scalars
    assert res.curves["total_energy"] == [10.0, 10.0]
