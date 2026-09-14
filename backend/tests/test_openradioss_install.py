"""Faz 1.4 — OpenRadioss ikili çözümleme (indirilmez; sahte dosya ağacı)."""

from pathlib import Path

from app.solvers.openradioss import (
    OPENRADIOSS_LINUX_ZIP,
    OPENRADIOSS_RELEASE,
    OpenRadiossAdapter,
    resolve_openradioss,
    runtime_env,
)


def _fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "OpenRadioss"
    execd = home / "exec"
    execd.mkdir(parents=True)
    (execd / "starter_linux64_gf").write_bytes(b"s")
    (execd / "engine_linux64_gf").write_bytes(b"e")
    (home / "hm_cfg_files").mkdir()
    (home / "extlib" / "hm_reader" / "linux64").mkdir(parents=True)
    (home / "extlib" / "h3d" / "lib" / "linux64").mkdir(parents=True)
    return home


def test_release_url_is_pinned():
    assert OPENRADIOSS_RELEASE == "latest-20260728"
    assert "OpenRadioss_linux64.zip" in OPENRADIOSS_LINUX_ZIP
    assert OPENRADIOSS_RELEASE in OPENRADIOSS_LINUX_ZIP


def test_resolve_from_official_home_dir(tmp_path, monkeypatch):
    home = _fake_home(tmp_path)
    monkeypatch.setenv("OPENRADIOSS_PATH", str(home))
    monkeypatch.delenv("OPENRADIOSS_HOME", raising=False)
    monkeypatch.setattr("app.solvers.openradioss.shutil.which", lambda _n: None)
    bins = resolve_openradioss()
    assert bins is not None
    assert bins.engine.name == "engine_linux64_gf"
    assert bins.starter is not None and bins.starter.name == "starter_linux64_gf"
    assert bins.home == home
    env = runtime_env(bins)
    assert env["RAD_CFG_PATH"] == str(home / "hm_cfg_files")
    assert str(home / "extlib" / "hm_reader" / "linux64") in env["LD_LIBRARY_PATH"]


def test_submit_runs_starter_then_engine(tmp_path, monkeypatch):
    home = _fake_home(tmp_path)
    monkeypatch.setenv("OPENRADIOSS_PATH", str(home))
    monkeypatch.setattr("app.solvers.openradioss.shutil.which", lambda _n: None)
    calls: list[list[str]] = []

    class _P:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
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
    assert len(calls) == 2
    assert calls[0][0].endswith("starter_linux64_gf")
    assert calls[0][1:4] == ["-i", "imp_0000.rad", "-np"]
    assert calls[1][0].endswith("engine_linux64_gf")
    assert calls[1][1:3] == ["-i", "imp_0001.rad"]
