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
    p = parse_progress_line(
        "      10  5.0000E+00  1.0000E-03  2.0000E+01  1.0000E+02",
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
