"""MeshGraphNet-benzeri encode-process-decode, NumPy (0.5.7).

PyTorch Geometric bilinçli olarak eklenmedi: Codespace imajı torch ile
disk dolduruyordu. Aynı şema (düğüm girdi/çıktı + kenar) korunur; GPU
eğitimi ayrı bir bağımlılık kararı.

Eğitim: son katman en küçük kareler, process katmanları birkaç SGD adımı.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.dataset.training_data import (
    NODE_INPUT_CHANNELS,
    NODE_INPUT_GROUPS,
    NODE_OUTPUT_CHANNELS,
    NODE_OUTPUT_GROUPS,
    channel_group_indices,
)
from app.ml.graph_data import GraphSample
from app.ml.gnn_torch import DEFAULT_PATIENCE, torch_available, train_torch_gnn
from app.ml.normalization import ChannelScaler
from app.ml.ood import bounds_from_matrix

DEFAULT_GNN_PATH = Path("uploads") / "models" / "field_gnn.npz"


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)


#: Düzleştirilmiş indeks dizisinin üst sınırı (öğe sayısı). Aşılırsa
#: sütun sütun toplanır: geçici dizi 2·kenar·gizli boyutunda büyüyor ve
#: gizli katman genişledikçe (1.3'te 64+) belleği zorluyor.
_FLAT_INDEX_LIMIT = 8_000_000


def _mean_neighbors(h: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Komşu ortalaması — mesaj geçişinin çekirdeği.

    Eskiden kenarlar üzerinde Python döngüsüydü; eğitim ve her ölçüm turu
    bu yüzden dakikalar sürüyordu. Ölçüldü (gizli=24, 3 tekrar ortalaması):

    | graf | döngü | vektör |
    |---|---|---|
    | 500 düğüm / 0.9k kenar | 4.44 ms | 0.43 ms |
    | 9k düğüm / 15k kenar | 81.0 ms | 5.41 ms |
    | 28k düğüm / 47k kenar | 246.9 ms | 17.3 ms |

    Sonuç 6.7e−16'ya kadar aynı (yalnız kayan nokta toplama sırası farklı).
    """
    n, d = h.shape
    if edges.size == 0:
        return np.zeros_like(h)

    # Yönsüz kenar: her iki yönde de taşınır.
    src = np.concatenate([edges[:, 0], edges[:, 1]]).astype(np.intp)
    dst = np.concatenate([edges[:, 1], edges[:, 0]]).astype(np.intp)
    gathered = np.asarray(h, dtype=np.float64)[dst]

    if src.shape[0] * d <= _FLAT_INDEX_LIMIT:
        idx = (src[:, None] * d + np.arange(d)[None, :]).ravel()
        agg = np.bincount(idx, weights=gathered.ravel(), minlength=n * d).reshape(n, d)
    else:
        agg = np.empty((n, d), dtype=np.float64)
        for j in range(d):
            agg[:, j] = np.bincount(src, weights=gathered[:, j], minlength=n)

    deg = np.bincount(src, minlength=n).astype(np.float64)
    return agg / np.maximum(deg, 1.0)[:, None]


class NumpyMeshGNN:
    def __init__(self, in_dim: int, hidden: int = 24, n_proc: int = 2, out_dim: int = 4, seed: int = 0):
        rng = np.random.default_rng(seed)
        scale = 0.15
        self.W_enc = rng.normal(0.0, scale, (in_dim, hidden))
        self.b_enc = np.zeros(hidden)
        self.W_self = rng.normal(0.0, scale, (hidden, hidden))
        self.W_nei = rng.normal(0.0, scale, (hidden, hidden))
        self.b_proc = np.zeros(hidden)
        self.W_out = rng.normal(0.0, scale, (hidden, out_dim))
        self.b_out = np.zeros(out_dim)
        self.n_proc = n_proc
        self.hidden = hidden

    def encode(self, X: np.ndarray) -> np.ndarray:
        return _relu(X @ self.W_enc + self.b_enc)

    def process(self, h: np.ndarray, edges: np.ndarray) -> np.ndarray:
        for _ in range(self.n_proc):
            agg = _mean_neighbors(h, edges)
            h = _relu(h @ self.W_self + agg @ self.W_nei + self.b_proc)
        return h

    def hidden_states(self, X: np.ndarray, edges: np.ndarray) -> np.ndarray:
        return self.process(self.encode(X), edges)

    def forward(self, X: np.ndarray, edges: np.ndarray) -> np.ndarray:
        h = self.hidden_states(X, edges)
        return h @ self.W_out + self.b_out

    def fit_output_ls(self, samples: list[GraphSample]) -> None:
        hs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        for s in samples:
            if s.node_outputs is None:
                continue
            hs.append(self.hidden_states(s.node_inputs, s.edges))
            ys.append(s.node_outputs)
        if not hs:
            raise ValueError("GNN eğitimi için düğüm çıktılı örnek yok.")
        H = np.vstack(hs)
        Y = np.vstack(ys)
        ones = np.ones((H.shape[0], 1))
        A = np.hstack([H, ones])
        wb, *_ = np.linalg.lstsq(A, Y, rcond=None)
        self.W_out = wb[:-1]
        self.b_out = wb[-1]

    def sgd_process(self, samples: list[GraphSample], *, steps: int = 8, lr: float = 1e-4) -> None:
        """Process ağırlıklarına kaba gradyan (son katman donuk)."""
        for _ in range(steps):
            d_self = np.zeros_like(self.W_self)
            d_nei = np.zeros_like(self.W_nei)
            n_used = 0
            for s in samples:
                if s.node_outputs is None:
                    continue
                h0 = self.encode(s.node_inputs)
                pred = self.forward(s.node_inputs, s.edges)
                err = pred - s.node_outputs
                # ∂L/∂h_last ≈ err @ W_out.T
                g_h = err @ self.W_out.T
                agg = _mean_neighbors(h0, s.edges)
                # tek process adımı yaklaşığı
                d_self += h0.T @ g_h
                d_nei += agg.T @ g_h
                n_used += 1
            if n_used == 0:
                return
            self.W_self -= lr * d_self / n_used
            self.W_nei -= lr * d_nei / n_used
            self.fit_output_ls(samples)

    def to_npz(self) -> dict[str, np.ndarray]:
        return {
            "W_enc": self.W_enc,
            "b_enc": self.b_enc,
            "W_self": self.W_self,
            "W_nei": self.W_nei,
            "b_proc": self.b_proc,
            "W_out": self.W_out,
            "b_out": self.b_out,
            "n_proc": np.int32(self.n_proc),
        }

    @classmethod
    def from_npz(cls, data: dict[str, np.ndarray]) -> "NumpyMeshGNN":
        model = cls(
            in_dim=int(data["W_enc"].shape[0]),
            hidden=int(data["W_enc"].shape[1]),
            n_proc=int(data["n_proc"]),
            out_dim=int(data["W_out"].shape[1]),
        )
        for key in ("W_enc", "b_enc", "W_self", "W_nei", "b_proc", "W_out", "b_out"):
            setattr(model, key, np.asarray(data[key], dtype=np.float64))
        return model


def normalized_samples(
    samples: list[GraphSample], x_scaler: ChannelScaler, y_scaler: ChannelScaler
) -> list[GraphSample]:
    """Girdi/çıktısı ölçeklenmiş kopyalar; graf yapısı paylaşılır."""
    out: list[GraphSample] = []
    for s in samples:
        out.append(
            GraphSample(
                run_id=s.run_id,
                node_inputs=x_scaler.transform(s.node_inputs).astype(np.float32),
                node_outputs=(
                    None
                    if s.node_outputs is None
                    else y_scaler.transform(s.node_outputs).astype(np.float32)
                ),
                edges=s.edges,
                node_ids=s.node_ids,
                element_size=s.element_size,
                edge_source=s.edge_source,
            )
        )
    return out


def predict_physical(
    model: NumpyMeshGNN,
    sample: GraphSample,
    x_scaler: ChannelScaler,
    y_scaler: ChannelScaler,
) -> np.ndarray:
    """HAM girdiden fiziksel birimli tahmin (mm, MPa).

    Ölçekleme yalnız modelin içinde kalır: çağıranlar her zaman fiziksel
    birim görür, metrikler eski ölçümlerle karşılaştırılabilir kalır.
    """
    z = model.forward(x_scaler.transform(sample.node_inputs), sample.edges)
    return y_scaler.inverse_transform(z)


def _field_rmse(
    samples: list[GraphSample],
    model: NumpyMeshGNN,
    x_scaler: ChannelScaler | None = None,
    y_scaler: ChannelScaler | None = None,
) -> dict[str, Any]:
    """Hata metrikleri FİZİKSEL birimde (mm, MPa) — `samples` ham olmalı."""
    n_in = samples[0].node_inputs.shape[1] if samples else 0
    n_out = len(NODE_OUTPUT_CHANNELS)
    x_scaler = x_scaler or ChannelScaler.identity(n_in)
    y_scaler = y_scaler or ChannelScaler.identity(n_out)
    sq = np.zeros(len(NODE_OUTPUT_CHANNELS))
    n = 0
    scalar_sq = np.zeros(2)
    n_graphs = 0
    by_size: dict[str, list[float]] = {}
    for s in samples:
        if s.node_outputs is None:
            continue
        pred = predict_physical(model, s, x_scaler, y_scaler)
        y = s.node_outputs
        diff = pred - y
        sq += (diff ** 2).mean(axis=0)
        n += 1
        n_graphs += 1
        mag_t = np.linalg.norm(y[:, :3], axis=1)
        mag_p = np.linalg.norm(pred[:, :3], axis=1)
        scalar_sq[0] += (float(mag_t.max()) - float(mag_p.max())) ** 2
        scalar_sq[1] += (float(y[:, 3].max()) - float(pred[:, 3].max())) ** 2
        key = "unknown" if s.element_size is None else f"{s.element_size:.1f}"
        node_rmse = float(np.sqrt((diff ** 2).mean()))
        by_size.setdefault(key, []).append(node_rmse)
    if n == 0:
        return {}
    per_ch = {
        name: float(np.sqrt(sq[i] / n))
        for i, name in enumerate(NODE_OUTPUT_CHANNELS)
    }
    size_rmse = {k: float(np.mean(v)) for k, v in sorted(by_size.items())}
    return {
        "n_graphs": n_graphs,
        "node_rmse": per_ch,
        "scalar_rmse": {
            "max_displacement": float(np.sqrt(scalar_sq[0] / n_graphs)),
            "max_von_mises": float(np.sqrt(scalar_sq[1] / n_graphs)),
        },
        "rmse_by_element_size": size_rmse,
    }


#: Bu sayıdan az doğrulama grafı anlamlı bir holdout metriği vermez —
#: skaler modellerdeki `MIN_HOLDOUT_SAMPLES` ile aynı gerekçe: az örnekle
#: hesaplanan "test hatası" güven verir ama ölçmez.
MIN_HOLDOUT_GRAPHS = 4
DEFAULT_HOLDOUT_FRACTION = 0.2


def split_holdout(
    samples: list[GraphSample], fraction: float, seed: int
) -> tuple[list[GraphSample], list[GraphSample]]:
    """(eğitim, holdout). Yeterli örnek yoksa holdout BOŞ döner.

    Örnek sayısı azken holdout ayırmak iki kötülüğü birden yapar: eğitimi
    zayıflatır ve ölçemediği bir sayıyı "test hatası" diye sunar.
    """
    n_holdout = int(round(len(samples) * fraction))
    if n_holdout < MIN_HOLDOUT_GRAPHS or len(samples) - n_holdout < MIN_HOLDOUT_GRAPHS:
        return list(samples), []
    order = np.random.default_rng(seed).permutation(len(samples))
    idx = [int(i) for i in order]
    holdout = [samples[i] for i in idx[:n_holdout]]
    train = [samples[i] for i in idx[n_holdout:]]
    return train, holdout


def train_gnn(
    samples: list[GraphSample],
    *,
    seed: int = 2026,
    hidden: int = 24,
    n_proc: int = 2,
    sgd_steps: int = 6,
    engine: str = "auto",
    epochs: int = 200,
    lr: float = 1e-3,
    patience: int = DEFAULT_PATIENCE,
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
) -> dict[str, Any]:
    """`engine`: "torch" (gerçek geri yayılım) | "numpy" (eski, en küçük
    kareler + kaba gradyan) | "auto" (torch varsa torch).

    Hangi motorun kullanıldığı `metrics["engine"]` ile raporlanır: "numpy"
    çıktısı bir EĞİTİM DEĞİLDİR, encoder donuk kalır.
    """
    if len(samples) < 2:
        raise ValueError("GNN için en az 2 graf örnek gerekir.")
    in_dim = samples[0].node_inputs.shape[1]

    if engine not in ("auto", "torch", "numpy"):
        raise ValueError(f"Bilinmeyen engine={engine!r} (auto|torch|numpy).")
    if engine == "auto":
        engine = "torch" if torch_available() else "numpy"

    # Ölçek EĞİTİM setinden çıkarılır; eğitim tamamen normalize uzayda
    # yapılır, dışarıya fiziksel birim döner (bkz. `predict_physical`).
    x_scaler = ChannelScaler.fit(
        (s.node_inputs for s in samples),
        channel_group_indices(NODE_INPUT_CHANNELS, NODE_INPUT_GROUPS),
    )
    y_scaler = ChannelScaler.fit(
        (s.node_outputs for s in samples if s.node_outputs is not None),
        channel_group_indices(NODE_OUTPUT_CHANNELS, NODE_OUTPUT_GROUPS),
    )
    train_samples, holdout_samples = split_holdout(samples, holdout_fraction, seed)
    scaled = normalized_samples(train_samples, x_scaler, y_scaler)
    scaled_holdout = normalized_samples(holdout_samples, x_scaler, y_scaler)

    out_dim = len(NODE_OUTPUT_CHANNELS)
    history: dict[str, Any] | None = None
    if engine == "torch":
        weights, hist = train_torch_gnn(
            scaled, scaled_holdout, hidden=hidden, n_proc=n_proc, out_dim=out_dim,
            seed=seed, epochs=epochs, lr=lr, patience=patience,
        )
        model = NumpyMeshGNN.from_npz(weights)
        history = hist.as_public()
    else:
        model = NumpyMeshGNN(in_dim, hidden=hidden, n_proc=n_proc, out_dim=out_dim, seed=seed)
        model.fit_output_ls(scaled)
        model.sgd_process(scaled, steps=sgd_steps, lr=1e-4)
    globals_ = []
    for s in samples:
        # OOD için global özet: bbox + ortalama yük/E (kanal 7-12)
        x = s.node_inputs
        g = np.concatenate(
            [
                x[:, :3].min(axis=0),
                x[:, :3].max(axis=0),
                x[:, 7:13].mean(axis=0),
            ]
        )
        globals_.append(g)
    G = np.vstack(globals_)
    # Ana metrikler EĞİTİM kümesinde (eski davranış, biçim korunuyor);
    # holdout ayrı alanda — yoksa None, "yok" ile "sıfır" karışmasın.
    metrics = _field_rmse(train_samples, model, x_scaler, y_scaler)
    metrics["engine"] = engine
    metrics["history"] = history
    metrics["holdout"] = (
        _field_rmse(holdout_samples, model, x_scaler, y_scaler)
        if holdout_samples
        else None
    )
    metrics["architecture"] = {"hidden": hidden, "n_proc": n_proc}
    metrics["n_train"] = len(train_samples)
    metrics["n_holdout"] = len(holdout_samples)
    return {
        "kind": "field_gnn",
        "model": model,
        "x_scaler": x_scaler,
        "y_scaler": y_scaler,
        "normalization": {
            "inputs": x_scaler.summary(NODE_INPUT_CHANNELS),
            "outputs": y_scaler.summary(NODE_OUTPUT_CHANNELS),
        },
        "bounds": bounds_from_matrix(G),
        "n_samples": len(samples),
        "metrics": metrics,
        "input_channels": list(NODE_INPUT_CHANNELS),
        "output_channels": list(NODE_OUTPUT_CHANNELS),
        "seed": seed,
    }


def save_gnn(bundle: dict[str, Any], path: Path | None = None) -> Path:
    dest = path or DEFAULT_GNN_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    model: NumpyMeshGNN = bundle["model"]
    payload = model.to_npz()
    for key, prefix in (("x_scaler", "x"), ("y_scaler", "y")):
        scaler = bundle.get(key)
        if scaler is not None:
            payload.update(scaler.to_npz(prefix))
    payload["bounds_min"] = np.asarray(bundle["bounds"]["min"], dtype=np.float64)
    payload["bounds_max"] = np.asarray(bundle["bounds"]["max"], dtype=np.float64)
    payload["n_samples"] = np.int32(bundle["n_samples"])
    payload["seed"] = np.int32(bundle["seed"])
    np.savez_compressed(dest, **payload)
    meta = dest.with_suffix(".json")
    import json

    meta.write_text(
        json.dumps(
            {
                "kind": "field_gnn",
                "n_samples": bundle["n_samples"],
                "metrics": bundle["metrics"],
                "normalization": bundle.get("normalization"),
                "input_channels": bundle["input_channels"],
                "output_channels": bundle["output_channels"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    bundle["metrics_path"] = str(meta)
    return dest


def load_gnn(path: Path | None = None) -> dict[str, Any] | None:
    dest = path or DEFAULT_GNN_PATH
    if not dest.is_file():
        return None
    with np.load(dest, allow_pickle=False) as z:
        data = {k: z[k] for k in z.files}
    model = NumpyMeshGNN.from_npz(data)
    x_scaler = ChannelScaler.from_npz(data, "x", int(data["W_enc"].shape[0]))
    y_scaler = ChannelScaler.from_npz(data, "y", int(data["W_out"].shape[1]))
    import json

    metrics = {}
    meta = dest.with_suffix(".json")
    if meta.is_file():
        metrics = json.loads(meta.read_text(encoding="utf-8"))
    return {
        "kind": "field_gnn",
        "model": model,
        "x_scaler": x_scaler,
        "y_scaler": y_scaler,
        "normalization": metrics.get("normalization") if isinstance(metrics, dict) else None,
        "bounds": {
            "min": [float(v) for v in data.get("bounds_min", [])],
            "max": [float(v) for v in data.get("bounds_max", [])],
        },
        "n_samples": int(data.get("n_samples", 0)),
        "metrics": metrics.get("metrics") if isinstance(metrics, dict) else {},
        "input_channels": metrics.get("input_channels") if isinstance(metrics, dict) else list(NODE_INPUT_CHANNELS),
        "output_channels": metrics.get("output_channels") if isinstance(metrics, dict) else list(NODE_OUTPUT_CHANNELS),
    }


def global_features_for_ood(X: np.ndarray) -> np.ndarray:
    return np.concatenate(
        [
            X[:, :3].min(axis=0),
            X[:, :3].max(axis=0),
            X[:, 7:13].mean(axis=0),
        ]
    )


def predict_field(bundle: dict[str, Any], sample: GraphSample) -> np.ndarray:
    """Fiziksel birimli düğüm alanı. Ölçek modelle birlikte saklanır;
    uygulanmazsa model sessizce saçmalar."""
    model: NumpyMeshGNN = bundle["model"]
    n_in = sample.node_inputs.shape[1]
    x_scaler = bundle.get("x_scaler") or ChannelScaler.identity(n_in)
    y_scaler = bundle.get("y_scaler") or ChannelScaler.identity(len(NODE_OUTPUT_CHANNELS))
    return predict_physical(model, sample, x_scaler, y_scaler)
