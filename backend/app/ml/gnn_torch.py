"""GNN'in GERÇEK eğitimi — PyTorch (TODO 1.3b).

NEDEN AYRI DOSYA: torch yalnız EĞİTİM bağımlılığıdır. Kurulu venv'i
563 MB'tan 1.2 GB'a çıkarıyor (ölçüldü) — `gnn.py` başlığındaki "Codespace
imajı torch ile disk dolduruyordu" itirazı gerçek. Bu yüzden:

    eğitim (bu dosya, torch)  ->  ağırlıklar .npz  ->  çıkarım (gnn.py, NumPy)

Sunucu, testler ve Codespace torch KURMADAN tahmin alabilir. İki
uygulamanın aynı sonucu verdiği `test_gnn_torch.py` ile kilitlenir.

ESKİDEN NE VARDI: `NumpyMeshGNN.fit_output_ls` yalnız son katmanı en küçük
karelerle çözüyor, `sgd_process` ara katmanlara zincir kuralını yok sayan
6 adım kaba gradyan atıyordu. **Encoder hiç güncellenmiyordu** — sabit
rastgele projeksiyon. Yani eğitim değildi.

Mimari birebir `NumpyMeshGNN` ile aynıdır (process ağırlıkları adımlar
arasında PAYLAŞILIR), yoksa ağırlıklar dışa aktarılamaz.

float64 kullanılır: graflar küçük, hız sorun değil ve NumPy yoluyla
eşlik 1e-12 mertebesinde doğrulanabiliyor (float32'de 1e-6).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from app.ml.graph_data import GraphSample

logger = logging.getLogger(__name__)

#: Erken durdurma: doğrulama kaybı bu kadar tur iyileşmezse dur.
DEFAULT_PATIENCE = 20


class TorchUnavailable(RuntimeError):
    """torch kurulu değil — `requirements-ml.txt`."""


def torch_available() -> bool:
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


def _torch():
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - ortama bağlı
        raise TorchUnavailable(
            "GNN eğitimi için torch gerekli: "
            "pip install -r requirements-ml.txt "
            "--index-url https://download.pytorch.org/whl/cpu"
        ) from exc
    return torch


@dataclass
class TrainHistory:
    """Her turun kaybı — eğitimin gerçekten indiğini GÖRMEK için."""

    train: list[float] = field(default_factory=list)
    holdout: list[float] = field(default_factory=list)
    best_epoch: int = 0
    stopped_early: bool = False

    def as_public(self) -> dict[str, Any]:
        return {
            "epochs": len(self.train),
            "train_loss_first": self.train[0] if self.train else None,
            "train_loss_last": self.train[-1] if self.train else None,
            "holdout_loss_best": min(self.holdout) if self.holdout else None,
            "best_epoch": self.best_epoch,
            "stopped_early": self.stopped_early,
        }


def _graph_tensors(sample: GraphSample, torch):
    """Bir grafı tensöre çevirir; kenarlar iki yöne de açılır."""
    X = torch.as_tensor(np.asarray(sample.node_inputs), dtype=torch.float64)
    Y = (
        None
        if sample.node_outputs is None
        else torch.as_tensor(np.asarray(sample.node_outputs), dtype=torch.float64)
    )
    e = np.asarray(sample.edges, dtype=np.int64)
    if e.size:
        src = torch.as_tensor(np.concatenate([e[:, 0], e[:, 1]]), dtype=torch.long)
        dst = torch.as_tensor(np.concatenate([e[:, 1], e[:, 0]]), dtype=torch.long)
    else:
        src = torch.zeros(0, dtype=torch.long)
        dst = torch.zeros(0, dtype=torch.long)
    deg = torch.zeros(X.shape[0], dtype=torch.float64)
    deg.index_add_(0, src, torch.ones_like(src, dtype=torch.float64))
    return X, Y, src, dst, deg.clamp(min=1.0).unsqueeze(1)


def build_module(in_dim: int, hidden: int, out_dim: int, n_proc: int, seed: int):
    """`NumpyMeshGNN` ile AYNI mimari, torch parametreleriyle."""
    torch = _torch()
    nn = torch.nn
    torch.manual_seed(seed)

    class TorchMeshGNN(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            scale = 0.15
            g = torch.Generator().manual_seed(seed)

            def par(*shape):
                return nn.Parameter(torch.randn(*shape, generator=g, dtype=torch.float64) * scale)

            self.W_enc = par(in_dim, hidden)
            self.b_enc = nn.Parameter(torch.zeros(hidden, dtype=torch.float64))
            self.W_self = par(hidden, hidden)
            self.W_nei = par(hidden, hidden)
            self.b_proc = nn.Parameter(torch.zeros(hidden, dtype=torch.float64))
            self.W_out = par(hidden, out_dim)
            self.b_out = nn.Parameter(torch.zeros(out_dim, dtype=torch.float64))
            self.n_proc = n_proc

        def forward(self, X, src, dst, deg):
            h = torch.relu(X @ self.W_enc + self.b_enc)
            for _ in range(self.n_proc):
                agg = torch.zeros_like(h)
                if src.numel():
                    agg = agg.index_add(0, src, h[dst]) / deg
                h = torch.relu(h @ self.W_self + agg @ self.W_nei + self.b_proc)
            return h @ self.W_out + self.b_out

    return TorchMeshGNN()


def weights_to_numpy(module) -> dict[str, np.ndarray]:
    """Eğitilmiş ağırlıklar → `NumpyMeshGNN.from_npz` şeması."""
    out = {
        name: param.detach().cpu().numpy().astype(np.float64)
        for name, param in module.named_parameters()
    }
    out["n_proc"] = np.int32(module.n_proc)
    return out


def train_torch_gnn(
    train_samples: Sequence[GraphSample],
    holdout_samples: Sequence[GraphSample] = (),
    *,
    hidden: int = 24,
    n_proc: int = 2,
    out_dim: int = 4,
    seed: int = 2026,
    epochs: int = 200,
    lr: float = 1e-3,
    patience: int = DEFAULT_PATIENCE,
) -> tuple[dict[str, np.ndarray], TrainHistory]:
    """Gerçek geri yayılım. Örnekler NORMALİZE uzayda olmalı.

    Kayıp normalize uzayda MSE'dir; fiziksel birimli metrikler eğitimden
    sonra `gnn._field_rmse` ile ham örnekler üzerinde hesaplanır.

    Doğrulama kümesi verilirse en iyi turun ağırlıkları geri yüklenir —
    son turunki değil. Aksi hâlde model doğrulama kaybı yükselirken
    "eğitim bitti" diye ezberlemiş hâliyle kaydedilir.
    """
    torch = _torch()
    if not train_samples:
        raise ValueError("Eğitim için graf örneği yok.")

    in_dim = int(np.asarray(train_samples[0].node_inputs).shape[1])
    module = build_module(in_dim, hidden, out_dim, n_proc, seed)
    opt = torch.optim.Adam(module.parameters(), lr=lr)

    tensors = [_graph_tensors(s, torch) for s in train_samples if s.node_outputs is not None]
    val = [_graph_tensors(s, torch) for s in holdout_samples if s.node_outputs is not None]
    if not tensors:
        raise ValueError("Düğüm çıktısı olan eğitim örneği yok.")

    history = TrainHistory()
    best_loss = float("inf")
    best_state: dict[str, Any] | None = None
    since_best = 0
    rng = np.random.default_rng(seed)

    for epoch in range(epochs):
        module.train()
        order = rng.permutation(len(tensors))
        total = 0.0
        for i in order:
            X, Y, src, dst, deg = tensors[i]
            opt.zero_grad()
            loss = torch.nn.functional.mse_loss(module(X, src, dst, deg), Y)
            loss.backward()
            opt.step()
            total += float(loss.detach())
        history.train.append(total / len(tensors))

        if val:
            module.eval()
            with torch.no_grad():
                v = sum(
                    float(torch.nn.functional.mse_loss(module(X, src, dst, deg), Y))
                    for X, Y, src, dst, deg in val
                ) / len(val)
            history.holdout.append(v)
            skor = v
        else:
            skor = history.train[-1]

        if skor < best_loss - 1e-12:
            best_loss = skor
            best_state = {k: p.detach().clone() for k, p in module.state_dict().items()}
            history.best_epoch = epoch
            since_best = 0
        else:
            since_best += 1
            if since_best >= patience:
                history.stopped_early = True
                break

    if best_state is not None:
        module.load_state_dict(best_state)
    logger.info(
        "GNN eğitildi: %d tur, en iyi tur %d, kayıp %.6g",
        len(history.train),
        history.best_epoch,
        best_loss,
    )
    return weights_to_numpy(module), history
