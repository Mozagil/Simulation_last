"""OPENRADIOSS_DOCKER_IMAGE: starter/engine `docker run` ile imaj içinde koşar.

Windows geliştirme makinesinde OpenRadioss ikilisi yok; Docker Desktop (WSL2)
var. Adaptör komutu sarmalar, iş klasörünü /work'e bağlar; deck göreli ad
kullandığı için iki yolda da aynı dosyalar çalışır. ccx/durability koduna
dokunulmaz.
"""

from __future__ import annotations

from pathlib import Path

from app.solvers.openradioss import (
    DOCKER_HOME,
    OpenRadiossAdapter,
    launch_command,
    resolve_openradioss,
)


def test_docker_image_env_overrides_local_binaries(monkeypatch):
    monkeypatch.setenv("OPENRADIOSS_DOCKER_IMAGE", "simsurrogate-openradioss:test")
    monkeypatch.setenv("OPENRADIOSS_PATH", "/nonexistent")
    bins = resolve_openradioss()
    assert bins is not None
    assert bins.docker_image == "simsurrogate-openradioss:test"
    assert bins.home == DOCKER_HOME
    assert bins.starter is not None and bins.starter.name == "starter_linux64_gf"


def test_launch_command_wraps_with_docker_run(tmp_path):
    monkey_bins = resolve_openradioss.__globals__["_docker_bins"]("img:1")
    cmd = launch_command(monkey_bins, monkey_bins.engine, ["-i", "imp_0001.rad"], tmp_path)
    assert Path(cmd[0]).stem == "docker" and cmd[1:3] == ["run", "--rm"]
    assert "-v" in cmd and cmd[cmd.index("-v") + 1].endswith(":/work")
    assert cmd[cmd.index("-w") + 1] == "/work"
    assert cmd[cmd.index("img:1") + 1 :] == ["/opt/openradioss/exec/engine_linux64_gf", "-i", "imp_0001.rad"]


def test_docker_home_override_and_env_args(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENRADIOSS_DOCKER_IMAGE", "img:1")
    monkeypatch.setenv("OPENRADIOSS_DOCKER_HOME", "/opt/OpenRadioss/OpenRadioss")
    monkeypatch.setenv("OPENRADIOSS_THREADS", "2")
    bins = resolve_openradioss()
    assert bins is not None and bins.starter is not None
    assert bins.starter.as_posix() == "/opt/OpenRadioss/OpenRadioss/exec/starter_linux64_gf"
    cmd = launch_command(bins, bins.starter, ["-i", "a_0000.rad", "-np", "1"], tmp_path)
    env = " ".join(cmd)
    assert "RAD_CFG_PATH=/opt/OpenRadioss/OpenRadioss/hm_cfg_files" in env
    assert "LD_LIBRARY_PATH=/opt/OpenRadioss/OpenRadioss/extlib/hm_reader/linux64" in env
    assert "OMP_NUM_THREADS=2" in env
    # ortam bayrakları imaj adından ÖNCE gelmeli (docker run seçenekleri)
    assert cmd.index("-e") < cmd.index("img:1")


def test_launch_command_plain_without_docker(tmp_path):
    from app.solvers.openradioss import OpenRadiossBins

    bins = OpenRadiossBins(engine=Path("/x/engine_linux64_gf"), starter=None, home=None)
    assert launch_command(bins, bins.engine, ["-i", "a.rad"], tmp_path) == [str(bins.engine), "-i", "a.rad"]


def test_submit_uses_docker_for_starter_and_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRADIOSS_DOCKER_IMAGE", "img:1")
    calls: list[list[str]] = []

    class _P:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(
        "app.solvers.openradioss.subprocess.run",
        lambda cmd, **_k: (calls.append(list(cmd)), _P())[1],
    )
    art = OpenRadiossAdapter().build_input(
        {
            "output_dir": tmp_path / "job",
            "job_name": "imp",
            "nodes": [
                {"id": 1, "x": 0.0, "y": 0.0, "z": 10.0},
                {"id": 2, "x": 1.0, "y": 0.0, "z": 10.0},
                {"id": 3, "x": 0.0, "y": 1.0, "z": 10.0},
                {"id": 4, "x": 0.0, "y": 0.0, "z": 11.0},
            ],
            "tets": [(1, 1, 2, 3, 4)],
        }
    )
    OpenRadiossAdapter().submit(art)
    assert len(calls) == 2
    assert Path(calls[0][0]).stem == "docker" and calls[0][1:3] == ["run", "--rm"] and calls[0][-4:] == [
        "-i", "imp_0000.rad", "-np", "1",
    ]
    assert calls[0][cmd_idx(calls[0], "img:1") + 1].endswith("starter_linux64_gf")
    assert calls[1][-2:] == ["-i", "imp_0001.rad"]
    assert calls[1][cmd_idx(calls[1], "img:1") + 1].endswith("engine_linux64_gf")
    # iş klasörü /work olarak bağlanmalı
    assert any(a.endswith(":/work") for a in calls[0])


def test_submit_converts_time_history_when_t01_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRADIOSS_DOCKER_IMAGE", "img:1")
    calls: list[list[str]] = []

    class _P:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **_k):
        calls.append(list(cmd))
        # engine "koşunca" T01 üretmiş gibi yap
        if cmd[-2:] == ["-i", "imp_0001.rad"]:
            (tmp_path / "job" / "impT01").write_bytes(b"\x00")
        return _P()

    monkeypatch.setattr("app.solvers.openradioss.subprocess.run", fake_run)
    art = OpenRadiossAdapter().build_input(
        {
            "output_dir": tmp_path / "job",
            "job_name": "imp",
            "nodes": [
                {"id": 1, "x": 0.0, "y": 0.0, "z": 10.0},
                {"id": 2, "x": 1.0, "y": 0.0, "z": 10.0},
                {"id": 3, "x": 0.0, "y": 1.0, "z": 10.0},
                {"id": 4, "x": 0.0, "y": 0.0, "z": 11.0},
            ],
            "tets": [(1, 1, 2, 3, 4)],
        }
    )
    OpenRadiossAdapter().submit(art)
    assert len(calls) == 3
    assert calls[2][-2:] == ["/opt/openradioss/exec/th_to_csv_linux64_gf", "impT01"]
    log = (tmp_path / "job" / "openradioss.log").read_text(encoding="utf-8")
    assert "=== th_to_csv ===" in log


def cmd_idx(cmd: list[str], token: str) -> int:
    return cmd.index(token)
