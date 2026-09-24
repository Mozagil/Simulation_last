"""Torch eğitimi + NumPy çıkarımı eşliği (TODO 1.3b).

KRİTİK: eğitim torch ile yapılıyor ama sunucu torch KURMUYOR — çıkarım
`gnn.py`'deki NumPy `forward` ile. İki uygulama ayrışırsa model sessizce
başka bir şey tahmin eder; hata vermez. Bu yüzden eşlik testle kilitli.

torch kurulu değilse (sunucu/CI) eşlik testleri atlanır, motor seçimi ve
holdout mantığı yine sınanır.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.gnn import (
    MIN_HOLDOUT_GRAPHS,
    NumpyMeshGNN,
    split_holdout,
    train_gnn,
)
from app.ml.gnn_torch import (
    TorchUnavailable,
    build_module,
    torch_available,
    train_torch_gnn,
    weights_to_numpy,
)
from app.ml.graph_data import GraphSample

torch_gerekli = pytest.mark.skipif(not torch_available(), reason="torch kurulu değil")


def _sample(i: int, n: int = 40) -> GraphSample:
    rng = np.random.default_rng(i)
    X = np.zeros((n, 14), dtype=np.float32)
    X[:, 0] = np.linspace(0, 500, n)
    X[:, 1] = rng.uniform(0, 10, n)
    X[:3, 3:6] = 1.0
    X[-1, 8] = -500.0
    X[:, 10] = 210000.0
    X[:, 11] = 0.3
    Y = np.zeros((n, 4), dtype=np.float32)
    Y[:, 1] = -0.02 * X[:, 0] ** 2 / 500.0 * (1 + 0.1 * i)
    Y[:, 3] = 120.0 * (1 - X[:, 0] / 500.0) * (1 + 0.1 * i)
    edges = np.stack([np.arange(n - 1), np.arange(1, n)], axis=1).astype(np.int32)
    return GraphSample(
        run_id=i, node_inputs=X, node_outputs=Y, edges=edges,
        node_ids=np.arange(1, n + 1, dtype=np.int32), edge_source="mesh",
    )


@pytest.fixture()
def samples():
    return [_sample(i) for i in range(14)]


# --- iki uygulama aynı mı ------------------------------------------------------


@torch_gerekli
def test_torch_ve_numpy_ayni_sonucu_verir(samples):
    """Aynı ağırlıklar, aynı graf → aynı çıktı. Eğitim/çıkarım köprüsü bu."""
    import torch

    module = build_module(14, 12, 4, 2, seed=5)
    s = samples[0]
    from app.ml.gnn_torch import _graph_tensors

    X, _, src, dst, deg = _graph_tensors(s, torch)
    with torch.no_grad():
        beklenen = module(X, src, dst, deg).numpy()

    numpy_model = NumpyMeshGNN.from_npz(weights_to_numpy(module))
    alinan = numpy_model.forward(s.node_inputs, s.edges)

    assert alinan == pytest.approx(beklenen, rel=1e-12)


@torch_gerekli
def test_egitilmis_agirliklar_da_esit(samples):
    import torch

    from app.ml.gnn_torch import _graph_tensors

    weights, _ = train_torch_gnn(samples[:10], epochs=5, hidden=8)
    numpy_model = NumpyMeshGNN.from_npz(weights)

    module = build_module(14, 8, 4, 2, seed=2026)
    module.load_state_dict(
        {k: torch.as_tensor(v, dtype=torch.float64) for k, v in weights.items() if k != "n_proc"}
    )
    X, _, src, dst, deg = _graph_tensors(samples[0], torch)
    with torch.no_grad():
        beklenen = module(X, src, dst, deg).numpy()

    assert numpy_model.forward(samples[0].node_inputs, samples[0].edges) == pytest.approx(
        beklenen, rel=1e-12
    )


@torch_gerekli
def test_kenarsiz_graf_da_esit():
    """Kenar yokken toplama atlanıyor; iki yol yine aynı olmalı."""
    import torch

    from app.ml.gnn_torch import _graph_tensors

    s = _sample(0, n=6)
    s.edges = np.zeros((0, 2), dtype=np.int32)
    module = build_module(14, 6, 4, 2, seed=1)
    X, _, src, dst, deg = _graph_tensors(s, torch)
    with torch.no_grad():
        beklenen = module(X, src, dst, deg).numpy()
    alinan = NumpyMeshGNN.from_npz(weights_to_numpy(module)).forward(s.node_inputs, s.edges)
    assert alinan == pytest.approx(beklenen, rel=1e-12)


# --- gerçekten öğreniyor mu ----------------------------------------------------


@torch_gerekli
def test_kayip_duser(samples):
    """Eski `sgd_process` encoder'ı hiç güncellemiyordu — bu testin
    varlık sebebi: kayıp gerçekten iniyor mu."""
    _, hist = train_torch_gnn(samples, epochs=30, hidden=12)
    assert hist.train[-1] < hist.train[0] * 0.8


@torch_gerekli
def test_encoder_gercekten_guncelleniyor(samples):
    """Asıl kusur buydu: W_enc sabit rastgele projeksiyon olarak kalıyordu."""
    ilk = weights_to_numpy(build_module(14, 12, 4, 2, seed=2026))["W_enc"]
    egitilmis, _ = train_torch_gnn(samples, epochs=10, hidden=12, seed=2026)
    assert not np.allclose(ilk, egitilmis["W_enc"])


@torch_gerekli
def test_en_iyi_tur_geri_yuklenir(samples):
    """Doğrulama kaybı yükselirken son tur değil, EN İYİ tur kaydedilmeli."""
    _, hist = train_torch_gnn(samples[:10], samples[10:], epochs=60, hidden=8, patience=5)
    assert hist.holdout
    assert hist.holdout[hist.best_epoch] == pytest.approx(min(hist.holdout))


@torch_gerekli
def test_asiri_ogrenmede_erken_durur(samples):
    """Doğrulama kaybı iyileşmeyi bırakınca durmalı. Senaryo: holdout
    eğitimle ÇELİŞEN hedefler taşıyor — eğitim iyileştikçe holdout kötüleşir."""
    celiskili = []
    for s in samples[10:]:
        kopya = GraphSample(
            run_id=s.run_id, node_inputs=s.node_inputs,
            node_outputs=-3.0 * s.node_outputs, edges=s.edges,
            node_ids=s.node_ids, edge_source=s.edge_source,
        )
        celiskili.append(kopya)

    _, hist = train_torch_gnn(samples[:10], celiskili, epochs=500, hidden=8, patience=3)

    assert hist.stopped_early
    assert len(hist.train) < 500
    assert hist.best_epoch < len(hist.train) - 1


def test_ciktisiz_ornek_reddedilir():
    s = _sample(0)
    s.node_outputs = None
    if not torch_available():
        pytest.skip("torch kurulu değil")
    with pytest.raises(ValueError):
        train_torch_gnn([s], epochs=1)


# --- motor seçimi --------------------------------------------------------------


def test_bilinmeyen_motor_reddedilir(samples):
    with pytest.raises(ValueError, match="engine"):
        train_gnn(samples, engine="tensorflow")


def test_numpy_motoru_hala_calisir(samples):
    """torch yoksa eski yol kullanılabilir olmalı — ama raporda görünür."""
    bundle = train_gnn(samples, engine="numpy")
    assert bundle["metrics"]["engine"] == "numpy"


@torch_gerekli
def test_auto_torchu_secer(samples):
    assert train_gnn(samples, epochs=3)["metrics"]["engine"] == "torch"


def test_torch_yoksa_acik_hata(monkeypatch):
    monkeypatch.setattr("app.ml.gnn_torch.torch_available", lambda: False)
    import app.ml.gnn_torch as gt

    def patlat():
        raise TorchUnavailable("yok")

    monkeypatch.setattr(gt, "_torch", patlat)
    with pytest.raises(TorchUnavailable):
        train_torch_gnn([_sample(0)], epochs=1)


# --- holdout -------------------------------------------------------------------


def test_holdout_bolunur(samples):
    train, holdout = split_holdout(samples, 0.3, seed=1)
    assert len(holdout) == 4
    assert len(train) == len(samples) - 4
    assert {s.run_id for s in train}.isdisjoint({s.run_id for s in holdout})


def test_az_ornekte_holdout_yok():
    """Az örnekle ayrılan holdout hem eğitimi zayıflatır hem ölçmediği bir
    sayıyı 'test hatası' diye sunar."""
    az = [_sample(i) for i in range(5)]
    train, holdout = split_holdout(az, 0.2, seed=1)
    assert holdout == []
    assert len(train) == 5


def test_holdout_metrigi_ayri_alanda(samples):
    bundle = train_gnn(samples, engine="numpy", holdout_fraction=0.3)
    m = bundle["metrics"]
    assert m["n_holdout"] >= MIN_HOLDOUT_GRAPHS
    assert m["holdout"]["node_rmse"]["u_y"] > 0
    assert m["n_train"] + m["n_holdout"] == len(samples)


def test_holdout_yoksa_none(samples):
    m = train_gnn(samples[:5], engine="numpy")["metrics"]
    assert m["holdout"] is None, "'yok' ile 'sıfır' karışmamalı"
    assert m["n_holdout"] == 0
