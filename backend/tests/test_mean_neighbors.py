"""Komşu ortalaması vektörleştirildi (TODO 1.3a).

NEDEN: mesaj geçişinin çekirdeği kenarlar üzerinde Python döngüsüydü;
28k düğümlü bir grafta çağrı başına 247 ms. Eğitim ve her A/B ölçümü bunu
yüzlerce kez çağırıyor. Vektör hâli 17 ms — ama sonuç DEĞİŞMEMELİ, bu
yüzden referans uygulama testte duruyor.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.gnn import _FLAT_INDEX_LIMIT, _mean_neighbors


def referans(h: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Eski döngülü uygulama — doğruluk ölçütü."""
    n = h.shape[0]
    agg = np.zeros_like(h)
    deg = np.zeros((n, 1), dtype=np.float64)
    if edges.size == 0:
        return agg
    for a, b in edges:
        agg[a] += h[b]
        agg[b] += h[a]
        deg[a] += 1.0
        deg[b] += 1.0
    return agg / np.maximum(deg, 1.0)


def _rastgele_graf(n, e, d, seed=0):
    rng = np.random.default_rng(seed)
    h = rng.normal(size=(n, d))
    edges = np.unique(np.sort(rng.integers(0, n, size=(e, 2)), axis=1), axis=0)
    edges = edges[edges[:, 0] != edges[:, 1]].astype(np.int32)
    return h, edges


@pytest.mark.parametrize("n,e,d", [(12, 20, 3), (200, 500, 8), (900, 2400, 24)])
def test_eski_uygulamayla_ayni(n, e, d):
    h, edges = _rastgele_graf(n, e, d)
    assert _mean_neighbors(h, edges) == pytest.approx(referans(h, edges), abs=1e-12)


def test_sutun_yolu_da_ayni(monkeypatch):
    """Bellek sınırı aşılınca sütun sütun toplanıyor; sonuç değişmemeli."""
    h, edges = _rastgele_graf(300, 800, 6, seed=3)
    monkeypatch.setattr("app.ml.gnn._FLAT_INDEX_LIMIT", 1)
    assert _mean_neighbors(h, edges) == pytest.approx(referans(h, edges), abs=1e-12)


def test_kenarsiz_graf_sifir():
    h = np.ones((5, 3))
    out = _mean_neighbors(h, np.zeros((0, 2), dtype=np.int32))
    assert out.shape == (5, 3)
    assert np.all(out == 0.0)


def test_bagsiz_dugum_sifir_kalir():
    """Derecesi sıfır olan düğüm sıfıra bölünmemeli."""
    h = np.array([[1.0], [2.0], [9.0]])
    out = _mean_neighbors(h, np.array([[0, 1]], dtype=np.int32))
    assert out[2, 0] == 0.0
    assert out[0, 0] == 2.0 and out[1, 0] == 1.0


def test_ortalama_gercekten_ortalama():
    """Üç komşusu olan düğüm komşularının ortalamasını görmeli."""
    h = np.array([[0.0], [3.0], [6.0], [9.0]])
    edges = np.array([[0, 1], [0, 2], [0, 3]], dtype=np.int32)
    out = _mean_neighbors(h, edges)
    assert out[0, 0] == pytest.approx(6.0)
    assert out[1, 0] == pytest.approx(0.0)


def test_kenar_yonu_onemsiz():
    """Graf yönsüz: (a,b) ile (b,a) aynı sonucu vermeli."""
    h, edges = _rastgele_graf(50, 120, 4, seed=7)
    ters = edges[:, ::-1].copy()
    assert _mean_neighbors(h, edges) == pytest.approx(_mean_neighbors(h, ters))


def test_sinir_degeri_makul():
    assert _FLAT_INDEX_LIMIT >= 1_000_000
