"""GNN ölçeklemeyi uçtan uca taşıyor mu (TODO 1.2).

KRİTİK: ölçek eğitimde çıkarılır ama TAHMİNDE uygulanmazsa model sessizce
saçmalar — hata vermez, sadece yanlış sayı döner. Bu yüzden kaydet/yükle
gidiş-dönüşü ve fiziksel birim sınanır.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.dataset.training_data import NODE_OUTPUT_CHANNELS
from app.ml.gnn import load_gnn, predict_field, save_gnn, train_gnn
from app.ml.graph_data import GraphSample
from app.ml.normalization import ChannelScaler


def _sample(seed: int, n: int = 30) -> GraphSample:
    """Ham ölçekli örnek: koordinat 0…500, E 210000, yoğunluk 7.85e−9."""
    rng = np.random.default_rng(seed)
    X = np.zeros((n, 14), dtype=np.float32)
    X[:, 0] = np.linspace(0, 500, n)          # x
    X[:, 1] = rng.uniform(0, 10, n)           # y
    X[:, 2] = rng.uniform(0, 50, n)           # z
    X[:3, 3:6] = 1.0                          # ankastre uç
    X[-1, 8] = -500.0                         # uç yükü
    X[:, 10] = 210000.0                       # E
    X[:, 11] = 0.3
    X[:, 12] = 7.85e-9
    Y = np.zeros((n, 4), dtype=np.float32)
    Y[:, 1] = -0.02 * (X[:, 0] ** 2) / 500.0 * (1 + 0.1 * seed)   # u_y, mm
    Y[:, 3] = 120.0 * (1 - X[:, 0] / 500.0) * (1 + 0.1 * seed)    # von Mises, MPa
    edges = np.stack([np.arange(n - 1), np.arange(1, n)], axis=1).astype(np.int32)
    return GraphSample(
        run_id=seed, node_inputs=X, node_outputs=Y, edges=edges,
        node_ids=np.arange(1, n + 1, dtype=np.int32), edge_source="mesh",
    )


@pytest.fixture()
def samples():
    return [_sample(i) for i in range(4)]


# --- eğitim ölçeği çıkarıyor mu ------------------------------------------------


def test_egitim_olcegi_cikarir_ve_saklar(samples):
    bundle = train_gnn(samples, sgd_steps=1)

    assert isinstance(bundle["x_scaler"], ChannelScaler)
    assert isinstance(bundle["y_scaler"], ChannelScaler)
    ozet = bundle["normalization"]["inputs"]
    assert ozet["youngs_modulus_mpa"]["constant"] is True, "tek malzeme: sabit"
    assert ozet["x"]["scale"] > 1.0


def test_koordinat_grubu_ortak_olcek(samples):
    ozet = train_gnn(samples, sgd_steps=1)["normalization"]["inputs"]
    assert ozet["x"]["scale"] == pytest.approx(ozet["y"]["scale"])
    assert ozet["y"]["scale"] == pytest.approx(ozet["z"]["scale"])


def test_metrikler_fiziksel_birimde(samples):
    """Ölçekli uzayda hesaplanırsa RMSE mm/MPa olmaktan çıkar ve eski
    ölçümlerle karşılaştırılamaz."""
    bundle = train_gnn(samples, sgd_steps=1)
    vm = bundle["metrics"]["node_rmse"]["von_mises_mpa"]
    hedef = np.vstack([s.node_outputs for s in samples])[:, 3]
    assert vm < float(hedef.std()) * 5, "MPa mertebesinde olmalı"
    assert vm > 0


# --- tahmin --------------------------------------------------------------------


def test_tahmin_fiziksel_birim_dondurur(samples):
    """Ham girdi verilir, mm/MPa alınır — ölçek çağıranı ilgilendirmez."""
    bundle = train_gnn(samples, sgd_steps=1)
    pred = predict_field(bundle, samples[0])

    assert pred.shape == (samples[0].node_inputs.shape[0], len(NODE_OUTPUT_CHANNELS))
    # von Mises 0…200 MPa bandında; ölçekli uzayda kalsaydı ±3 çıkardı
    assert 10.0 < float(np.abs(pred[:, 3]).max()) < 400.0


def test_kaydet_yukle_ayni_tahmini_verir(samples, tmp_path):
    bundle = train_gnn(samples, sgd_steps=1)
    once = predict_field(bundle, samples[1])

    save_gnn(bundle, tmp_path / "field_gnn.npz")
    geri = load_gnn(tmp_path / "field_gnn.npz")

    assert geri is not None
    assert geri["x_scaler"].scale == pytest.approx(bundle["x_scaler"].scale)
    assert predict_field(geri, samples[1]) == pytest.approx(once, rel=1e-9)


def test_olceksiz_eski_model_okunabilir(samples, tmp_path):
    """Ölçek anahtarları olmayan eski dosya birim ölçekle yüklenmeli."""
    bundle = train_gnn(samples, sgd_steps=1)
    path = tmp_path / "eski.npz"
    save_gnn(bundle, path)
    with np.load(path, allow_pickle=False) as z:
        data = {k: z[k] for k in z.files if not k.startswith(("x_", "y_"))}
    np.savez_compressed(path, **data)

    geri = load_gnn(path)

    assert geri is not None
    assert geri["x_scaler"].scale == pytest.approx(np.ones(14))
    assert predict_field(geri, samples[0]).shape[1] == len(NODE_OUTPUT_CHANNELS)


def test_olcek_uygulanmazsa_sonuc_farkli(samples):
    """Ölçeği atlamak sessiz bir hata olurdu; fark ölçülebilir olmalı."""
    bundle = train_gnn(samples, sgd_steps=1)
    dogru = predict_field(bundle, samples[0])
    ham = bundle["model"].forward(samples[0].node_inputs, samples[0].edges)
    assert not np.allclose(dogru, ham)
