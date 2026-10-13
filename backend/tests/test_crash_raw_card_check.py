"""1.22c — "Kontrol et": yalnız starter; ERROR/WARNING blokları aynen."""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

import app.db.session  # noqa: F401 — .env (OPENRADIOSS_DOCKER_*) yüklensin
from app.api.crash import CRASH_DIR
from app.postprocess.openradioss_th import starter_message_blocks
from app.solvers.base import SolverError
from app.solvers.openradioss import OpenRadiossAdapter, resolve_openradioss
from tests.test_crash_multipart import _two_part_params
from tests.test_crash_solve import _barrier, _upload_and_mesh_box, client, requires_db

_OUT = """\
 STARTER PRINT
ERROR ID :     79
** ERROR: DUPLICATE ID
DESCRIPTION :
   IN MATERIAL DEFINITION
   ID=1 is DUPLICATED

         SHELL ELEMENTS TIME STEP
WARNING ID :   1912
** WARNING IN SHELL PROPERTY
|       |---     1   ERROR ID :           79                |
"""

#: Ham kart ile üretilen MAT 1 çakışır → starter ERROR 79 (gerçek koşuda ölçüldü).
_DUP_MAT = "\n".join(["/MAT/LAW1/1", "kopya", f"{7.85e-9:20.8g}", f"{210000.0:20.8g}{0.3:20.8g}"])


def _starter_ready() -> bool:
    bins = resolve_openradioss()
    if bins is None or bins.starter is None:
        return False
    if not bins.docker_image:
        return True
    docker = shutil.which("docker")
    return bool(docker) and subprocess.run(
        [docker, "image", "inspect", bins.docker_image], capture_output=True, check=False
    ).returncode == 0


requires_starter = pytest.mark.skipif(not _starter_ready(), reason="OpenRadioss starter / imajı yok")

#: conftest .env Docker değişkenlerini her testte siler; gerçek starter testleri geri koyar.
_DOCKER_ENV = {k: os.environ[k] for k in ("OPENRADIOSS_DOCKER_IMAGE", "OPENRADIOSS_DOCKER_HOME") if k in os.environ}


@pytest.fixture
def docker_env(monkeypatch):
    for k, v in _DOCKER_ENV.items():
        monkeypatch.setenv(k, v)


def test_message_blocks_verbatim_and_summary_ignored():
    blocks = starter_message_blocks(_OUT)
    assert blocks == [
        {
            "kind": "error",
            "id": "79",
            "lines": [
                "ERROR ID :     79",
                "** ERROR: DUPLICATE ID",
                "DESCRIPTION :",
                "   IN MATERIAL DEFINITION",
                "   ID=1 is DUPLICATED",
            ],
        },
        {"kind": "warning", "id": "1912", "lines": ["WARNING ID :   1912", "** WARNING IN SHELL PROPERTY",
                                                     "|       |---     1   ERROR ID :           79                |"]},
    ]


def test_message_block_line_cap():
    text = "ERROR ID : 5\n" + "\n".join(f"satır {i}" for i in range(50))
    assert len(starter_message_blocks(text, max_lines=10)[0]["lines"]) == 10


def test_check_without_starter_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("app.solvers.openradioss.resolve_openradioss", lambda: None)
    art = OpenRadiossAdapter().build_input(_two_part_params(tmp_path))
    with pytest.raises(SolverError, match="starter bulunamadı"):
        OpenRadiossAdapter().check_starter(art)


@requires_starter
def test_real_starter_clean_vs_duplicate_mat(docker_env):
    for raw, exit_ok, n_err in (("", True, 0), (_DUP_MAT, False, 1)):
        d = CRASH_DIR / "_test_check" / ("bozuk" if raw else "temiz")
        shutil.rmtree(d, ignore_errors=True)
        try:
            p = _two_part_params(d)
            p["raw_cards"] = raw
            a = OpenRadiossAdapter()
            res = a.check_starter(a.build_input(p))
            blocks = [b for b in starter_message_blocks(res["out_text"]) if b["kind"] == "error"]
            assert (res["exit_code"] == 0) is exit_ok
            assert len(blocks) == n_err
            if n_err:
                assert blocks[0]["id"] == "79" and "   ID=1 is DUPLICATED" in blocks[0]["lines"]
        finally:
            shutil.rmtree(d, ignore_errors=True)


@requires_db
def test_check_endpoint_without_starter_is_503(monkeypatch):
    monkeypatch.setattr("app.solvers.openradioss.resolve_openradioss", lambda: None)
    gid = _upload_and_mesh_box()
    r = client.post("/crash/raw-cards/check", json={"geometry_id": gid, "barrier": _barrier()})
    assert r.status_code == 503
    assert not any((CRASH_DIR / "_check").glob("*"))


@requires_db
@requires_starter
def test_check_endpoint_real_starter(docker_env):
    gid = _upload_and_mesh_box()
    r = client.post(
        "/crash/raw-cards/check",
        json={"geometry_id": gid, "barrier": _barrier(), "raw_cards": _DUP_MAT},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exit_code"] != 0
    assert [e["id"] for e in body["errors"]] == ["79"]
    assert body["raw_cards_deck_line"] and body["raw_cards_deck_line"] > 1
    assert not any((CRASH_DIR / "_check").glob("*"))
