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
    #: "mesh" = eleman bağlantısından, "knn" = koordinat komşuluğundan
    #: (bağlantı yazılmamış eski dosyalar). Eğitim raporunda gösterilir:
    #: k-NN grafı mesh grafı DEĞİLDİR, aynı sayılmamalı.
    edge_source: str = "knn"


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


#: Eleman tipi -> yerel kenar listesi (0-based, CalculiX düğüm sırası).
#: Kliğin (tüm düğüm çiftleri) yerine GERÇEK eleman kenarları: C3D10'da
#: klik 45 kenar üretir ve karşılıklı kenar-ortası düğümleri birbirine
#: bağlar — mesh'te böyle bir komşuluk yoktur.
ELEMENT_EDGES: dict[str, tuple[tuple[int, int], ...]] = {
    "C3D4": ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)),
    # Kenar-ortası düğümler köşeleri ikiye böler: köşe-orta-köşe.
    "C3D10": (
        (0, 4), (4, 1), (1, 5), (5, 2), (2, 6), (6, 0),
        (0, 7), (7, 3), (1, 8), (8, 3), (2, 9), (9, 3),
    ),
    "C3D8": (
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ),
    "S3": ((0, 1), (1, 2), (2, 0)),
    "S4": ((0, 1), (1, 2), (2, 3), (3, 0)),
}


def _clique_edges(block: np.ndarray) -> np.ndarray:
    """Tipi bilinmeyen eleman: tüm düğüm çiftleri (eski davranış)."""
    width = block.shape[1]
    pairs = [(a, b) for a in range(width) for b in range(a + 1, width)]
    if not pairs:
        return np.zeros((0, 2), dtype=np.int64)
    local = np.asarray(pairs, dtype=np.int64)
    return np.stack([block[:, local[:, 0]].ravel(), block[:, local[:, 1]].ravel()], axis=1)


def edges_from_connectivity(
    conn: np.ndarray,
    n_nodes: int,
    element_types: np.ndarray | list[str] | None = None,
) -> np.ndarray:
    """Eleman bağlantısından benzersiz, yönsüz graf kenarları.

    `element_types` verilirse her eleman kendi kenar tablosuyla açılır;
    verilmezse (eski `.npz` dosyaları) klik davranışına düşer.
    """
    if conn is None:
        return np.zeros((0, 2), dtype=np.int32)
    conn = np.asarray(conn)
    if conn.size == 0 or conn.ndim != 2:
        return np.zeros((0, 2), dtype=np.int32)

    valid = conn >= 0
    if not valid.any():
        return np.zeros((0, 2), dtype=np.int32)
    # Düğüm numaraları 1-based yazılır (`.inp` sırası); 0-based diziye çevir.
    if conn[valid].min() >= 1 and conn[valid].max() <= n_nodes:
        conn = np.where(valid, conn - 1, conn)

    types = (
        np.asarray(element_types, dtype="<U8")
        if element_types is not None and len(element_types) == conn.shape[0]
        else None
    )

    chunks: list[np.ndarray] = []
    if types is None:
        chunks.append(_clique_edges(conn))
    else:
        for etype in np.unique(types):
            block = conn[types == etype]
            table = ELEMENT_EDGES.get(str(etype))
            if table is None:
                chunks.append(_clique_edges(block))
                continue
            local = np.asarray(table, dtype=np.int64)
            width = block.shape[1]
            local = local[(local[:, 0] < width) & (local[:, 1] < width)]
            if local.size == 0:
                continue
            chunks.append(
                np.stack(
                    [block[:, local[:, 0]].ravel(), block[:, local[:, 1]].ravel()],
                    axis=1,
                )
            )

    if not chunks:
        return np.zeros((0, 2), dtype=np.int32)
    raw = np.concatenate(chunks, axis=0)
    a = np.minimum(raw[:, 0], raw[:, 1])
    b = np.maximum(raw[:, 0], raw[:, 1])
    keep = (a != b) & (a >= 0) & (b < n_nodes)
    if not keep.any():
        return np.zeros((0, 2), dtype=np.int32)
    pairs = np.unique(np.stack([a[keep], b[keep]], axis=1), axis=0)
    return pairs.astype(np.int32)


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
        etypes = z["element_types"] if "element_types" in z.files else None
        node_ids = (
            np.asarray(z["node_ids"], dtype=np.int32)
            if "node_ids" in z.files
            else np.arange(1, X.shape[0] + 1, dtype=np.int32)
        )
    n = X.shape[0]
    edges = edges_from_connectivity(conn, n, etypes)
    source = "mesh"
    if edges.shape[0] == 0:
        coords = X[:, :3]
        edges = knn_edges(coords, k=6)
        source = "knn"
    return GraphSample(
        run_id=run_id,
        node_inputs=X,
        node_outputs=Y,
        edges=edges,
        node_ids=node_ids,
        edge_source=source,
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
