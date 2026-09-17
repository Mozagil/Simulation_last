"""knn_edges bellek güvenliği (0.5.7 regresyon).

Eski `.train.npz` dosyalarında connectivity boş olduğu için graf kenarları
koordinatlardan kuruluyor. Tam (n, n) mesafe matrisi 40k düğümde 36 GiB
isteyip `/surrogate/gnn/train`'i düşürmüştü.
"""

from __future__ import annotations

import numpy as np

from app.ml.graph_data import _knn_indices, knn_edges


def _brute_force_edges(coords: np.ndarray, k: int) -> set[tuple[int, int]]:
    n = coords.shape[0]
    k = min(k, n - 1)
    d2 = ((coords[:, None, :] - coords[None, :, :]) ** 2).sum(axis=2)
    np.fill_diagonal(d2, np.inf)
    nn = np.argpartition(d2, kth=k - 1, axis=1)[:, :k]
    edges: set[tuple[int, int]] = set()
    for i in range(n):
        for j in nn[i]:
            a, b = (int(i), int(j)) if i < int(j) else (int(j), int(i))
            if a != b:
                edges.add((a, b))
    return edges


def test_knn_edges_matches_brute_force_on_random_cloud():
    rng = np.random.default_rng(3)
    coords = rng.uniform(0.0, 50.0, size=(120, 3))
    edges = knn_edges(coords, k=6)
    assert set(map(tuple, edges.tolist())) == _brute_force_edges(coords, 6)


def test_knn_edges_line_is_sorted_and_symmetric_free():
    coords = np.array([[0.0, 0, 0], [1.0, 0, 0], [2.0, 0, 0], [3.0, 0, 0]])
    edges = knn_edges(coords, k=2)
    assert edges.dtype == np.int32
    assert (edges[:, 0] < edges[:, 1]).all()
    lex = np.lexsort((edges[:, 1], edges[:, 0]))
    assert (lex == np.arange(edges.shape[0])).all()


def test_knn_edges_handles_degenerate_sizes():
    assert knn_edges(np.zeros((0, 3)), k=6).shape == (0, 2)
    assert knn_edges(np.zeros((1, 3)), k=6).shape == (0, 2)
    assert knn_edges(np.array([[0.0, 0, 0], [1.0, 0, 0]]), k=6).shape == (1, 2)


def test_knn_edges_large_cloud_stays_within_memory():
    rng = np.random.default_rng(7)
    coords = rng.uniform(0.0, 100.0, size=(40_000, 3))
    edges = knn_edges(coords, k=6)
    assert edges.shape[0] > 40_000
    assert edges[:, 1].max() < 40_000


def test_blocked_fallback_matches_kdtree(monkeypatch):
    rng = np.random.default_rng(11)
    coords = rng.uniform(0.0, 10.0, size=(200, 3))
    ref = _knn_indices(coords, 6)

    import builtins

    real_import = builtins.__import__

    def no_sklearn(name, *args, **kwargs):
        if name.startswith("sklearn"):
            raise ImportError("sklearn devre dışı")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_sklearn)
    blocked = _knn_indices(coords, 6)
    assert [set(row) for row in blocked.tolist()] == [set(row) for row in ref.tolist()]
