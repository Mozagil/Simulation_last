"""0.5.6–0.5.9 surrogate: skaler RF, GNN, OOD, tahmin API."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.dataset.training_data import build_node_inputs, write_inputs, write_training_sample
from app.db.session import get_db
from app.main import app
from app.ml.gnn import predict_field, save_gnn, train_gnn
from app.ml.graph_data import GraphSample, knn_edges, load_graph
from app.ml.ood import bounds_from_matrix, is_out_of_domain
from app.ml.scalar_features import FEATURE_KEYS, collect_scalar_table
from app.ml.scalar_rf import MIN_SAMPLES, predict_scalar, save_scalar_rf, train_scalar_rf
from app.models.base import Base
from app.models.geometry import Geometry
from app.models.run import AnalysisRun
from app.solvers.calculix import _resolve_bc_node_ids


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ml.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _geo_run(db, *, length, thickness, width, fy, disp, vm, element_size=8.0, status="solved"):
    g = Geometry(
        original_filename="b.step",
        current_filename="b.step",
        template_id="cantilever_beam",
        template_params={"length": length, "thickness": thickness, "width": width},
    )
    db.add(g)
    db.flush()
    r = AnalysisRun(
        geometry_id=g.id,
        dimension=3,
        element_size=element_size,
        element_scheme="tet",
        bcs=[{"type": "fixed", "face_ids": [1]}, {"type": "cload", "fy": fy}],
        materials_snapshot=[
            {"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}
        ],
        status=status,
        scalars={"max_displacement": disp, "max_von_mises": vm, "node_count": 100},
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return g, r


def test_collect_scalar_table_skips_unsolved(db_session):
    _geo_run(db_session, length=500, thickness=10, width=40, fy=-500, disp=20.0, vm=200.0)
    _geo_run(
        db_session,
        length=500,
        thickness=10,
        width=40,
        fy=-500,
        disp=1.0,
        vm=1.0,
        status="inp_only",
    )
    X, y, ids = collect_scalar_table(db_session)
    assert len(ids) == 1
    assert X.shape == (1, len(FEATURE_KEYS))
    assert y[0, 0] == pytest.approx(20.0)


def test_random_forest_fits_synthetic_beam_table(tmp_path):
    rng = np.random.default_rng(0)
    n = 40
    L = rng.uniform(450, 700, n)
    T = rng.uniform(8, 12, n)
    W = rng.uniform(35, 70, n)
    F = rng.uniform(200, 800, n)
    disp = 4.0 * F * (L**3) / (210e3 * W * T**3)
    vm = 6.0 * F * L / (W * T**2) / 1000.0
    X = np.column_stack(
        [
            L,
            T,
            W,
            np.full(n, 8.0),
            np.full(n, 210e9),
            np.full(n, 0.3),
            np.zeros(n),
            -F,
            np.zeros(n),
            np.zeros(n),
            np.full(n, 3.0),
        ]
    )
    y = np.column_stack([disp, vm])
    bundle = train_scalar_rf(X, y, seed=1, n_estimators=40)
    assert bundle["n_samples"] == n
    assert bundle["metrics"]["train"]["max_displacement"]["r2"] > 0.85
    path = save_scalar_rf(bundle, tmp_path / "rf.joblib")
    assert path.is_file()
    inside = predict_scalar(bundle, X[0])
    assert inside["out_of_domain"] is False
    assert "max_displacement" in inside["predictions"]


def test_too_few_samples_raises():
    X = np.zeros((MIN_SAMPLES - 1, len(FEATURE_KEYS)))
    y = np.zeros((MIN_SAMPLES - 1, 2))
    with pytest.raises(ValueError, match="En az"):
        train_scalar_rf(X, y)


def test_out_of_domain_flags_extrapolation():
    X = np.array([[400.0, 10.0], [600.0, 12.0]])
    bounds = bounds_from_matrix(X)
    assert is_out_of_domain(np.array([500.0, 11.0]), bounds) is False
    assert is_out_of_domain(np.array([2000.0, 11.0]), bounds) is True
    assert is_out_of_domain(np.array([500.0, 1.0]), bounds) is True


def _line_sample(scale: float, *, es: float | None = None) -> GraphSample:
    n = 6
    X = np.zeros((n, 14), dtype=np.float64)
    X[:, 0] = np.linspace(0, 100.0 * scale, n)
    X[:, 10] = 210000.0
    X[:, 11] = 0.3
    Y = np.zeros((n, 4), dtype=np.float64)
    Y[:, 1] = (X[:, 0] / (100.0 * scale)) ** 2 * 5.0 * scale
    Y[:, 3] = 50.0 * scale * (X[:, 0] / (100.0 * scale))
    edges = knn_edges(X[:, :3], k=2)
    return GraphSample(
        run_id=None,
        node_inputs=X,
        node_outputs=Y,
        edges=edges,
        node_ids=np.arange(1, n + 1, dtype=np.int32),
        element_size=es,
    )


def test_gnn_overfits_two_line_graphs_and_reports_size_rmse():
    samples = [_line_sample(1.0, es=8.0), _line_sample(1.1, es=12.0)]
    bundle = train_gnn(samples, seed=0, hidden=16, sgd_steps=4)
    assert bundle["n_samples"] == 2
    rmse = bundle["metrics"]["node_rmse"]
    assert rmse["u_y"] < 2.0
    assert "8.0" in bundle["metrics"]["rmse_by_element_size"]
    assert "12.0" in bundle["metrics"]["rmse_by_element_size"]
    yhat = predict_field(bundle, samples[0])
    assert yhat.shape == samples[0].node_outputs.shape


def test_load_graph_uses_knn_when_connectivity_empty(tmp_path):
    coords = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)]
    X = build_node_inputs(
        coords,
        [{"type": "fixed", "face_ids": [1]}],
        {"FACE_1": [1]},
        [{"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850}],
        3,
        0.0,
        _resolve_bc_node_ids,
    )
    ip = tmp_path / "a.inputs.npz"
    write_inputs(ip, X, None)
    tp = tmp_path / "a.train.npz"
    write_training_sample(
        ip,
        tp,
        [1, 2, 3, 4],
        [[0, 0, 0], [0, 0.1, 0], [0, 0.4, 0], [0, 0.9, 0]],
        [0.0, 10.0, 20.0, 30.0],
    )
    g = load_graph(tp, run_id=7)
    assert g is not None
    assert g.edges.shape[0] > 0
    assert g.node_outputs is not None


def test_predict_api_returns_preview_schema_and_ood(db_session, tmp_path, monkeypatch):
    _g, r = _geo_run(
        db_session, length=500, thickness=10, width=40, fy=-500, disp=20.0, vm=200.0
    )
    rng = np.random.default_rng(1)
    n = 16
    X = np.column_stack(
        [
            rng.uniform(450, 700, n),
            rng.uniform(8, 12, n),
            rng.uniform(35, 70, n),
            np.full(n, 8.0),
            np.full(n, 210e9),
            np.full(n, 0.3),
            np.zeros(n),
            rng.uniform(-800, -200, n),
            np.zeros(n),
            np.zeros(n),
            np.full(n, 3.0),
        ]
    )
    y = np.column_stack([0.05 * X[:, 0], 0.4 * np.abs(X[:, 7])])
    bundle = train_scalar_rf(X, y, n_estimators=20)
    rf_path = tmp_path / "rf.joblib"
    save_scalar_rf(bundle, rf_path)
    monkeypatch.setattr("app.api.surrogate.DEFAULT_MODEL_PATH", rf_path)
    monkeypatch.setattr("app.api.surrogate.DEFAULT_GNN_PATH", tmp_path / "missing_gnn.npz")

    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        st = client.get("/surrogate/status")
        assert st.status_code == 200
        assert st.json()["scalar_rf"]["n_samples"] == 16
        pred = client.post("/surrogate/predict", json={"run_id": r.id})
        assert pred.status_code == 200, pred.text
        body = pred.json()
        assert body["source"] == "surrogate"
        assert body["kind"] == "scalar"
        assert body["preview"]["source"] == "surrogate_scalar"
        assert "max_displacement" in body["preview"]
        ood = client.post(
            "/surrogate/scalar/predict",
            json={"features": {k: 0.0 for k in FEATURE_KEYS} | {"length": 5000.0}},
        )
        assert ood.status_code == 200
        assert ood.json()["out_of_domain"] is True
        params = client.post(
            "/surrogate/predict/params",
            json={
                "length": 500.0,
                "thickness": 10.0,
                "width": 40.0,
                "element_size": 8.0,
                "load_fy": -500.0,
                "compare_run_id": r.id,
            },
        )
        assert params.status_code == 200, params.text
        pbody = params.json()
        assert pbody["kind"] == "scalar"
        assert "max_displacement" in pbody["predictions"]
        assert pbody["fea"]["run_id"] == r.id
        assert pbody["fea"]["max_displacement"] == pytest.approx(20.0)
        assert pbody["deviation_pct"]["max_displacement_pct"] is not None
        no_run = client.post(
            "/surrogate/predict/params",
            json={"length": 500.0, "thickness": 10.0, "width": 40.0, "load_fy": -500.0},
        )
        assert no_run.status_code == 200
        assert no_run.json()["fea"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_field_predict_matches_preview_keys(tmp_path):
    samples = [_line_sample(1.0), _line_sample(1.05)]
    bundle = train_gnn(samples, seed=2, hidden=12, sgd_steps=2)
    save_gnn(bundle, tmp_path / "g.npz")
    yhat = predict_field(bundle, samples[0])
    mag = np.linalg.norm(yhat[:, :3], axis=1)
    assert mag.shape[0] == samples[0].node_inputs.shape[0]
    assert yhat.shape[1] == 4
