"""Faz 1.6 — crash websocket ilerleme (`/solve` dokunulmaz)."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.jobs.progress import get_hub
from app.main import app
from app.solvers.openradioss_progress import parse_progress_chunk, parse_progress_line


def setup_function() -> None:
    get_hub().reset()


def test_parse_cycle_line_percent():
    # listing sütun biçimi: 4. alan eleman tipi
    p = parse_progress_line(
        "      10  5.0000E+00  1.0000E-03 SHELL  12  0.0%  2.0000E+01  1.0000E+02",
        t_end_ms=10.0,
    )
    assert p is not None
    assert p.cycle == 10
    assert p.time_ms == pytest.approx(5.0)
    assert p.percent == pytest.approx(50.0)
    assert p.state == "running"


def test_parse_header_ignored():
    assert parse_progress_line("   CYCLE        TIME     TIMESTP", 10.0) is None


def test_parse_normal_termination():
    p = parse_progress_line("     NORMAL TERMINATION", 10.0)
    assert p is not None
    assert p.percent == 100.0


def test_parse_error_termination():
    p = parse_progress_line("     ERROR TERMINATION", 10.0)
    assert p is not None
    assert p.state == "failed"


def test_parse_chunk_keeps_last_cycle():
    text = """
   CYCLE        TIME     TIMESTP      IENERGY
       0  0.0000E+00  1.0000E-03  0.0000E+00
      20  8.0000E+00  1.0000E-03  1.0000E+01
"""
    p = parse_progress_chunk(text, t_end_ms=10.0)
    assert p is not None
    assert p.cycle == 20
    assert p.percent == pytest.approx(80.0)


def test_snapshot_404_unknown():
    client = TestClient(app)
    assert client.get("/crash/jobs/nope").status_code == 404


def test_snapshot_after_create():
    hub = get_hub()
    hub.create("j1")
    hub.update("j1", state="running", percent=25.0, cycle=4, time_ms=2.5)
    client = TestClient(app)
    body = client.get("/crash/jobs/j1").json()
    assert body["job_id"] == "j1"
    assert body["percent"] == 25.0
    assert body["cycle"] == 4
    assert body["kind"] == "crash"


def test_websocket_streams_until_done():
    hub = get_hub()
    hub.create("ws1")
    hub.update("ws1", state="running", percent=10.0, cycle=1, time_ms=1.0)
    with TestClient(app) as client:
        with client.websocket_connect("/crash/jobs/ws1/ws") as ws:
            first = ws.receive_json()
            assert first["percent"] == 10.0
            hub.update("ws1", state="done", percent=100.0, cycle=99, time_ms=10.0)
            last = ws.receive_json()
            assert last["state"] == "done"
            assert last["percent"] == 100.0


def test_websocket_unknown_job_closes():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/crash/jobs/missing/ws") as ws:
                ws.receive_json()


def test_parse_dt_from_real_listing_line():
    """1.23 D3 — gerçek engine listing satırı (koşu #325): 3. sütun TIME-STEP (ms)."""
    p = parse_progress_line(
        "     100  0.5400E-01  0.5396E-03 SHELL       1957   0.0%   45.49       13.34      0.3981E-01"
        "   0.000       0.000       1.187       0.000",
        t_end_ms=4.0,
    )
    assert p is not None
    assert p.cycle == 100
    assert p.time_ms == pytest.approx(0.054)
    assert p.dt_ms == pytest.approx(5.396e-4)
    assert p.percent == pytest.approx(1.35)


def test_parse_dt_missing_or_invalid_is_none():
    assert parse_progress_line("      10  5.0", 10.0).dt_ms is None
    assert parse_progress_line("      10  5.0  NaN", 10.0).dt_ms is None
    assert parse_progress_line("      10  5.0  0.0", 10.0).dt_ms is None


def test_hub_dt_ms_in_snapshot():
    hub = get_hub()
    hub.create("d3")
    hub.update("d3", state="running", cycle=100, time_ms=0.054, dt_ms=5.396e-4)
    snap = hub.get("d3").to_dict()
    assert snap["dt_ms"] == pytest.approx(5.396e-4)
    assert snap["cycle"] == 100


def test_job_snapshot_endpoint_carries_dt(tmp_path, monkeypatch):
    import json

    import app.api.crash as crash_api

    monkeypatch.setattr(crash_api, "CRASH_DIR", tmp_path)
    (tmp_path / "jd3").mkdir()
    (tmp_path / "jd3" / "job.json").write_text(json.dumps({"job_id": "jd3", "status": "running"}), encoding="utf-8")
    get_hub().create("jd3")
    get_hub().update("jd3", state="running", cycle=7, time_ms=0.01, dt_ms=2.5e-4)
    body = TestClient(app).get("/crash/jobs/jd3").json()
    assert body["dt_ms"] == pytest.approx(2.5e-4)
    assert body["cycle"] == 7


def test_stream_ignores_timing_table_after_termination():
    """1.23 D3 — gerçek listing kuyruğu (koşu #325 tekrarı): bitişten sonra zamanlama tablosu."""
    tail = (
        "    7400   3.996      0.5398E-03 SHELL       1945  -0.1%   55.56       3.126      0.1076"
        "       0.000       0.000       1.187       0.000\n"
        " NORMAL TERMINATION\n"
        "   1   .4804E+01 .3618E+00 .7280E+00 .1764E+01 .6694E+00 .5541E+00 .9471E+01\n"
    )
    last = parse_progress_chunk(tail, 4.0)
    assert last is not None
    assert last.percent == 100.0
    assert last.cycle is None  # zamanlama tablosundaki "1" cycle sayılmaz
    from app.solvers.openradioss_progress import ProgressStream

    s = ProgressStream(4.0)
    got = [s.feed(line) for line in tail.splitlines()]
    assert got[0].dt_ms == pytest.approx(5.398e-4)
    assert got[2] is None


def test_parse_engine_stdout_nc_line():
    """1.23 D3 — gerçek engine stdout'u (koşu #325 kurulumu, 20 ms)."""
    p = parse_progress_line(" NC=   37000 T= 1.9980E+01 DT= 5.3986E-04 ERR= -0.5% DM/M= 0.0000E+00", t_end_ms=20.0)
    assert p is not None
    assert p.cycle == 37000
    assert p.time_ms == pytest.approx(19.98)
    assert p.dt_ms == pytest.approx(5.3986e-4)
    assert p.mass_added_rel == 0.0
    assert p.percent == pytest.approx(99.9)


def test_parse_engine_stdout_times_line_keeps_percent():
    p = parse_progress_line(" ELAPSED TIME=         15.57 s  REMAINING TIME=          0.02 s", t_end_ms=20.0)
    assert p is not None
    assert (p.elapsed_s, p.remaining_s) == (pytest.approx(15.57), pytest.approx(0.02))
    assert p.percent is None and p.cycle is None
    hub = get_hub()
    hub.create("tm")
    hub.update("tm", percent=40.0, cycle=10)
    hub.update("tm", percent=p.percent, elapsed_s=p.elapsed_s, remaining_s=p.remaining_s)
    snap = hub.get("tm")
    assert snap.percent == 40.0 and snap.remaining_s == pytest.approx(0.02)


def test_cpu_summary_row_is_not_progress():
    """Bitişteki CPU tablosu satırı (4. alan sayı) ilerleme değil."""
    assert parse_progress_line("   1   .2512E+02 .1815E+01 .4247E+01 .4304E+01 .4733E+01 .2500E+01 .4547E+02", 20.0) is None
