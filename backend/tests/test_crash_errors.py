"""Crash hata kodları: ıraksama = Hata #1 (failed), adaptör hataları sınıflanır."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.api.crash as crash_api
from app.postprocess.crash_errors import CRASH_ERRORS, classify_failure, error_message
from app.solvers.base import ResultSet, SolverError


def test_catalog_codes_fixed():
    assert set(CRASH_ERRORS) == {1, 2, 3, 4, 5, 9}


@pytest.mark.parametrize(
    "msg, code",
    [
        ("OpenRadioss bulunamadı (PATH)", 5),
        ("OpenRadioss zaman aşımı (600s).", 4),
        ("OpenRadioss hata (exit=3). Log: x.log", 3),
        ("beklenmedik", 9),
    ],
)
def test_classify_failure(msg, code):
    assert classify_failure(msg)["code"] == code


def test_starter_failure_lists_error_ids(tmp_path):
    (tmp_path / "crash_0000.out").write_text(
        "ERROR ID :   79\n ** detay\n\nERROR ID :   12\n", encoding="utf-8"
    )
    err = classify_failure("OpenRadioss starter hata (exit=2). Log: l", tmp_path)
    assert err["code"] == 2
    assert err["detail"] == "ERROR ID 12, 79"
    assert error_message(err) == "Hata #2 — Starter hatası: ERROR ID 12, 79"


class _Adapter:
    def __init__(self, scalars=None, exc=None):
        self.scalars, self.exc = scalars or {}, exc

    def submit(self, *_a, **_k):
        if self.exc:
            raise self.exc
        return object()

    def parse_results(self, _h):
        return ResultSet(scalars=self.scalars, curves={"time": [0.0, 1.0]}, diagnostics={})


def _run(tmp_path, monkeypatch, adapter) -> dict:
    monkeypatch.setattr(crash_api, "CRASH_DIR", tmp_path)
    monkeypatch.setattr(crash_api, "OpenRadiossAdapter", lambda: adapter)
    monkeypatch.setattr(crash_api, "_sync_run", lambda _m: None)
    crash_api._write_job({"job_id": "j1", "starter_path": str(tmp_path / "j1" / "crash_0000.rad")})
    crash_api._complete_crash_job("j1")
    return json.loads((Path(tmp_path) / "j1" / "job.json").read_text(encoding="utf-8"))


def test_diverged_run_is_failed_with_error_1(tmp_path, monkeypatch):
    meta = _run(tmp_path, monkeypatch, _Adapter(scalars={"diverged_at_ms": 0.01425}))
    assert meta["status"] == "failed"
    assert meta["solver_ran"] is True
    assert meta["curves"]["time"] == [0.0, 1.0]  # ıraksamaya kadar incelenebilir
    assert meta["diagnostics"]["error"]["code"] == 1
    assert meta["message"].startswith("Hata #1 — Çözüm ıraksadı: t = 0.01425 ms")


def test_clean_run_stays_solved(tmp_path, monkeypatch):
    meta = _run(tmp_path, monkeypatch, _Adapter(scalars={"rwall_force_max": 1.0}))
    assert meta["status"] == "solved"
    assert "error" not in meta["diagnostics"]


def test_engine_exit_is_error_3(tmp_path, monkeypatch):
    meta = _run(tmp_path, monkeypatch, _Adapter(exc=SolverError("OpenRadioss hata (exit=1). Log: l")))
    assert meta["status"] == "failed"
    assert meta["diagnostics"]["error"]["code"] == 3
    assert meta["message"].startswith("Hata #3 — ")


def test_corpus_skips_legacy_diverged_solved_runs():
    """2026-10-14 öncesi ıraksayan koşu "solved" kaydedildi; korpus yine almaz."""
    from types import SimpleNamespace

    from app.ml.crash.corpus import load_records

    def run(i, scalars):
        return SimpleNamespace(id=i, job_id=f"j{i}", request={}, scalars=scalars)

    rows = [(run(1, {"rwall_force_max": 1.0}), "t", {}), (run(2, {"diverged_at_ms": 0.01}), "t", {})]
    db = SimpleNamespace(execute=lambda _q: SimpleNamespace(all=lambda: rows))
    assert [r.run_id for r in load_records(db)] == [1]
