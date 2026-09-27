"""Kanal başına ölçekleme — GNN girdi/çıktıları için (TODO 1.2).

NEDEN: ham kanallar aynı katmana giriyordu. Ölçüldü:

| kanal | aralık |
|---|---|
| x, y, z | 0 … 700 |
| fixed_ux/uy/uz | 0 / 1 |
| youngs_modulus_mpa | 210000 |
| density_tonne_mm3 | 7.85e−9 |

Tek bir doğrusal katmanda E ve koordinatlar çıktıyı domine ediyor; sınır
koşulu bayrakları ile yoğunluk sayısal olarak yok hükmünde. Bunlar FİZİKSEL
olarak en belirleyici girdiler — hangi düğümün ankastre olduğunu bilmeyen
bir model alan tahmin edemez. Çıktı tarafı da normalize değildi: u (mm
mertebesi) ile von Mises (100 MPa mertebesi) aynı kare-hata toplamında
yarışıyor, gerilme deplasmanı eziyordu.

Ölçek eğitim setinden ÇIKARILIR ve modelle birlikte saklanır; tahminde aynı
dönüşüm uygulanmazsa model sessizce saçmalar. Bu yüzden `to_npz`/`from_npz`
model dosyasının parçası.

Sabit kanallar (eğitimde hiç değişmeyen, örn. tek malzeme kullanıldığında
poisson_ratio) ölçek 1 ile bırakılır: sıfıra bölme yok, kanal ortalamasını
çıkarınca sabit sıfır olur ve modele bilgi taşımaz — doğrusu da budur.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

#: Mutlak olarak bu eşiğin altındaki standart sapma "sabit" sayılır.
CONSTANT_STD = 1e-12

#: BAĞIL eşik: std / |ortalama| bundan küçükse kanal sabit sayılır.
#: Gerekçe ölçüldü: `poisson_ratio` fiziksel olarak sabit (0.3) ama
#: float32 saklama yüzünden std = 9.1e−8 çıkıyor. Yalnız mutlak eşik
#: kullanılırsa bu kanal 9.1e−8'e BÖLÜNÜYOR ve saf yuvarlama gürültüsü
#: ±1 mertebesinde bir girdiye dönüşüyor — modele gürültü besliyoruz.
CONSTANT_REL = 1e-6


@dataclass
class ChannelScaler:
    """Kanal başına (x − ortalama) / ölçek."""

    mean: np.ndarray
    scale: np.ndarray
    #: Eğitimde hiç değişmemiş kanallar (ölçek 1 bırakıldı).
    constant: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.constant is None:
            self.constant = np.zeros(self.mean.shape[0], dtype=bool)

    @property
    def n_channels(self) -> int:
        return int(self.mean.shape[0])

    @property
    def constant_channels(self) -> list[int]:
        """Eğitimde hiç değişmemiş kanallar — bilgi taşımazlar."""
        return [i for i, c in enumerate(self.constant) if bool(c)]

    def transform(self, X: np.ndarray) -> np.ndarray:
        return (np.asarray(X, dtype=np.float64) - self.mean) / self.scale

    def inverse_transform(self, Z: np.ndarray) -> np.ndarray:
        return np.asarray(Z, dtype=np.float64) * self.scale + self.mean

    # --- kurulum ---------------------------------------------------------

    @classmethod
    def identity(cls, n_channels: int) -> "ChannelScaler":
        """Dönüşüm yok — ölçek bilgisi olmayan eski model dosyaları için."""
        return cls(np.zeros(n_channels), np.ones(n_channels))

    @classmethod
    def fit(
        cls,
        blocks: Iterable[np.ndarray],
        groups: tuple[tuple[int, ...], ...] = (),
    ) -> "ChannelScaler":
        """Birden çok graftan akışkan ortalama/std — hepsi belleğe yığılmaz.

        Yüzlerce graf × on binlerce düğüm tek dizide toplanamaz; sayaç,
        toplam ve kare toplamı biriktirilir.

        `groups`: aynı fiziksel büyüklüğün bileşenleri (örn. x/y/z). Grup
        üyeleri ORTAK bir ölçek alır — havuzlanmış varyansın karekökü.
        Ayrı ölçek verilirse vektör alanı bileşen bazında gerilir; geometri
        ve yön bilgisi bozulur (bkz. `NODE_INPUT_GROUPS`).
        """
        count = 0
        total: np.ndarray | None = None
        total_sq: np.ndarray | None = None
        for block in blocks:
            A = np.asarray(block, dtype=np.float64)
            if A.ndim != 2 or A.shape[0] == 0:
                continue
            if total is None:
                total = np.zeros(A.shape[1])
                total_sq = np.zeros(A.shape[1])
            if A.shape[1] != total.shape[0]:
                raise ValueError(
                    f"Kanal sayısı tutarsız: {A.shape[1]} ≠ {total.shape[0]}"
                )
            count += A.shape[0]
            total += A.sum(axis=0)
            total_sq += (A**2).sum(axis=0)
        if total is None or count == 0:
            raise ValueError("Ölçek çıkarılacak veri yok.")

        mean = total / count
        var = np.maximum(total_sq / count - mean**2, 0.0)
        for members in groups:
            cols = list(members)
            var[cols] = var[cols].mean()  # havuzlanmış varyans = ortak ölçek
        std = np.sqrt(var)
        was_constant = (std <= CONSTANT_STD) | (std <= CONSTANT_REL * np.abs(mean))
        scale = np.where(was_constant, 1.0, std)
        return cls(mean, scale, was_constant)

    # --- saklama ---------------------------------------------------------

    def to_npz(self, prefix: str) -> dict[str, np.ndarray]:
        return {
            f"{prefix}_mean": self.mean,
            f"{prefix}_scale": self.scale,
            f"{prefix}_constant": np.asarray(self.constant, dtype=bool),
        }

    @classmethod
    def from_npz(
        cls, data: dict[str, np.ndarray], prefix: str, n_channels: int
    ) -> "ChannelScaler":
        """Eksikse birim ölçek: ölçeksiz eğitilmiş eski modeller bozulmasın."""
        if f"{prefix}_mean" not in data or f"{prefix}_scale" not in data:
            return cls.identity(n_channels)
        mean = np.asarray(data[f"{prefix}_mean"], dtype=np.float64)
        constant = data.get(f"{prefix}_constant")
        return cls(
            mean,
            np.asarray(data[f"{prefix}_scale"], dtype=np.float64),
            None if constant is None else np.asarray(constant, dtype=bool),
        )

    def summary(self, names: tuple[str, ...] | list[str]) -> dict[str, dict[str, float]]:
        """Rapor için: hangi kanal ne kadar ölçeklendi, hangisi sabitti."""
        return {
            str(name): {
                "mean": float(self.mean[i]),
                "scale": float(self.scale[i]),
                "constant": bool(self.constant[i]),
            }
            for i, name in enumerate(names)
            if i < self.n_channels
        }
