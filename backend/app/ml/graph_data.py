"""Mesh-graf örnekleri `.train.npz`'den (0.5.7).

Eleman boyutu parametre olduğu için düğüm sayısı run'dan run'a değişir;
örnek bir graftır. Connectivity boşsa (eski dosyalar) koordinattan k-NN.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from app.dataset.training_data import NODE_INPUT_CHANNELS, NODE_OUTPUT_CHANNELS


@dataclass
class GraphSample:
    run_id: int | None
    node_inputs: np.ndarray
    node_outputs: np.ndarray | None
    edges: np.ndarray  # (E, 2) int32, 0-based
    node_ids: np.ndarray
    element_size: float | None = None


#: kNN mesafe bloğu: satır sayısı × n float64 tutulur (n=40k'da ~330 MB).
KNN_BLOCK = 1024


def _knn_indices(coords: np.ndarray, k: int) -> np.ndarray:
    """Her düğüm için en yakın k komşunun indeksi (kendisi hariç).

    Tam (n, n) mesafe matrisi kurulmaz: 40k düğümlü bir mesh'te bu 36 GiB
    istiyordu ve `/surrogate/gnn/train` bellek hatasıyla düşüyordu.
    """
    try:
        from sklearn.neighbors import KDTree
    except ImportError:  # pragma: no cover - sklearn zaten bağımlılık
        KDTree = None

    if KDTree is not None:
        tree = KDTree(coords)
        idx = tree.query(coords, k=k + 1, return_distance=False)
        return np.asarray(idx[:, 1:], dtype=np.int64)

    n = coords.shape[0]
    sq = (coords**2).sum(axis=1)
    out = np.empty((n, k), dtype=np.int64)
    for start in range(0, n, KNN_BLOCK):
        stop = min(start + KNN_BLOCK, n)
        block = coords[start:stop]
        d2 = sq[None, :] + (block**2).sum(axis=1)[:, None] - 2.0 * (block @ coords.T)
        rows = np.arange(stop - start)
        d2[rows, np.arange(start, stop)] = np.inf
        out[start:stop] = np.argpartition(d2, kth=k - 1, axis=1)[:, :k]
    return out


def knn_edges(coords: np.ndarray, k: int = 6) -> np.ndarray:
    n = coords.shape[0]
    if n <= 1:
        return np.zeros((0, 2), dtype=np.int32)
    k = min(k, n - 1)
    nn = _knn_indices(np.asarray(coords, dtype=np.float64), k)
    rows = np.repeat(np.arange(n, dtype=np.int64), nn.shape[1])
    cols = nn.reshape(-1)
    a = np.minimum(rows, cols)
    b = np.maximum(rows, cols)
    keep = a != b
    if not np.any(keep):
        return np.zeros((0, 2), dtype=np.int32)
    pairs = np.unique(np.stack([a[keep], b[keep]], axis=1), axis=0)
    return pairs.astype(np.int32)


def edges_from_connectivity(conn: np.ndarray, n_nodes: int) -> np.ndarray:
    if conn is None or conn.size == 0:
        return np.zeros((0, 2), dtype=np.int32)
    edges: set[tuple[int, int]] = set()
    for elem in np.asarray(conn):
        nodes = [int(v) for v in elem if int(v) >= 0]
        # 1-based mesh ids → 0-based; if already 0-based max < n_nodes
        if nodes and min(nodes) >= 1 and max(nodes) <= n_nodes:
            nodes = [v - 1 for v in nodes]
        for a_i in range(len(nodes)):
            for b_i in range(a_i + 1, len(nodes)):
                a, b = nodes[a_i], nodes[b_i]
                if not (0 <= a < n_nodes and 0 <= b < n_nodes):
                    continue
                if a > b:
                    a, b = b, a
                edges.add((a, b))
    if not edges:
        return np.zeros((0, 2), dtype=np.int32)
    return np.asarray(sorted(edges), dtype=np.int32)


def load_graph(path: Path, *, run_id: int | None = None) -> GraphSample | None:
    if not path.is_file():
        return None
    with np.load(path, allow_pickle=False) as z:
        analysis = str(z["analysis_type"]) if "analysis_type" in z.files else "static"
        if analysis == "modal":
            return None
        X = np.asarray(z["node_inputs"], dtype=np.float64)
        Y = np.asarray(z["node_outputs"], dtype=np.float64) if "node_outputs" in z.files else None
        conn = z["connectivity"] if "connectivity" in z.files else np.zeros((0, 0), np.int32)
        node_ids = (
            np.asarray(z["node_ids"], dtype=np.int32)
            if "node_ids" in z.files
            else np.arange(1, X.shape[0] + 1, dtype=np.int32)
        )
    n = X.shape[0]
    edges = edges_from_connectivity(conn, n)
    if edges.shape[0] == 0:
        coords = X[:, :3]
        edges = knn_edges(coords, k=6)
    return GraphSample(
        run_id=run_id,
        node_inputs=X,
        node_outputs=Y,
        edges=edges,
        node_ids=node_ids,
    )


def iter_training_graphs(runs_root: Path) -> Iterator[GraphSample]:
    if not runs_root.is_dir():
        return
    for npz in sorted(runs_root.glob("*/*.train.npz")):
        rid = None
        try:
            rid = int(npz.parent.name)
        except ValueError:
            rid = None
        sample = load_graph(npz, run_id=rid)
        if sample is None or sample.node_outputs is None:
            continue
        yield sample


assert len(NODE_INPUT_CHANNELS) == 14
assert len(NODE_OUTPUT_CHANNELS) == 4
