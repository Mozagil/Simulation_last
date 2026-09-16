"""OpenRadioss adaptörü — Faz 1.1 starter/engine yazımı (engine ikilisi gerekmez)."""

import pytest

from app.solvers.base import SolverError
from app.solvers.openradioss import OpenRadiossAdapter, _engine_executable


def _tiny_tet():
    return {
        "output_dir": None,  # filled in test
        "job_name": "imp",
        "title": "tiny_tet",
        "nodes": [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 10.0},
            {"id": 2, "x": 1.0, "y": 0.0, "z": 10.0},
            {"id": 3, "x": 0.0, "y": 1.0, "z": 10.0},
            {"id": 4, "x": 0.0, "y": 0.0, "z": 11.0},
        ],
        "tets": [(1, 1, 2, 3, 4)],
        "initial_velocity": {"vx": 0.0, "vy": 0.0, "vz": -8000.0},
        "rigid_wall": {"point": [0.0, 0.0, 0.0], "normal": [0.0, 0.0, 1.0]},
        "t_end_ms": 5.0,
        "materials": [
            {
                "name": "S235",
                "density": 7850.0,
                "youngs_modulus": 210e9,
                "poisson_ratio": 0.3,
            }
        ],
    }


def test_build_input_writes_starter_and_engine(tmp_path):
    params = _tiny_tet()
    params["output_dir"] = tmp_path
    art = OpenRadiossAdapter().build_input(params)
    assert art.path == tmp_path / "imp_0000.rad"
    starter = art.path.read_text(encoding="utf-8")
    engine = (tmp_path / "imp_0001.rad").read_text(encoding="utf-8")
    assert "/BEGIN" in starter
    assert "/NODE" in starter
    assert "/TETRA4/1/1" in starter
    assert "/INIVEL/TRA/1" in starter
    assert "-8000" in starter
    assert "/RWALL/PLANE/1" in starter
    assert "/TH/RWALL/1" in starter
    assert "/MAT/LAW1/1" in starter
    assert "/RUN/imp/1" in engine
    assert "/TH/TITLE" in engine
    assert "/STOP" in engine
    assert "/ANIM/VECT/VEL" in engine


def test_build_input_rejects_empty_nodes(tmp_path):
    with pytest.raises(SolverError, match="nodes"):
        OpenRadiossAdapter().build_input({"output_dir": tmp_path, "nodes": []})


def test_submit_without_binary_raises(tmp_path, monkeypatch):
    params = _tiny_tet()
    params["output_dir"] = tmp_path
    art = OpenRadiossAdapter().build_input(params)
    monkeypatch.delenv("OPENRADIOSS_PATH", raising=False)
    monkeypatch.delenv("OPENRADIOSS_HOME", raising=False)
    monkeypatch.setattr("app.solvers.openradioss.shutil.which", lambda _n: None)
    monkeypatch.setattr("app.solvers.openradioss._install_roots", lambda: [])
    with pytest.raises(SolverError, match="OpenRadioss bulunamadı"):
        OpenRadiossAdapter().submit(art)


def test_engine_executable_uses_env(tmp_path, monkeypatch):
    fake = tmp_path / "engine_openradioss.exe"
    fake.write_bytes(b"x")
    monkeypatch.setenv("OPENRADIOSS_PATH", str(fake))
    assert _engine_executable() == str(fake)


def test_parse_results_empty_without_tfile(tmp_path):
    params = _tiny_tet()
    params["output_dir"] = tmp_path
    adapter = OpenRadiossAdapter()
    art = adapter.build_input(params)
    from app.solvers.base import JobHandle

    rs = adapter.parse_results(JobHandle(job_id="j", work_dir=tmp_path, artifact=art))
    assert rs.scalars == {}
    assert rs.raw_result_path == tmp_path


def test_build_input_plastic_writes_law2_and_type14_nip(tmp_path):
    params = _tiny_tet()
    params["output_dir"] = tmp_path
    params["materials"][0]["yield_strength"] = 235e6
    params["model"] = {
        "law": "plastic",
        "isolid": 14,
        "ismstr": 2,
        "nip": 4,
        "harden_b_mpa": 150.0,
        "harden_n": 0.22,
    }
    starter = OpenRadiossAdapter().build_input(params).path.read_text(encoding="utf-8")
    assert "/MAT/LAW2/1" in starter
    assert "/MAT/LAW1/" not in starter
    assert "/PROP/TYPE14/1" in starter
    assert "        14         2         0         0         4" in starter
    law2 = starter.split("/MAT/LAW2/1", 1)[1]
    assert "150" in law2
    assert "0.22" in law2


def test_build_input_plastic_without_yield_is_solver_error(tmp_path):
    params = _tiny_tet()
    params["output_dir"] = tmp_path
    params["model"] = {"law": "plastic"}
    with pytest.raises(SolverError, match="σy"):
        OpenRadiossAdapter().build_input(params)


def test_build_input_invalid_model_is_solver_error(tmp_path):
    params = _tiny_tet()
    params["output_dir"] = tmp_path
    params["model"] = {"law": "hyperelastic"}
    with pytest.raises(SolverError, match="model"):
        OpenRadiossAdapter().build_input(params)
