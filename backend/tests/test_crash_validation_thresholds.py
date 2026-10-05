"""Validasyon eşikleri: mühendis girer, dosyada saklanır; araç eşik koymaz."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api import crash_scenario
from app.main import app

client = TestClient(app)


@pytest.fixture
def thr_file(tmp_path, monkeypatch):
    path = tmp_path / "crash_thresholds.json"
    monkeypatch.setattr(crash_scenario, "VALIDATION_THRESHOLDS", path)
    return path


def test_empty_when_no_file(thr_file):
    r = client.get("/crash/validation/thresholds")
    assert r.status_code == 200
    d = r.json()
    assert d["cases"] == {}
    assert all(v is None for v in d["default"].values())


def test_put_roundtrip_drops_empty_cases(thr_file):
    body = {
        "default": {"ratio_min": 0.9, "ratio_max": 1.1, "energy_balance_max": 0.05},
        "cases": {"V8": {"ratio_min": 0.5}, "V3": {}},
    }
    r = client.put("/crash/validation/thresholds", json=body)
    assert r.status_code == 200, r.text
    saved = json.loads(thr_file.read_text(encoding="utf-8"))
    assert saved["default"]["ratio_max"] == 1.1 and saved["default"]["hourglass_max"] is None
    assert list(saved["cases"]) == ["V8"] and saved["updated_at"]
    assert client.get("/crash/validation/thresholds").json()["cases"]["V8"]["ratio_min"] == 0.5


@pytest.mark.parametrize("body", [
    {"default": {"ratio_min": 1.2, "ratio_max": 1.1}},
    {"cases": {"X1": {"ratio_min": 0.9}}},
    {"default": {"energy_balance_max": -0.1}},
])
def test_invalid_rejected(thr_file, body):
    assert client.put("/crash/validation/thresholds", json=body).status_code == 422
    assert not thr_file.exists()
